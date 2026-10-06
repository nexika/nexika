import { readFileSync, writeFileSync } from "node:fs";
import pixelmatch from "pixelmatch";
import { PNG } from "pngjs";
import { round } from "./util.js";
function read(path) {
    return PNG.sync.read(readFileSync(path));
}
/** Scale a PNG by an integer-free factor with nearest-neighbour sampling (Figma exports at 2x). */
function scaled(img, factor) {
    if (factor === 1)
        return img;
    const out = new PNG({ width: Math.round(img.width * factor), height: Math.round(img.height * factor) });
    for (let y = 0; y < out.height; y++) {
        for (let x = 0; x < out.width; x++) {
            const sx = Math.min(img.width - 1, Math.floor(x / factor));
            const sy = Math.min(img.height - 1, Math.floor(y / factor));
            const s = (sy * img.width + sx) * 4, d = (y * out.width + x) * 4;
            out.data[d] = img.data[s];
            out.data[d + 1] = img.data[s + 1];
            out.data[d + 2] = img.data[s + 2];
            out.data[d + 3] = img.data[s + 3];
        }
    }
    return out;
}
/** Copy into a canvas of the given size; missing area is magenta so it always counts as different. */
function padded(img, width, height) {
    const out = new PNG({ width, height });
    for (let i = 0; i < out.data.length; i += 4) {
        out.data[i] = 255;
        out.data[i + 1] = 0;
        out.data[i + 2] = 255;
        out.data[i + 3] = 255;
    }
    PNG.bitblt(img, out, 0, 0, Math.min(img.width, width), Math.min(img.height, height), 0, 0);
    return out;
}
/** Grey levels, downsampled by `f` (mean of each f×f block). */
function grey(img, f) {
    const w = Math.floor(img.width / f), h = Math.floor(img.height / f);
    const px = new Float32Array(w * h);
    for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
            let sum = 0;
            for (let dy = 0; dy < f; dy++) {
                for (let dx = 0; dx < f; dx++) {
                    const i = ((y * f + dy) * img.width + (x * f + dx)) * 4;
                    sum += 0.299 * img.data[i] + 0.587 * img.data[i + 1] + 0.114 * img.data[i + 2];
                }
            }
            px[y * w + x] = sum / (f * f);
        }
    }
    return { w, h, px };
}
/**
 * Content-aligned comparison: a section that is a little taller pushes everything below it down,
 * and a position-for-position diff then calls the rest of the page different. Here each horizontal
 * band of the design is compared with the built page at the offset where it matches best (searched
 * near the previous band's offset), so the score says how close the page looks, and the offsets say
 * where heights drift.
 */
function aligned(actual, expected, band = 48, reach = 240) {
    const f = 4;
    const a = grey(actual, f), e = grey(expected, f);
    const w = Math.min(a.w, e.w);
    const bandH = Math.max(2, Math.floor(band / f));
    const step = 1;
    let prev = 0;
    let matched = 0, total = 0;
    const offsets = [];
    for (let y0 = 0; y0 + bandH <= e.h; y0 += bandH) {
        let best = prev, bestCost = Infinity;
        const lo = Math.max(-y0, prev - Math.floor(reach / f)), hi = prev + Math.floor(reach / f);
        for (let dy = lo; dy <= hi; dy += step) {
            if (y0 + dy + bandH > a.h)
                break;
            let cost = 0;
            for (let y = 0; y < bandH; y++) {
                const ra = (y0 + dy + y) * a.w, re = (y0 + y) * e.w;
                for (let x = 0; x < w; x += 2)
                    cost += Math.abs(a.px[ra + x] - e.px[re + x]);
            }
            // A small pull towards the previous offset keeps flat bands (plain colour) from wandering.
            cost += Math.abs(dy - prev) * 0.5;
            if (cost < bestCost) {
                bestCost = cost;
                best = dy;
            }
        }
        prev = best;
        offsets.push({ y: y0 * f, dy: best * f });
        // Score this band at full resolution with the same comparison as the whole-page diff
        // (pixelmatch, anti-aliasing ignored), at the offset where its content really is.
        const ye = y0 * f, ya = ye + best * f;
        const h = Math.min(band, expected.height - ye, actual.height - ya);
        const wFull = Math.min(actual.width, expected.width);
        if (h > 0 && ya >= 0) {
            const ea = new PNG({ width: wFull, height: h }), aa = new PNG({ width: wFull, height: h });
            PNG.bitblt(expected, ea, 0, ye, wFull, h, 0, 0);
            PNG.bitblt(actual, aa, 0, ya, wFull, h, 0, 0);
            const bad = pixelmatch(aa.data, ea.data, null, wFull, h, { threshold: 0.1, includeAA: false });
            matched += wFull * h - bad;
            total += wFull * h;
        }
    }
    // Flat bands (a plain background, a photo) can match at many offsets: smooth with a running
    // median, then report only shifts that hold for several bands.
    const med = offsets.map((_, i) => {
        const win = offsets.slice(Math.max(0, i - 3), i + 4).map((o) => o.dy).sort((p, q) => p - q);
        return win[Math.floor(win.length / 2)];
    });
    const shifts = [];
    let last = 0;
    for (let i = 0; i < med.length; i++) {
        const held = med.slice(i, i + 3);
        if (held.length === 3 && held.every((v) => Math.abs(v - med[i]) < 8) && Math.abs(med[i] - last) >= 12) {
            shifts.push({ designY: offsets[i].y, builtY: offsets[i].y + med[i], dy: med[i] - last });
            last = med[i];
        }
    }
    return { match: round(total ? matched / total : 0, 4), shifts: shifts.slice(0, 20) };
}
export function diff(actualPath, expectedPath, opts = {}) {
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
            if (out.data[i] === 255 && out.data[i + 1] === 0 && out.data[i + 2] === 0)
                hot[Math.floor(y / cell) * cols + Math.floor(x / cell)] += 1;
        }
    }
    const isHot = (c, r) => hot[r * cols + c] / (cell * cell) > 0.08;
    const seen = new Uint8Array(cols * rows);
    const regions = [];
    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            if (seen[r * cols + c] || !isHot(c, r))
                continue;
            let minC = c, maxC = c, minR = r, maxR = r, sum = 0, count = 0;
            const stack = [[c, r]];
            seen[r * cols + c] = 1;
            while (stack.length) {
                const [cc, rr] = stack.pop();
                minC = Math.min(minC, cc);
                maxC = Math.max(maxC, cc);
                minR = Math.min(minR, rr);
                maxR = Math.max(maxR, rr);
                sum += hot[rr * cols + cc];
                count++;
                for (const [dc, dr] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
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
    if (opts.heatmap)
        writeFileSync(opts.heatmap, PNG.sync.write(out));
    return {
        match: round(1 - changed / (width * height), 4),
        aligned: aligned(actual, expected),
        size: { actual: [actual.width, actual.height], expected: [expected.width, expected.height] },
        sizeMismatch: actual.width !== expected.width || actual.height !== expected.height,
        regions: regions.slice(0, 20),
        heatmap: opts.heatmap ?? null,
    };
}
