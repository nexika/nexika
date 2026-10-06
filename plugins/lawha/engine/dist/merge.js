const TAILWIND = [["sm", 640], ["md", 768], ["lg", 1024], ["xl", 1280], ["2xl", 1536]];
/** The Tailwind prefix for each frame above the base: the largest breakpoint not above the frame's
 * width that is still above the previous frame's width. */
export function breakpoints(widths) {
    const sorted = [...widths].sort((a, b) => a - b);
    return sorted.map((w, i) => {
        if (i === 0)
            return "base";
        const prev = sorted[i - 1];
        // Candidates start above the previous frame (so it keeps its own layout) and at or below this one.
        const fits = TAILWIND.filter(([, min]) => min > prev && min <= w);
        // A desktop frame right after a phone frame: start at lg, since a phone layout stretched to
        // 1279px rarely works. Otherwise the largest breakpoint a little below the frame's width (a 1024
        // or 834 tablet from md, a 1440 desktop from xl), else the first candidate.
        if (prev < 600 && w >= 1200 && fits.some(([n]) => n === "lg"))
            return "lg";
        const pick = fits.filter(([, min]) => min <= w * 0.95).pop() ?? fits[0];
        return pick ? pick[0] : `min-[${w}px]`;
    });
}
function sizeText(s) {
    return s.mode === "fixed" ? `${s.px}px` : s.mode;
}
/** The properties that can change between breakpoints, flattened for comparison. */
function flat(s) {
    const f = {
        width: sizeText(s.width),
        height: s.kind === "text" ? "hug" : sizeText(s.height),
        grow: s.grow,
        stretch: s.selfStretch,
        radius: s.radius,
        fill: s.fills.map((p) => p.token ?? p.hex ?? p.imageRef ?? p.css).join(" + ") || null,
        border: s.border ? `${JSON.stringify(s.border.width)} ${s.border.color?.token ?? s.border.color?.hex}` : null,
        shadow: s.shadow,
    };
    if (s.layout)
        Object.assign(f, { dir: s.layout.dir, gap: s.layout.gap, wrap: s.layout.wrap, justify: s.layout.justify, align: s.layout.align, pad: s.layout.pad.join(" ") });
    if (s.text) {
        Object.assign(f, { content: s.text.content, font: `${s.text.family} ${s.text.weight}`, size: s.text.size, lineHeight: s.text.lineHeight, tracking: s.text.letterSpacing, case: s.text.transform, textAlign: s.text.align, color: s.text.color?.token ?? s.text.color?.hex ?? null, trim: s.text.trim ? "cap" : null });
    }
    return f;
}
/** What a layer contains: its texts (normalised) and its images. */
function signature(s, out = new Set()) {
    if (s.text)
        out.add("t:" + s.text.content.toLowerCase().replace(/\s+/g, " ").trim());
    for (const f of s.fills)
        if (f.kind === "image" && f.imageRef)
            out.add("i:" + f.imageRef);
    s.children.forEach((c) => signature(c, out));
    return out;
}
const sigCache = new WeakMap();
function sig(s) {
    let found = sigCache.get(s);
    if (!found)
        sigCache.set(s, (found = signature(s)));
    return found;
}
/** How likely two layers from different frames are the same layer, 0..1. */
export function similarity(a, b) {
    if (a.kind !== b.kind && (a.kind === "text" || b.kind === "text" || a.kind === "image" || b.kind === "image"))
        return 0;
    const sa = sig(a), sb = sig(b);
    if (sa.size || sb.size) {
        let common = 0;
        for (const x of sa)
            if (sb.has(x))
                common++;
        const jaccard = common / (sa.size + sb.size - common || 1);
        return jaccard + (a.name.toLowerCase() === b.name.toLowerCase() ? 0.1 : 0);
    }
    if (a.name.toLowerCase() === b.name.toLowerCase())
        return 0.8;
    return a.kind === b.kind ? 0.4 : 0;
}
/** Align children of the same layer in each frame into rows: one row per layer of the merged page. */
function alignChildren(parents) {
    const width = parents.length;
    const rows = [];
    parents.forEach((parent, i) => {
        let last = -1;
        for (const child of parent?.children ?? []) {
            let best = -1, bestScore = 0.34;
            rows.forEach((row, r) => {
                if (row[i])
                    return;
                const score = Math.max(...row.map((m) => (m ? similarity(m, child) : 0))) - (r < last ? 0.05 : 0);
                if (score > bestScore) {
                    best = r;
                    bestScore = score;
                }
            });
            if (best >= 0) {
                rows[best][i] = child;
                last = best;
            }
            else {
                const row = Array.from({ length: width }, () => null);
                row[i] = child;
                rows.splice(last + 1, 0, row);
                last += 1;
            }
        }
    });
    return rows;
}
function mergeNode(versions, names) {
    const present = versions;
    const first = present.find((v) => !!v);
    const values = {};
    let previous = {};
    present.forEach((v, i) => {
        if (!v)
            return;
        const now = flat(v);
        const diff = {};
        for (const [k, val] of Object.entries(now))
            if (JSON.stringify(val) !== JSON.stringify(previous[k]))
                diff[k] = val;
        if (Object.keys(diff).length)
            values[names[i]] = diff;
        previous = { ...previous, ...now };
    });
    const hiddenAt = names.filter((_, i) => !present[i]);
    const notes = [...new Set(present.flatMap((v) => v?.notes ?? []))];
    const rows = alignChildren(present);
    const frames = present.filter(Boolean).length;
    // Rows found in only one of several frames mean the frames nest this layer differently.
    const lonely = rows.filter((row) => row.filter(Boolean).length === 1).length;
    if (frames > 1 && rows.length > 1 && lonely / rows.length > 0.3) {
        const restructured = {};
        present.forEach((v, i) => { if (v)
            restructured[names[i]] = v; });
        return { id: first.id, name: first.name, kind: first.kind, values, hiddenAt, children: [], notes, restructured };
    }
    const children = rows.map((row) => mergeNode(row, names));
    return { id: first.id, name: first.name, kind: first.kind, values, hiddenAt, children, notes };
}
export function merge(frames) {
    const sorted = [...frames].sort((a, b) => a.width - b.width);
    const names = breakpoints(sorted.map((f) => f.width));
    // Frames have different names ("Mobile version", "portfolio-landing page"): merge their contents.
    const roots = sorted.map((f) => ({ ...f.spec, name: "page" }));
    const root = mergeNode(roots, names);
    return { breakpoints: sorted.map((f, i) => ({ name: names[i], width: f.width })), root };
}
// ---------------------------------------------------------------- the spec Claude reads
const SHOW = ["dir", "gap", "wrap", "justify", "align", "pad", "width", "height", "grow", "stretch", "fill", "border", "radius", "shadow", "font", "size", "lineHeight", "trim", "tracking", "case", "textAlign", "color"];
function describe(m, bps) {
    const parts = [];
    const base = m.values.base ?? m.values[bps.find((b) => m.values[b]) ?? "base"] ?? {};
    for (const key of SHOW) {
        const steps = bps.filter((b) => m.values[b] && key in m.values[b]).map((b) => [b, m.values[b][key]]);
        if (!steps.length)
            continue;
        const shown = steps.filter(([, v]) => v !== null && v !== false && v !== 0 && v !== "0 0 0 0" && v !== "" && v !== "none" && v !== "start" || steps.length > 1);
        if (!shown.length)
            continue;
        const fmt = (v) => (typeof v === "string" ? v : JSON.stringify(v));
        parts.push(steps.length === 1 && steps[0][0] === "base" ? `${key} ${fmt(steps[0][1])}` : `${key} ${steps.map(([b, v]) => `${b === "base" ? "" : b + ":"}${fmt(v)}`).join(" → ")}`);
    }
    void base;
    return parts.join(" · ");
}
export function specMarkdown(merged, title) {
    const bps = merged.breakpoints.map((b) => b.name);
    const lines = [
        `# ${title}`,
        "",
        `Breakpoints (mobile first): ${merged.breakpoints.map((b) => `${b.name} = ${b.width}px frame`).join(", ")}.`,
        "Each line: the layer, then its properties; `a → md:b → xl:c` means the value changes at that breakpoint.",
        "Sizes: fill = takes the free space (flex-1 / w-full), hug = fits its content, NNpx = fixed in the design.",
        "",
    ];
    const single = (s, depth) => {
        const pad = "  ".repeat(depth);
        const one = { id: s.id, name: s.name, kind: s.kind, values: { base: flat(s) }, hiddenAt: [], children: [], notes: s.notes };
        const label = s.kind === "text" ? `text ${JSON.stringify(s.text?.content)}` : `${s.kind} "${s.name}"`;
        lines.push(`${pad}- ${label} · ${describe(one, ["base"])}`.replace(/ · $/, ""));
        for (const n of s.notes)
            lines.push(`${pad}  > ${n}`);
        if (s.kind !== "vector")
            s.children.forEach((c) => single(c, depth + 1));
    };
    const walk = (m, depth) => {
        const pad = "  ".repeat(depth);
        const content = m.values.base?.content ?? Object.values(m.values).find((v) => v.content)?.content;
        const label = m.kind === "text" ? `text ${JSON.stringify(content)}` : `${m.kind} "${m.name}"`;
        const hidden = m.hiddenAt.length ? ` · HIDDEN at ${m.hiddenAt.join(", ")}` : "";
        if (m.restructured) {
            lines.push(`${pad}- ${label}${hidden} · RESTRUCTURED between frames: each width's own layers follow; build one responsive layout that gives each of them`);
            for (const [bp, s] of Object.entries(m.restructured)) {
                lines.push(`${pad}  - at ${bp}:`);
                single(s, depth + 2);
            }
            return;
        }
        lines.push(`${pad}- ${label}${hidden} · ${describe(m, bps)}`.replace(/ · $/, ""));
        for (const n of m.notes)
            lines.push(`${pad}  > ${n}`);
        if (m.kind !== "vector")
            m.children.forEach((c) => walk(c, depth + 1));
    };
    walk(merged.root, 0);
    return lines.join("\n") + "\n";
}
