// Per-film R / G / B tone curves (Caduceus for OM-3, branch feature/rgb-curves, camera-tested test 4, 2026-11-15).
// Each channel has 5 points at 0 / 25 / 50 / 75 / 100 % of the camera's 12-bit gamma output, each an offset of
// -7..+7 steps of 48 (1.2 % of full scale). The camera bends its R, G and B gamma tables by a monotone cubic through
// the points (firmware cv_prm / cv_d in st_run, in the same pass as split toning); this is the same integer maths as
// research/rgbcurves/model.py, bit for bit. Not in LOOKS.BIN or the photo code yet: set on the camera's RGB row.
import type { Look } from './pack';

export type Channel = 'r' | 'g' | 'b';
export interface RgbCurves { r: number[]; g: number[]; b: number[] }   // 5 offsets each, -7..7
export const CURVE_POINTS = 5, CURVE_MAX = 7, CURVE_STEP = 48;
export const CHANNELS: Channel[] = ['r', 'g', 'b'];
const X = [0, 1024, 2048, 3072, 4096];
const H = [1024, 1024, 1024, 1024];
const INV = H.map((h) => Math.trunc((1 << 24) / h));

const tdiv = (a: number, b: number) => Math.trunc(a / b);   // the CPU's div: truncates toward zero
export const flatCurves = (): RgbCurves => ({ r: [0, 0, 0, 0, 0], g: [0, 0, 0, 0, 0], b: [0, 0, 0, 0, 0] });
export const curveIsFlat = (v: number[]) => v.every((x) => !x);
export const hasCurves = (l: Look) => !!l.rgb && CHANNELS.some((c) => !curveIsFlat(l.rgb![c]));

/** A channel's 5 offsets -> the firmware's block (Y[5], A[4], B[4]). */
function prm(v: number[]) {
  const Y = v.map((x) => Math.max(-CURVE_MAX, Math.min(CURVE_MAX, x)) * CURVE_STEP);
  const d = [0, 1, 2, 3].map((i) => tdiv((Y[i + 1] - Y[i]) * 4096, H[i]));
  const m = [d[0], 0, 0, 0, d[3]];
  for (let i = 1; i < 4; i++) {
    const a = d[i - 1], b = d[i];
    m[i] = a === 0 || b === 0 || (a < 0) !== (b < 0) ? 0 : tdiv(2 * a * b, a + b);
  }
  return { Y, A: [0, 1, 2, 3].map((i) => (H[i] * m[i]) >> 12), B: [0, 1, 2, 3].map((i) => (H[i] * m[i + 1]) >> 12) };
}

/** The curve's change D(t) at a 12-bit table value t (0..4095), as the camera. */
export function curveDelta(v: number[]): (t: number) => number {
  if (curveIsFlat(v)) return () => 0;
  const { Y, A, B } = prm(v);
  return (t: number) => {
    t = Math.max(0, Math.min(4095, Math.round(t)));
    const i = Math.min(3, t >> 10);
    const s = ((t - X[i]) * INV[i]) >> 12, s2 = (s * s) >> 12, s3 = (s2 * s) >> 12;
    const h00 = 2 * s3 - 3 * s2 + 4096, h10 = s3 - 2 * s2 + s, h01 = 3 * s2 - 2 * s3, h11 = s3 - s2;
    return Math.floor((h00 * Y[i] + h10 * A[i] + h01 * Y[i + 1] + h11 * B[i]) / 4096);   // asr 12
  };
}

/** A parsed `rgb` field, or undefined when missing, flat or malformed. */
export function parseCurves(v: unknown): RgbCurves | undefined {
  if (!v || typeof v !== 'object') return undefined;
  const o = v as Record<string, unknown>, out = flatCurves();
  for (const c of CHANNELS) {
    const a = o[c];
    if (a === undefined) continue;
    if (!Array.isArray(a) || a.length !== CURVE_POINTS || !a.every((x) => Number.isInteger(x) && Math.abs(x) <= CURVE_MAX)) return undefined;
    out[c] = a.slice();
  }
  return CHANNELS.some((c) => !curveIsFlat(out[c])) ? out : undefined;
}
