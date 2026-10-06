/**
 * From Figma's layer tree to a clean design spec Claude can build from.
 *
 * Auto Layout becomes flex (direction, gap, padding, alignment, wrap), FILL / HUG / FIXED become
 * sizing rules, named colour styles become tokens, text keeps its content and type. Design-file
 * habits are read as what the designer meant, and every such reading is listed in `notes`:
 *   - space-between with a large fixed gap: the gap is only what was left over, so it is dropped;
 *   - padding that only centres a fixed child (a footer "centred" with 565px of left padding):
 *     centring, not padding.
 */
const hex2 = (n) => Math.round(n * 255).toString(16).padStart(2, "0");
export function toHex(c) {
    return `#${hex2(c.r)}${hex2(c.g)}${hex2(c.b)}`.toUpperCase();
}
/** "Background/Color 1" -> "background-color-1"; "Text/Headings" -> "text-headings". */
export function tokenName(styleName) {
    return styleName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}
function paints(list, token) {
    const out = [];
    for (const p of list ?? []) {
        if (p.visible === false)
            continue;
        if (p.type === "SOLID" && p.color)
            out.push({ kind: "solid", hex: toHex(p.color), opacity: Math.round(((p.opacity ?? 1) * (p.color.a ?? 1)) * 100) / 100, token });
        else if (p.type === "IMAGE")
            out.push({ kind: "image", imageRef: p.imageRef, scaleMode: p.scaleMode ?? "FILL" });
        else if (p.type.startsWith("GRADIENT") && p.gradientStops) {
            const stops = p.gradientStops.map((s) => `${toHex(s.color)} ${Math.round(s.position * 100)}%`).join(", ");
            out.push({ kind: "gradient", css: `${p.type === "GRADIENT_RADIAL" ? "radial-gradient(circle" : "linear-gradient(180deg"}, ${stops})` });
        }
    }
    return out;
}
const JUSTIFY = { MIN: "start", CENTER: "center", MAX: "end", SPACE_BETWEEN: "between" };
const ALIGN = { MIN: "start", CENTER: "center", MAX: "end", BASELINE: "baseline" };
function size(sizing, px) {
    return { mode: sizing === "FILL" ? "fill" : sizing === "HUG" ? "hug" : "fixed", px: Math.round(px) };
}
function shadowOf(effects) {
    const list = (effects ?? []).filter((e) => e.visible !== false && (e.type === "DROP_SHADOW" || e.type === "INNER_SHADOW") && e.color);
    if (!list.length)
        return null;
    return list
        .map((e) => `${e.type === "INNER_SHADOW" ? "inset " : ""}${e.offset?.x ?? 0}px ${e.offset?.y ?? 0}px ${e.radius ?? 0}px ${e.spread ?? 0}px ${toHex(e.color)}${hex2(e.color.a)}`)
        .join(", ");
}
/**
 * The style most of the text really has. Designers often restyle a text through a character
 * override (all of it bold, say) while the layer's own style says regular: when one override
 * covers most characters, it is the text's style; smaller overrides are reported as mixed runs.
 */
function effectiveStyle(n) {
    const base = n.style ?? {};
    const runs = n.characterStyleOverrides ?? [];
    const table = n.styleOverrideTable ?? {};
    const length = (n.characters ?? "").length;
    if (!runs.length || !length)
        return { style: base, mixed: [] };
    const counts = new Map();
    for (let i = 0; i < length; i++)
        counts.set(runs[i] ?? 0, (counts.get(runs[i] ?? 0) ?? 0) + 1);
    const [top, topCount] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
    const style = top !== 0 && table[String(top)] && topCount / length >= 0.6 ? { ...base, ...table[String(top)] } : base;
    const mixed = [...counts.keys()]
        .filter((id) => id !== 0 && id !== top && table[String(id)])
        .map((id) => {
        const o = table[String(id)];
        const start = runs.indexOf(id);
        let end = start;
        while (runs[end + 1] === id)
            end++;
        const part = (n.characters ?? "").slice(start, end + 1);
        const what = [o.fontWeight && `weight ${o.fontWeight}`, o.fontSize && `${o.fontSize}px`, o.fontFamily, o.textDecoration?.toLowerCase(), o.fills && "own colour"].filter(Boolean).join(", ");
        return `"${part.slice(0, 40)}" is styled differently (${what || "own style"})`;
    });
    return { style, mixed };
}
function textOf(n, styles, notes) {
    const { style: s, mixed } = effectiveStyle(n);
    notes.push(...mixed);
    const fillToken = n.styles?.fill ? styles[n.styles.fill]?.name : undefined;
    const color = paints(s.fills ?? n.fills, fillToken && !s.fills ? tokenName(fillToken) : undefined)[0] ?? null;
    const cases = { UPPER: "upper", LOWER: "lower", TITLE: "title" };
    const aligns = { LEFT: "start", CENTER: "center", RIGHT: "end", JUSTIFIED: "justify" };
    return {
        // U+2028 / U+2029 are line breaks typed in Figma (shift+enter): show them as real line breaks.
        content: (n.characters ?? "").replace(/[\u2028\u2029]/g, "\n").replace(/\r/g, ""),
        family: s.fontFamily ?? "",
        weight: s.fontWeight ?? 400,
        size: Math.round((s.fontSize ?? 16) * 10) / 10,
        // Figma reports the rendered line height even when it is "auto": keep it, or the build falls back
        // to the framework's default leading and every line sits tighter than designed.
        lineHeight: s.lineHeightPx ? Math.round(s.lineHeightPx * 10) / 10 : null,
        letterSpacing: Math.round((s.letterSpacing ?? 0) * 100) / 100,
        transform: cases[s.textCase ?? ""] ?? "none",
        align: aligns[s.textAlignHorizontal ?? "LEFT"] ?? "start",
        color,
        decoration: s.textDecoration === "UNDERLINE" ? "underline" : s.textDecoration === "STRIKETHROUGH" ? "strike" : "none",
        trim: s.leadingTrim === "CAP_HEIGHT",
    };
}
const VECTOR_TYPES = new Set(["VECTOR", "BOOLEAN_OPERATION", "STAR", "LINE", "ELLIPSE", "REGULAR_POLYGON"]);
/** A frame or group made only of vector shapes, no text and no Auto Layout: an icon, exported as SVG. */
function isIcon(n) {
    if (!["FRAME", "GROUP", "INSTANCE", "COMPONENT"].includes(n.type) || !n.children?.length)
        return false;
    if (n.layoutMode === "HORIZONTAL" || n.layoutMode === "VERTICAL")
        return false;
    const b = n.absoluteBoundingBox;
    if (b && (b.width > 96 || b.height > 96))
        return false;
    const leaves = (x) => (x.children?.length ? x.children.every(leaves) : VECTOR_TYPES.has(x.type));
    return n.children.every(leaves);
}
export function normalize(n, styles) {
    if (n.visible === false)
        return null;
    const box = n.absoluteBoundingBox ?? { x: 0, y: 0, width: 0, height: 0 };
    const fillToken = n.styles?.fill ? styles[n.styles.fill]?.name : undefined;
    const strokeToken = n.styles?.stroke ? styles[n.styles.stroke]?.name : undefined;
    const fills = paints(n.fills, fillToken ? tokenName(fillToken) : undefined);
    const isText = n.type === "TEXT";
    const isVector = (["VECTOR", "BOOLEAN_OPERATION", "STAR", "LINE", "ELLIPSE", "REGULAR_POLYGON"].includes(n.type)
        && !(n.type === "ELLIPSE" && fills.some((f) => f.kind === "image"))) || isIcon(n);
    const kind = isText ? "text" : isVector ? "vector" : !n.children?.length && fills.some((f) => f.kind === "image") ? "image" : "box";
    const notes = [];
    let layout = null;
    if (n.layoutMode === "HORIZONTAL" || n.layoutMode === "VERTICAL") {
        const pad = [n.paddingTop ?? 0, n.paddingRight ?? 0, n.paddingBottom ?? 0, n.paddingLeft ?? 0].map(Math.round);
        let justify = JUSTIFY[n.primaryAxisAlignItems ?? "MIN"] ?? "start";
        let gap = Math.round(n.itemSpacing ?? 0);
        if (justify === "between") {
            if (gap > 48)
                notes.push(`gap ${gap}px with space-between is leftover space, not spacing: dropped`);
            gap = null;
        }
        const kids = (n.children ?? []).filter((c) => c.visible !== false && c.layoutPositioning !== "ABSOLUTE");
        // Padding that only centres one fixed child: the designer meant "centred".
        if (kids.length === 1 && n.layoutMode === "VERTICAL") {
            const kid = kids[0].absoluteBoundingBox;
            if (kid && box.width > 0) {
                const left = kid.x - box.x;
                const right = box.x + box.width - (kid.x + kid.width);
                if (Math.abs(left - right) <= 4 && Math.min(left, right) > box.width * 0.15 && (pad[1] > box.width * 0.15 || pad[3] > box.width * 0.15)) {
                    notes.push(`padding ${pad[3]}/${pad[1]}px only centres the content: centred instead`);
                    pad[1] = 0;
                    pad[3] = 0;
                    layout = { dir: "col", gap, rowGap: null, wrap: false, justify, align: "center", pad };
                }
            }
        }
        if (!layout) {
            layout = {
                dir: n.layoutMode === "HORIZONTAL" ? "row" : "col",
                gap,
                rowGap: n.layoutWrap === "WRAP" ? Math.round(n.counterAxisSpacing ?? n.itemSpacing ?? 0) : null,
                wrap: n.layoutWrap === "WRAP",
                justify,
                align: ALIGN[n.counterAxisAlignItems ?? "MIN"] ?? "start",
                pad,
            };
        }
    }
    else if (!isText && !isVector && n.children?.length) {
        layout = { dir: "none", gap: null, rowGap: null, wrap: false, justify: "start", align: "start", pad: [0, 0, 0, 0] };
        notes.push("no Auto Layout: children are placed by position; build it with flex or grid from the picture");
    }
    const strokes = paints(n.strokes, strokeToken ? tokenName(strokeToken) : undefined).filter((p) => p.kind === "solid");
    const w = n.individualStrokeWeights;
    const border = strokes.length && (n.strokeWeight ?? 0) > 0
        ? { width: w ? [w.top, w.right, w.bottom, w.left].map(Math.round) : Math.round((n.strokeWeight ?? 0) * 10) / 10, color: strokes[0], align: (n.strokeAlign ?? "INSIDE").toLowerCase() }
        : null;
    const spec = {
        id: n.id,
        name: n.name,
        kind,
        layout,
        width: size(n.layoutSizingHorizontal, box.width),
        height: size(n.layoutSizingVertical, box.height),
        grow: (n.layoutGrow ?? 0) > 0,
        selfStretch: n.layoutAlign === "STRETCH",
        absolute: n.layoutPositioning === "ABSOLUTE",
        fills: isText ? [] : fills,
        border,
        radius: n.rectangleCornerRadii ? n.rectangleCornerRadii.map(Math.round) : Math.round(n.cornerRadius ?? 0),
        shadow: shadowOf(n.effects),
        opacity: Math.round((n.opacity ?? 1) * 100) / 100,
        clip: !!n.clipsContent,
        text: isText ? textOf(n, styles, notes) : null,
        children: [],
        notes,
    };
    if (!isVector) {
        for (const child of n.children ?? []) {
            const c = normalize(child, styles);
            if (c)
                spec.children.push(c);
        }
    }
    return spec;
}
/** Every colour token used, with its value: from named styles first, then the most used raw colours. */
export function tokens(specs) {
    const colors = {};
    const raw = new Map();
    const visit = (s) => {
        for (const p of [...s.fills, ...(s.text?.color ? [s.text.color] : []), ...(s.border?.color ? [s.border.color] : [])]) {
            if (p.kind !== "solid" || !p.hex)
                continue;
            if (p.token)
                colors[p.token] = p.hex;
            else
                raw.set(p.hex, (raw.get(p.hex) ?? 0) + 1);
        }
        s.children.forEach(visit);
    };
    specs.forEach(visit);
    const named = new Set(Object.values(colors));
    return { colors, untokened: [...raw.entries()].filter(([h]) => !named.has(h)).sort((a, b) => b[1] - a[1]).map(([hex, uses]) => ({ hex, uses })) };
}
/** Distinct text styles (family, weight, size, line height, tracking, case) with how often each is used. */
export function typeStyles(specs) {
    const found = new Map();
    const visit = (s) => {
        if (s.text) {
            const t = s.text;
            const key = [t.family, t.weight, t.size, t.lineHeight, t.letterSpacing, t.transform].join("|");
            const f = found.get(key);
            if (f)
                f.uses++;
            else
                found.set(key, { family: t.family, weight: t.weight, size: t.size, lineHeight: t.lineHeight, letterSpacing: t.letterSpacing, transform: t.transform, uses: 1, sample: t.content.slice(0, 40) });
        }
        s.children.forEach(visit);
    };
    specs.forEach(visit);
    return [...found.values()].sort((a, b) => b.size - a.size || b.weight - a.weight);
}
