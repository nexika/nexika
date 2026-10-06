import { round } from "./util.js";
function collect() {
    const probe = document.createElement("span");
    document.body.appendChild(probe);
    const norm = (value) => {
        probe.style.color = "";
        probe.style.color = value;
        return probe.style.color ? getComputedStyle(probe).color : "";
    };
    const tokens = {};
    const rootStyle = getComputedStyle(document.documentElement);
    for (const sheet of [...document.styleSheets]) {
        let rules;
        try {
            rules = sheet.cssRules;
        }
        catch {
            continue;
        }
        const walk = (list) => {
            for (const rule of [...list]) {
                if (rule instanceof CSSStyleRule) {
                    for (const prop of [...rule.style]) {
                        if (!prop.startsWith("--"))
                            continue;
                        const value = rootStyle.getPropertyValue(prop).trim() || rule.style.getPropertyValue(prop).trim();
                        const color = value && !value.includes("var(") ? norm(value) : "";
                        if (color)
                            tokens[prop] = color;
                    }
                }
                if ("cssRules" in rule && rule.cssRules)
                    walk(rule.cssRules);
            }
        };
        walk(rules);
    }
    const spacingRaw = rootStyle.getPropertyValue("--spacing").trim();
    let spacingBase = null;
    if (spacingRaw) {
        probe.style.width = spacingRaw;
        spacingBase = parseFloat(getComputedStyle(probe).width) || null;
    }
    probe.remove();
    const transparent = (c) => !c || c === "transparent" || /rgba\(.*,\s*0\)$/.test(c);
    const index = new Map();
    const elements = [];
    for (const el of document.body.querySelectorAll("*")) {
        if (["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "BR"].includes(el.tagName))
            continue;
        const s = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        if (s.display === "none" || s.visibility === "hidden" || Number(s.opacity) === 0 || r.width < 1 || r.height < 1)
            continue;
        let parent = -1;
        for (let p = el.parentElement; p; p = p.parentElement) {
            const i = index.get(p);
            if (i !== undefined) {
                parent = i;
                break;
            }
        }
        let bg = "";
        for (let p = el; p; p = p.parentElement) {
            const c = getComputedStyle(p).backgroundColor;
            if (!transparent(c)) {
                bg = c;
                break;
            }
        }
        const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent || "").join("").trim();
        const lh = parseFloat(s.lineHeight);
        index.set(el, elements.length);
        elements.push({
            selector: el.id ? `#${el.id}` : `${el.tagName.toLowerCase()}${el.classList.length ? "." + [...el.classList].slice(0, 2).join(".") : ""}`,
            tag: el.tagName.toLowerCase(),
            box: { x: Math.round(r.x + scrollX), y: Math.round(r.y + scrollY), w: Math.round(r.width), h: Math.round(r.height) },
            parent,
            text: own.length,
            fontSize: parseFloat(s.fontSize),
            lineHeight: Number.isNaN(lh) ? parseFloat(s.fontSize) * 1.2 : lh,
            fontFamily: s.fontFamily.split(",")[0].replace(/["']/g, "").trim(),
            fontWeight: s.fontWeight,
            color: s.color,
            background: transparent(s.backgroundColor) ? "" : s.backgroundColor,
            effectiveBackground: bg || "rgb(255, 255, 255)",
            display: s.display,
            label: own.slice(0, 48),
            media: ["IMG", "VIDEO", "CANVAS", "PICTURE"].includes(el.tagName) || (el.tagName === "svg" && r.width * r.height > 2500),
            interactive: el.matches("a[href], button, [role=button], input, select, textarea"),
        });
        if (elements.length >= 3000)
            break;
    }
    return { vw: document.documentElement.clientWidth, vh: innerHeight, elements, tokens, spacingBase };
}
function parseRgb(c) {
    const m = c.match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/);
    return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}
function luminance([r, g, b]) {
    const f = (v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
export function contrast(a, b) {
    const x = parseRgb(a), y = parseRgb(b);
    if (!x || !y)
        return null;
    const [hi, lo] = [luminance(x), luminance(y)].sort((p, q) => q - p);
    return (hi + 0.05) / (lo + 0.05);
}
function hsl([r, g, b]) {
    const [R, G, B] = [r / 255, g / 255, b / 255];
    const max = Math.max(R, G, B), min = Math.min(R, G, B);
    const l = (max + min) / 2;
    if (max === min)
        return { h: 0, s: 0, l };
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    const h = max === R ? (G - B) / d + (G < B ? 6 : 0) : max === G ? (B - R) / d + 2 : (R - G) / d + 4;
    return { h: h * 60, s, l };
}
function hex(c) {
    const rgb = parseRgb(c);
    return rgb ? "#" + rgb.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("") : c;
}
function cluster(values, tolerance) {
    const sorted = [...values].sort((a, b) => a - b);
    const out = [];
    for (const v of sorted) {
        const last = out[out.length - 1];
        if (last && v - last.value <= tolerance) {
            last.sum += v;
            last.count++;
            last.value = last.sum / last.count;
        }
        else
            out.push({ value: v, count: 1, sum: v });
    }
    return out.map(({ value, count }) => ({ value: round(value, 1), count }));
}
function harmonyOf(hues) {
    if (hues.length <= 1)
        return "monochrome";
    const spread = (a, b) => { const d = Math.abs(a - b) % 360; return d > 180 ? 360 - d : d; };
    const max = Math.max(...hues.flatMap((a) => hues.map((b) => spread(a, b))));
    if (max <= 35)
        return "analogous";
    if (hues.length === 2 && max >= 150)
        return "complementary";
    if (hues.length === 3 && hues.every((a) => hues.every((b) => a === b || Math.abs(spread(a, b) - 120) < 30)))
        return "triadic";
    return max >= 150 ? "split / contrasting" : "mixed";
}
export function analyse(raw, variant) {
    const els = raw.elements;
    const blocks = els.filter((e) => e.box.w >= 24 && e.box.h >= 16 && e.box.w < raw.vw - 2 && e.display !== "inline");
    // Alignment: shared left edges are the page's real columns; edges 1-4px apart are near-misses.
    const lefts = blocks.map((e) => e.box.x);
    const columns = cluster(lefts, 0.5).filter((c) => c.count >= 3).map((c) => c.value).slice(0, 12);
    const nearMisses = [];
    const edges = (e) => ({ left: e.box.x, right: e.box.x + e.box.w, top: e.box.y });
    for (let i = 0; i < blocks.length && nearMisses.length < 15; i++) {
        for (let j = i + 1; j < blocks.length; j++) {
            const a = blocks[i], b = blocks[j];
            if (a.parent === j || b.parent === i || a.parent !== b.parent)
                continue;
            const ea = edges(a), eb = edges(b);
            const verticalNeighbours = Math.abs(ea.top - eb.top) > 4;
            for (const edge of ["left", "right"]) {
                const off = Math.abs(ea[edge] - eb[edge]);
                if (verticalNeighbours && off >= 1 && off <= 4) {
                    nearMisses.push({ a: a.selector, b: b.selector, edge, off });
                    break;
                }
            }
        }
    }
    // Rhythm: vertical gaps between stacked siblings, against the spacing base.
    const base = raw.spacingBase ?? 4;
    const stackable = els.filter((e) => e.box.h >= 8 && e.box.w >= 24 && e.display !== "inline");
    const byParent = new Map();
    for (const e of stackable)
        byParent.set(e.parent, [...(byParent.get(e.parent) ?? []), e]);
    const gaps = [];
    const offScale = [];
    const uneven = [];
    for (const [, kids] of byParent) {
        const stacked = kids.sort((a, b) => a.box.y - b.box.y);
        const local = [];
        for (let i = 1; i < stacked.length; i++) {
            const prev = stacked[i - 1], cur = stacked[i];
            const gap = cur.box.y - (prev.box.y + prev.box.h);
            if (gap <= 0 || gap > 400 || Math.abs(cur.box.x - prev.box.x) > 8)
                continue;
            gaps.push(gap);
            local.push(gap);
            const rem = gap % base;
            if (gap > 2 && rem > 0.5 && base - rem > 0.5 && offScale.length < 15)
                offScale.push({ between: `${prev.selector} → ${cur.selector}`, gap });
        }
        if (local.length >= 3 && Math.max(...local) - Math.min(...local) > base && new Set(stacked.map((k) => k.tag)).size === 1) {
            uneven.push({ list: stacked[0].selector, gaps: local });
        }
    }
    // Typography: sizes weighted by text, the scale ratio, families, line length and leading.
    const texty = els.filter((e) => e.text > 0);
    const weight = new Map();
    for (const e of texty)
        weight.set(round(e.fontSize, 1), (weight.get(round(e.fontSize, 1)) ?? 0) + e.text);
    const total = [...weight.values()].reduce((a, b) => a + b, 0) || 1;
    const sizes = [...weight.entries()].sort((a, b) => b[0] - a[0]).map(([px, n]) => ({ px, share: round(n / total, 3) }));
    const distinct = sizes.map((s) => s.px).sort((a, b) => a - b);
    const steps = distinct.slice(1).map((s, i) => s / distinct[i]).filter((r) => r > 1.04);
    const ratio = steps.length ? round(Math.exp(steps.reduce((a, r) => a + Math.log(r), 0) / steps.length), 3) : null;
    const longLines = texty
        .filter((e) => e.text > 120)
        .map((e) => ({ selector: e.selector, chars: Math.round(e.box.w / (e.fontSize * 0.5)) }))
        .filter((l) => l.chars > 85)
        .slice(0, 10);
    const tightLeading = texty
        .filter((e) => e.text > 80 && e.fontSize <= 24)
        .map((e) => ({ selector: e.selector, ratio: round(e.lineHeight / e.fontSize, 2) }))
        .filter((t) => t.ratio < 1.35)
        .slice(0, 10);
    // Colour: area shares of backgrounds and text, harmony, colours outside the tokens, contrast.
    const area = new Map();
    for (const e of els) {
        if (e.background)
            area.set(e.background, (area.get(e.background) ?? 0) + e.box.w * e.box.h);
        if (e.text)
            area.set(e.color, (area.get(e.color) ?? 0) + e.text * e.fontSize * e.fontSize * 0.5);
    }
    const areaTotal = [...area.values()].reduce((a, b) => a + b, 0) || 1;
    const tokenByColour = new Map();
    for (const [name, value] of Object.entries(raw.tokens))
        if (!tokenByColour.has(value))
            tokenByColour.set(value, name);
    const palette = [...area.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10)
        .map(([c, n]) => ({ hex: hex(c), share: round(n / areaTotal, 3), token: tokenByColour.get(c) ?? null }));
    const chromatic = [...area.keys()]
        .map((c) => parseRgb(c))
        .filter((c) => !!c)
        .map(hsl)
        .filter((c) => c.s > 0.2 && c.l > 0.1 && c.l < 0.92);
    const hues = cluster(chromatic.map((c) => c.h), 15).map((h) => h.value);
    const offToken = Object.keys(raw.tokens).length
        ? [...area.keys()].filter((c) => !tokenByColour.has(c)).map(hex).slice(0, 15)
        : [];
    const lowContrast = texty
        .map((e) => {
        const ratioValue = contrast(e.color, e.effectiveBackground);
        const large = e.fontSize >= 24 || (e.fontSize >= 18.66 && Number(e.fontWeight) >= 700);
        return { selector: e.selector, ratio: ratioValue ?? 21, needs: large ? 3 : 4.5 };
    })
        .filter((c) => c.ratio < c.needs)
        .map((c) => ({ ...c, ratio: round(c.ratio, 2) }))
        .slice(0, 15);
    // Visual weight above the fold: big, contrasting, bold or saturated things pull the eye first.
    // A heuristic ranking (not an eye tracker): good enough to say whether the call to action or the
    // logo wins the first glance.
    const fold = raw.vh;
    const weighted = [];
    for (const e of els) {
        if (e.box.y > fold || e.box.y + e.box.h < 0 || e.box.w * e.box.h < 120)
            continue;
        const visibleH = Math.min(e.box.y + e.box.h, fold) - Math.max(e.box.y, 0);
        const area = Math.max(0, visibleH) * e.box.w;
        let weight = 0;
        let kind = "text";
        if (e.media) {
            weight = area * 0.35;
            kind = "media";
        }
        else if (e.text > 0) {
            const c = contrast(e.color, e.effectiveBackground) ?? 4.5;
            weight = e.fontSize ** 2 * Math.sqrt(e.text) * Math.min(c, 12) * (Number(e.fontWeight) / 400) * 0.6;
        }
        if (e.interactive && e.background) {
            const rgbBg = parseRgb(e.background);
            const sat = rgbBg ? hsl(rgbBg).s : 0;
            const c = contrast(e.background, e.effectiveBackground === e.background ? "rgb(255, 255, 255)" : e.effectiveBackground) ?? 1;
            weight = Math.max(weight, area * (0.6 + sat) * Math.min(c, 6) * 0.5);
            kind = "action";
        }
        if (weight > 0)
            weighted.push({ selector: e.selector, label: e.label || e.selector, kind, weight, box: e.box });
    }
    weighted.sort((a, b) => b.weight - a.weight);
    const top = weighted[0]?.weight || 1;
    const focus = weighted.slice(0, 6).map((f) => ({ ...f, weight: round(f.weight / top, 2) }));
    return {
        variant,
        focus,
        alignment: { columns, nearMisses },
        rhythm: { base: raw.spacingBase, gaps: cluster(gaps, 0.5).sort((a, b) => b.count - a.count).slice(0, 10), offScale, uneven: uneven.slice(0, 10) },
        typography: {
            sizes,
            ratio,
            families: [...new Set(texty.map((e) => e.fontFamily))],
            weights: [...new Set(texty.map((e) => e.fontWeight))].sort(),
            longLines,
            tightLeading,
        },
        colour: { palette, harmony: harmonyOf(hues), offToken, lowContrast },
    };
}
export async function see(page, v, name) {
    void v;
    return analyse(await page.evaluate(collect), name);
}
