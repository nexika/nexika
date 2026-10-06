import { readFileSync, writeFileSync } from "node:fs";
import pixelmatch from "pixelmatch";
import { PNG } from "pngjs";
import { type Box, round } from "./util.js";

export interface DiffResult {
  match: number; // share of pixels that match, 0..1
  size: { actual: [number, number]; expected: [number, number] };
  sizeMismatch: boolean;
  regions: (Box & { off: number })[]; // areas that differ, worst first
  heatmap: string | null;
}

function read(path: string): PNG {
  return PNG.sync.read(readFileSync(path));
}

/** Scale a PNG by an integer-free factor with nearest-neighbour sampling (Figma exports at 2x). */
function scaled(img: PNG, factor: number): PNG {
  if (factor === 1) return img;
  const out = new PNG({ width: Math.round(img.width * factor), height: Math.round(img.height * factor) });
  for (let y = 0; y < out.height; y++) {
    for (let x = 0; x < out.width; x++) {
      const sx = Math.min(img.width - 1, Math.floor(x / factor));
      const sy = Math.min(img.height - 1, Math.floor(y / factor));
      const s = (sy * img.width + sx) * 4, d = (y * out.width + x) * 4;
      out.data[d] = img.data[s]!; out.data[d + 1] = img.data[s + 1]!; out.data[d + 2] = img.data[s + 2]!; out.data[d + 3] = img.data[s + 3]!;
    }
  }
  return out;
}

/** Copy into a canvas of the given size; missing area is magenta so it always counts as different. */
function padded(img: PNG, width: number, height: number): PNG {
  const out = new PNG({ width, height });
  for (let i = 0; i < out.data.length; i += 4) { out.data[i] = 255; out.data[i + 1] = 0; out.data[i + 2] = 255; out.data[i + 3] = 255; }
  PNG.bitblt(img, out, 0, 0, Math.min(img.width, width), Math.min(img.height, height), 0, 0);
  return out;
}

export function diff(actualPath: string, expectedPath: string, opts: { heatmap?: string; expectedScale?: number; cell?: number } = {}): DiffResult {
  const actual = read(actualPath);
  const expected = scaled(read(expectedPath), opts.expectedScale ?? 1);
  const width = Math.max(actual.width, expected.width);
  const height = Math.max(actual.height, expected.height);
  const a = padded(actual, width, height), e = padded(expected, width, height);
  const out = new PNG({ width, height });
  const changed = pixelmatch(a.data, e.data, out.data, width, height, { threshold: 0.1, includeAA: false, alpha: 0.2 });

  // Regions: cells of the grid where more than 8% of pixels differ, merged with their neighbours.
  const cell = opts.cell ?? 24;
  const cols = Math.ceil(width / cell), rows = Math.ceil(height / cell);
  const hot = new Float32Array(cols * rows);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      if (out.data[i] === 255 && out.data[i + 1] === 0 && out.data[i + 2] === 0) hot[Math.floor(y / cell) * cols + Math.floor(x / cell)]! += 1;
    }
  }
  const isHot = (c: number, r: number) => hot[r * cols + c]! / (cell * cell) > 0.08;
  const seen = new Uint8Array(cols * rows);
  const regions: DiffResult["regions"] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (seen[r * cols + c] || !isHot(c, r)) continue;
      let minC = c, maxC = c, minR = r, maxR = r, sum = 0, count = 0;
      const stack: [number, number][] = [[c, r]];
      seen[r * cols + c] = 1;
      while (stack.length) {
        const [cc, rr] = stack.pop()!;
        minC = Math.min(minC, cc); maxC = Math.max(maxC, cc); minR = Math.min(minR, rr); maxR = Math.max(maxR, rr);
        sum += hot[rr * cols + cc]!; count++;
        for (const [dc, dr] of [[1, 0], [-1, 0], [0, 1], [0, -1]] as const) {
          const nc = cc + dc, nr = rr + dr;
          if (nc >= 0 && nr >= 0 && nc < cols && nr < rows && !seen[nr * cols + nc] && isHot(nc, nr)) {
            seen[nr * cols + nc] = 1;
            stack.push([nc, nr]);
          }
        }
      }
      regions.push({ x: minC * cell, y: minR * cell, w: (maxC - minC + 1) * cell, h: (maxR - minR + 1) * cell, off: round(sum / (count * cell * cell), 3) });
    }
  }
  regions.sort((p, q) => q.off * q.w * q.h - p.off * p.w * p.h);

  if (opts.heatmap) writeFileSync(opts.heatmap, PNG.sync.write(out));
  return {
    match: round(1 - changed / (width * height), 4),
    size: { actual: [actual.width, actual.height], expected: [expected.width, expected.height] },
    sizeMismatch: actual.width !== expected.width || actual.height !== expected.height,
    regions: regions.slice(0, 20),
    heatmap: opts.heatmap ?? null,
  };
}
