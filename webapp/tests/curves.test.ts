import { describe, expect, it } from 'vitest';
import { curveDelta, parseCurves } from '../src/curves';
import { bendSplit } from '../src/split';

// research/rgbcurves/model.py (feature/rgb-curves, test 4) d_at at these inputs, for these 5-point curves
const TS = [0, 1, 512, 1024, 1500, 2048, 2600, 3072, 3600, 4000, 4095];
const CASES: Record<string, [number[], number[]]> = {
  flat: [[0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
  black7: [[7, 0, 0, 0, 0], [336, 335, 126, 0, 0, 0, 0, 0, 0, 0, 0]],
  mid7: [[0, 0, 7, 0, 0], [0, 0, 0, 0, 150, 336, 148, 0, 0, 0, 0]],
  ramp: [[0, 2, 3, 4, 5], [0, 0, 52, 96, 120, 144, 169, 192, 216, 235, 239]],
  zig: [[-7, 7, -7, 7, -7], [-336, -336, 84, 336, 35, -336, 39, 336, 70, -268, -336]],
  sc: [[0, -3, 0, 3, 0], [0, -1, -90, -144, -97, 0, 96, 144, 87, 14, 0]],
};

describe('RGB curves', () => {
  it('match the firmware model bit for bit', () => {
    for (const [name, [v, want]] of Object.entries(CASES)) expect(TS.map(curveDelta(v)), name).toEqual(want);
  });
  it('parse only valid curves, flat ones drop out', () => {
    expect(parseCurves({ r: [0, 1, 0, 0, 0] })).toEqual({ r: [0, 1, 0, 0, 0], g: [0, 0, 0, 0, 0], b: [0, 0, 0, 0, 0] });
    expect(parseCurves({ r: [0, 0, 0, 0, 0] })).toBeUndefined();
    expect(parseCurves({ g: [0, 8, 0, 0, 0] })).toBeUndefined();
    expect(parseCurves({ b: [0, 1, 0] })).toBeUndefined();
  });
  it('bend the preview like the camera: a red lift in the shadows', () => {
    const img = new Float32Array([0.25, 0.25, 0.25, 0.75, 0.75, 0.75]);
    bendSplit(img, 2, undefined, 1, 0, { r: [0, 7, 0, 0, 0], g: [0, 0, 0, 0, 0], b: [0, 0, 0, 0, 0] });
    expect(img[0]).toBeGreaterThan(0.3);          // red up by about 336 / 4095 at 25 %
    expect(img[1]).toBeCloseTo(0.25, 2);
    expect(img[3]).toBeCloseTo(0.75, 2);         // nothing at 75 %
  });
});
