#!/usr/bin/env python3
"""Emulator regression tests: each test boots a build in om-emu one or more times and checks the debug log.

    python3 tools/test/emu_test.py BUILD_DIR [--only NAME ...] [--jobs N] [--out DIR] [--repeat N] [--without BUILD_DIR]
                                   [--stock OLY_E_147_1100_0000_0000.BIN]

BUILD_DIR is a firmware/build.py --out folder (main.bin, GUIDES.BIN, LABELS.BIN). om-emu comes from $OM3_EMU
(research/setup.sh writes it to env.sh). The static:* tests are tools/test/static_check.py's checks and need the
stock firmware (--stock, else $OM3_STOCK, else $OM3_WORK/stock). --repeat N runs each test N times and fails if any run fails.
--without BUILD_DIR (needs --only) runs those tests on a build without the fix and exits 1 if any passes.
Exit 0 when every test passes, 1 otherwise.
"""
import argparse, concurrent.futures, json, os, pathlib, re, subprocess, sys, tempfile
from dataclasses import dataclass, field

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'firmware'))
import static_check  # noqa: E402
from provenance import source_digest  # noqa: E402

DRIVER = REPO / 'tools/emulator/session_ed1.mjs'
DEBUG_TXT = REPO / 'debug-log/DEBUG.TXT'
MODEL = 'E147'
AUDIT = 'patch-audit'
STATIC_PREFIX = 'static:'
STATIC = [STATIC_PREFIX + n for n in static_check.CHECKS]
BOOT_TIMEOUT_S = 300
AUDIT_TOKENS = 'wait:100'
LOG_PATH = 'OM3MOD/CADLOG.TXT'
# A branch that changes these needs a suite pass on its HEAD before a pull request (tools/test/pr_gate.py).
TESTED_PATHS = ('firmware/', 'card/', 'tools/emulator/', 'tools/test/')
PASS_FILE = 'emu-test-pass.json'
# Two sessions peak at about 1.3 GB each. More side by side has had runs killed (research/TESTING.md).
DEFAULT_JOBS = 2
# Switch positions the driver sets before each boot (session_ed1.mjs PSET0, MODE0).
PHOTO_SWITCH_PHOTO = 2
MODE_DIAL_P = 2
MODE_DIAL_C1 = 7
MODE_DIAL_M = 9
# The movie position, set explicitly: om-emu 0819080 (2026-11-14) reads an unset switch as photo, so a test that left it
# unset ran in photo (v0.30 test 8, emulator).
PHOTO_SWITCH_VIDEO = 1

# From COLOR 1 on the shooting screen, picks FILM 2: the list runs COLOR 1-4, then the films.
# Keep in sync with FILM_2_LINE.
PICK_FILM_2 = 'ok wait ok wait right wait right wait right wait right wait right wait ok wait menu wait wait'
FILM_2_LINE = r'^Picture mode setting: \d+ = COLOR \d+, FILM 2$'

# In P: picks a film, assigns it to C1 (menu), then picks another film in P.
BOOT1_ASSIGN_C1 = ('s1 wait wait ok wait ok wait right wait right wait right wait right wait ok wait menu wait wait s1 wait wait menu wait right wait right wait right wait right wait right wait right wait right wait ok wait ok wait down wait ok wait ok wait menu wait menu wait menu wait wait ok wait ok wait right wait right wait right wait right wait right wait ok wait menu wait wait s1 wait wait poweroff')
C1_TURN_WHILE_OFF = 'wait wait wait s1 wait wait poweroff'
C1_TURN_BEFORE_HALF_PRESS = 'wait wait wait mode:7 wait wait wait s1 wait wait poweroff'
VIDEO_BOOT = 'wait wait wait s1 wait wait poweroff'
# Picture mode 54 = COLOR 1 is C1's film (FILM 1), 55 = COLOR 2 is the film picked last in P (FILM 6).
C1_FILM_LINE = r'^Picture mode setting: 54 = COLOR 1, FILM 1$'
P_FILM_LINE = r'^Picture mode setting: 55 = COLOR 2, FILM 6$'
C1_RECORD_LINE = r'^Custom modes: a valid record at the first look: yes'
GROUP_C1_LINE = r'^Custom modes: group now .*: 0, mode code 53'
# The photo boot before it leaves the video boot with nothing put back and the photo switch read as video.
# rc_go does no film work in video (#53): no film switched, no record write. A build without the fix writes the record.
VIDEO_BOOT_LINES = [r'^Films put back after a shooting-mode change: 0 \(camera settings written: 0\)',
                    r'photo check .*: (193|10)$',    # 192 + the movie switch, or the video mode's code 10
                    r'^Custom modes: group now .*; .*films switched: 0, record writes: 0,']   # PR #56's early load reads
                    # the dial position (el_ok -> cm_gnow) in video too, so group and code show it; no work follows


@dataclass
class Boot:
    tokens: str
    expect: list = field(default_factory=list)     # regexes, each must match a debug log line
    reject: list = field(default_factory=list)     # regexes no debug log line may match
    mode_dial: int = MODE_DIAL_P
    photo_switch: int = PHOTO_SWITCH_PHOTO    # None leaves PSET0 unset: the movie switch


TESTS = {
    'boot-smoke': [
        Boot('s1 wait wait poweroff', expect=[
            r'^Card files: all match this firmware$',
            r'^LOOKS\.BIN looks loaded: yes$',
            r'^GUIDES\.BIN code block loaded: yes$',
            r'^Films from: the card',
            r'^Block written this power-on: 1 times',
        ]),
    ],
    'films-from-camera-memory': [
        Boot('s1 wait wait poweroff', expect=[r'^Films from: the card']),
        Boot('s1 wait wait poweroff', expect=[
            r'^Films in camera memory: a valid block at power-on: yes',
            r'^Films from: the camera',
        ], reject=[r'^Films from: the card']),
    ],
    'film-kept-with-half-press-after-pick': [
        Boot('s1 wait wait poweroff'),
        Boot(f'wait wait s1 wait wait {PICK_FILM_2} s1 wait wait poweroff', expect=[FILM_2_LINE]),
        Boot('wait wait s1 wait wait poweroff', expect=[FILM_2_LINE]),
    ],
    'film-kept-with-no-half-press-after-pick': [
        Boot('s1 wait wait poweroff'),
        Boot(f'wait wait s1 wait wait {PICK_FILM_2} poweroff'),
        Boot('wait wait s1 wait wait poweroff', expect=[FILM_2_LINE]),
    ],
    'custom-mode-film-over-dial-turn-while-off': [
        Boot(BOOT1_ASSIGN_C1),
        Boot(C1_TURN_WHILE_OFF, expect=[C1_FILM_LINE, C1_RECORD_LINE], mode_dial=MODE_DIAL_C1),
        Boot(C1_TURN_WHILE_OFF, expect=[P_FILM_LINE, C1_RECORD_LINE], mode_dial=MODE_DIAL_P),
    ],
    'dial-turn-before-first-half-press': [
        Boot(BOOT1_ASSIGN_C1),
        Boot(C1_TURN_BEFORE_HALF_PRESS, expect=[GROUP_C1_LINE, C1_FILM_LINE], mode_dial=MODE_DIAL_M),
    ],
    'video-boot-after-photo-boot': [
        Boot('s1 wait wait poweroff'),
        Boot(VIDEO_BOOT, expect=VIDEO_BOOT_LINES, photo_switch=PHOTO_SWITCH_VIDEO),
    ],
}

# Tests the current release fails, with the reason. They do not fail a run. Remove an entry once main passes it.
KNOWN_FAILURES = {}   # v0.30 test 8: 'film-kept-with-no-half-press-after-pick' passes with PR #56 (early load)


def git(*args, cwd=REPO):
    r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def pass_path(cwd=REPO):
    d = git('rev-parse', '--absolute-git-dir', cwd=cwd)
    return pathlib.Path(d, PASS_FILE) if d else None


def read_pass(cwd=REPO):
    p = pass_path(cwd)
    try:
        return json.loads(p.read_text()) if p else None
    except (OSError, ValueError):
        return None


def record_pass(build):
    """Writes the pass that pr_gate.py checks, only for committed code: a dirty tree is not what a PR proposes."""
    head, dirty, p = git('rev-parse', 'HEAD'), git('status', '--porcelain'), pass_path()
    try:
        built = json.loads((build / 'build.json').read_text()).get('source_sha256')
    except (OSError, ValueError):
        built = None
    if built != source_digest(REPO):
        print('No pass recorded for the pull request check: the build is not from this checkout, build it again')
    elif head and dirty == '' and p:
        p.write_text(json.dumps({'head': head, 'build': str(build)}))
        print(f'Pass recorded on {head[:12]} for the pull request check')
    else:
        print('No pass recorded for the pull request check: commit your changes, then run the suite again')


def node(*args, env=None, timeout=BOOT_TIMEOUT_S):
    return subprocess.run(['node', *map(str, args)], env=env, capture_output=True, text=True, timeout=timeout)


def card_tool(emu, *args):
    r = node(f'{emu}/bin/card.mjs', *args)
    if r.returncode:
        raise RuntimeError(f'card.mjs {" ".join(map(str, args))}: {r.stderr.strip()}')


def make_card(emu, build, looks, path):
    card_tool(emu, 'new', path)
    card_tool(emu, 'mkdir', path, 'OM3MOD')
    for local, name in [(build / 'GUIDES.BIN', 'GUIDES.BIN'), (build / 'LABELS.BIN', 'LABELS.BIN'),
                        (looks, 'LOOKS.BIN'), (DEBUG_TXT, 'DEBUG.TXT')]:
        card_tool(emu, 'put', path, local, f'OM3MOD/{name}')


def read_log(emu, card, dest):
    """The boot's debug log, then removed from the card so the next boot cannot pass on a stale one."""
    r = node(f'{emu}/bin/card.mjs', 'get', card, LOG_PATH, dest)
    if r.returncode:
        return None
    card_tool(emu, 'rm', card, LOG_PATH)
    return [l.rstrip() for l in dest.read_bytes().decode('latin1').replace('\r', '').split('\n') if l.strip()]


def run_test(name, boots, emu, build, card0, out):
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'OM_EMU_MODEL': MODEL, 'NV_FILE': str(d / 'nv.bin'), }
    (d / 'nv.bin').unlink(missing_ok=True)
    card, errors = card0, []
    for i, boot in enumerate(boots, 1):
        nxt = d / f'card{i}.omsd'
        try:
            r = node(DRIVER, emu, build / 'main.bin', card, d / f'boot{i}.json', nxt, boot.tokens,
                     env={**env, 'MODE0': str(boot.mode_dial),
                     **({} if boot.photo_switch is None else {'PSET0': str(boot.photo_switch)})})
        except subprocess.TimeoutExpired:
            return name, [f'boot {i}: no result after {BOOT_TIMEOUT_S} s']
        (d / f'boot{i}.log').write_text(r.stdout + r.stderr)
        if r.returncode:
            return name, [f'boot {i}: driver exit {r.returncode} (boot{i}.log)']
        if not nxt.exists():
            return name, [f'boot {i}: driver saved no card (boot{i}.log)']
        if boot.tokens.split()[-1] == 'poweroff' and not json.loads((d / f'boot{i}.json').read_text())['log'][-1].get('power_off'):
            errors.append(f'boot {i}: the firmware did not power off (boot{i}.json)')
        lines = read_log(emu, nxt, d / f'cadlog{i}.txt')
        if lines is None:
            if boot.expect or boot.reject:
                return name, [f'boot {i}: no {LOG_PATH} on the card']
            lines = []
        errors += [f'boot {i}: no line matches {p}' for p in boot.expect if not any(re.search(p, l) for l in lines)]
        errors += [f'boot {i}: unwanted line {l!r}' for p in boot.reject for l in lines if re.search(p, l)]
        card = nxt
    return name, errors


def run_audit(emu, build, out):
    """om-emu's patch audit: no patched byte where the camera's boot does not load it, no task started at power-on."""
    d = out / AUDIT
    d.mkdir(parents=True, exist_ok=True)
    r = node(f'{emu}/bin/session.mjs', '--model', MODEL, '--main', build / 'main.bin', '--loaded', 'auto', AUDIT_TOKENS)
    (d / 'session.log').write_text(r.stdout + r.stderr)
    summary = next((json.loads(l) for l in r.stdout.splitlines() if l.startswith('{"summary"')), None)
    if r.returncode or not summary:
        return AUDIT, [f'session.mjs exit {r.returncode}, no summary (session.log)']
    audit = summary.get('patch_audit')
    if not isinstance(audit, dict) or not {'unloaded', 'tasks'} <= audit.keys():
        return AUDIT, ['no patch_audit unloaded and tasks in the summary (session.log)']
    return AUDIT, [f'{k}: {json.dumps(audit[k])}' for k in ('unloaded', 'tasks') if audit[k]]


def newest_looks():
    def key(d):
        n, _, pre = d.name.lstrip('v').partition('-')
        return [int(x) for x in n.split('.')], pre == '', pre
    rel = max((d for d in (REPO / 'releases').iterdir() if d.name.startswith('v') and (d / 'LOOKS.BIN').exists()), key=key)
    return rel / 'LOOKS.BIN'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('build', type=pathlib.Path)
    ap.add_argument('--only', nargs='+', choices=sorted([*TESTS, AUDIT, *STATIC]))
    ap.add_argument('--jobs', type=lambda v: max(1, int(v)), default=DEFAULT_JOBS)
    ap.add_argument('--out', type=pathlib.Path)
    ap.add_argument('--looks', type=pathlib.Path)
    ap.add_argument('--repeat', type=lambda v: max(1, int(v)), default=1, help='runs per test, each in its own subfolder')
    ap.add_argument('--stock', help='official firmware file, for the static:* tests')
    ap.add_argument('--without', type=pathlib.Path, help='build without the fix: the --only tests must FAIL on it')
    a = ap.parse_args()
    if a.without and not a.only:
        sys.exit('--without needs --only: name the tests that must catch the bug')
    emu = os.environ.get('OM3_EMU')
    if not emu or not pathlib.Path(emu, 'bin/card.mjs').exists():
        sys.exit('OM3_EMU is not set to an om-emu emu/ folder: run research/setup.sh, then . $OM3_WORK/env.sh')
    build = (a.without or a.build).resolve()
    if not (build / 'main.bin').exists():
        sys.exit(f'{build}: no main.bin (a firmware/build.py --out folder)')
    out = (a.out or pathlib.Path(tempfile.mkdtemp(prefix='emu-test-'))).resolve()
    out.mkdir(parents=True, exist_ok=True)
    card0 = out / 'card0.omsd'
    make_card(emu, build, (a.looks or newest_looks()).resolve(), card0)
    names = a.only or sorted([*TESTS, AUDIT, *STATIC])
    stock = static_check.find_stock(a.stock) if any(n in STATIC for n in names) else None
    runs = [(n, k) for n in names for k in range(1, a.repeat + 1)]
    print(f'{len(names)} tests{f" x {a.repeat}" if a.repeat > 1 else ""} on {build}, results in {out}')
    def one(run):
        n, k = run
        d = out / f'run{k}' if a.repeat > 1 else out
        try:
            if n in STATIC:
                return n, static_check.CHECKS[n[len(STATIC_PREFIX):]](build, stock)
            return run_audit(emu, build, d) if n == AUDIT else run_test(n, TESTS[n], emu, build, card0, d)
        except static_check.Skip as e:
            return n, [f'could not run: {e}']
        except (subprocess.TimeoutExpired, RuntimeError, OSError, ValueError, KeyError, IndexError) as e:
            return n, [f'runner error: {e}']
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as pool:
        done = list(pool.map(one, runs))
    results = {n: [] for n in names}
    for (n, k), (_, errors) in zip(runs, done):
        results[n] += [f'run {k}: {e}' if a.repeat > 1 else e for e in errors]
    failed = 0
    for name, errors in results.items():
        if a.without:
            print(f'{"caught" if errors else "MISSED":<7}{name}')
            for e in errors or ['passed on the build without the fix: the test does not catch the bug']:
                print(f'      {e}')
            failed += not errors
            continue
        known = KNOWN_FAILURES.get(name)
        print(f'{"pass" if not errors else "known" if known else "FAIL":<6}{name}')
        for e in errors:
            print(f'      {e}')
        if known:
            print(f'      {known}' if errors else '      listed in KNOWN_FAILURES but passed: remove it')
        failed += bool(errors) and not known
    (out / 'results.json').write_text(json.dumps(results, indent=1))
    if not a.only and not a.without:
        if failed:
            p = pass_path()
            if p:
                p.unlink(missing_ok=True)
        else:
            record_pass(build)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
