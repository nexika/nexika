// lawha's Figma reading, offline: a synthetic file in Figma's REST format with the habits found in
// real community designs (fake gaps, padding that centres, vertical trim, style overrides, typed
// line breaks, icons as groups, layers renamed between frames).
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { breakpoints, merge, specMarkdown } from "../dist/merge.js";
import { normalize, tokens, typeStyles } from "../dist/normalize.js";
import { parseUrl } from "../dist/figma.js";

const black = { r: 0, g: 0, b: 0, a: 1 };
const peach = { r: 0.976, g: 0.859, b: 0.757, a: 1 };
const box = (x, y, width, height) => ({ x, y, width, height });
const styles = { "1:1": { name: "Background/Color 1", styleType: "FILL" }, "1:2": { name: "Text/Headings", styleType: "FILL" } };

function text(id, characters, extra = {}, at = box(0, 0, 100, 20)) {
  return { id, name: characters.slice(0, 20), type: "TEXT", characters, absoluteBoundingBox: at,
    fills: [{ type: "SOLID", color: black }], styles: { fill: "1:2" },
    style: { fontFamily: "Poppins", fontWeight: 400, fontSize: 16, lineHeightPx: 24, lineHeightUnit: "INTRINSIC_%", textAutoResize: "WIDTH_AND_HEIGHT", ...extra.style },
    ...extra.node };
}

const icon = { id: "9:1", name: "mi:email", type: "GROUP", absoluteBoundingBox: box(0, 0, 28, 28),
  children: [{ id: "9:2", name: "Vector", type: "VECTOR", absoluteBoundingBox: box(2, 4, 24, 20), fills: [{ type: "SOLID", color: black }] }] };

function desktop() {
  return { id: "2:1", name: "portfolio-landing page", type: "FRAME", layoutMode: "VERTICAL", absoluteBoundingBox: box(0, 0, 1440, 900),
    layoutSizingHorizontal: "FIXED", layoutSizingVertical: "HUG", fills: [{ type: "SOLID", color: { r: 1, g: 1, b: 1, a: 1 } }],
    children: [
      { id: "2:2", name: "Header", type: "FRAME", layoutMode: "HORIZONTAL", primaryAxisAlignItems: "SPACE_BETWEEN", counterAxisAlignItems: "CENTER",
        itemSpacing: 796, paddingLeft: 100, paddingRight: 100, absoluteBoundingBox: box(0, 0, 1440, 111), layoutSizingHorizontal: "FILL",
        fills: [{ type: "SOLID", color: peach }], styles: { fill: "1:1" },
        strokes: [{ type: "SOLID", color: black }], strokeWeight: 2, individualStrokeWeights: { top: 0, right: 0, bottom: 2, left: 0 },
        children: [
          text("2:3", "Bernard Smith", { style: { fontWeight: 600, fontSize: 24, leadingTrim: "CAP_HEIGHT" } }),
          text("2:4", "Book Consultation", { style: { fontWeight: 400 }, node: { characterStyleOverrides: [1, 1, 1, 1, 1, 0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2], styleOverrideTable: { 1: { fontWeight: 500 }, 2: { fontWeight: 700 } } } }),
        ] },
      { id: "2:5", name: "Introduction", type: "FRAME", layoutMode: "HORIZONTAL", absoluteBoundingBox: box(0, 111, 1440, 600), children: [
        text("2:6", "Hey, I’m Bernard Smith", { style: { fontSize: 64, fontWeight: 500, lineHeightPx: 72, lineHeightUnit: "PIXELS" } }),
        { id: "2:7", name: "image", type: "RECTANGLE", absoluteBoundingBox: box(720, 111, 720, 600), fills: [{ type: "IMAGE", imageRef: "abc123", scaleMode: "FILL" }] },
      ] },
      { id: "2:8", name: "contact", type: "FRAME", layoutMode: "HORIZONTAL", absoluteBoundingBox: box(0, 711, 1440, 80), children: [
        { ...icon },
        text("2:9", "Email", { style: { fontFamily: "Inter", fontWeight: 600, fontSize: 20 } }),
      ] },
      { id: "2:10", name: "footer_12", type: "FRAME", layoutMode: "VERTICAL", paddingLeft: 565, paddingRight: 566, absoluteBoundingBox: box(0, 791, 1440, 71),
        children: [text("2:11", "© 2024 Bernard Smith.", {}, box(565, 806, 309, 26))] },
    ] };
}

function mobile() {
  return { id: "3:1", name: "Mobile version", type: "FRAME", layoutMode: "VERTICAL", absoluteBoundingBox: box(0, 0, 387, 1400),
    layoutSizingHorizontal: "FIXED", children: [
      { id: "3:2", name: "navbar", type: "FRAME", layoutMode: "HORIZONTAL", primaryAxisAlignItems: "SPACE_BETWEEN", itemSpacing: 206, absoluteBoundingBox: box(0, 0, 387, 73),
        fills: [{ type: "SOLID", color: peach }], styles: { fill: "1:1" }, children: [
          text("3:3", "Bernard Smith", { style: { fontWeight: 600, fontSize: 16, leadingTrim: "CAP_HEIGHT" } }),
          text("3:4", "Book Consultation", { style: { fontWeight: 500 } }),
        ] },
      { id: "3:5", name: "header", type: "FRAME", layoutMode: "VERTICAL", absoluteBoundingBox: box(0, 73, 387, 900), children: [
        text("3:6", "Hey, I’m Bernard Smith", { style: { fontSize: 32, fontWeight: 500, lineHeightPx: 40, lineHeightUnit: "PIXELS" } }),
        { id: "3:7", name: "image", type: "RECTANGLE", absoluteBoundingBox: box(16, 200, 355, 530), fills: [{ type: "IMAGE", imageRef: "abc123", scaleMode: "FILL" }] },
      ] },
      { id: "3:8", name: "contact", type: "FRAME", layoutMode: "VERTICAL", absoluteBoundingBox: box(0, 973, 387, 300), children: [
        { ...icon, id: "9:3" },
        text("3:9", "Email", { style: { fontFamily: "Inter", fontWeight: 600, fontSize: 16 } }),
      ] },
      { id: "3:10", name: "footer_12", type: "FRAME", layoutMode: "VERTICAL", absoluteBoundingBox: box(0, 1273, 387, 74),
        children: [text("3:11", "© 2024 Bernard Smith.", {}, box(77, 1290, 233, 26))] },
    ] };
}

const walk = (s, fn) => { fn(s); s.children.forEach((c) => walk(c, fn)); };
const find = (s, pred) => { let hit = null; walk(s, (x) => { if (!hit && pred(x)) hit = x; }); return hit; };

test("Figma links give the file key and the selected node", () => {
  assert.deepEqual(parseUrl("https://www.figma.com/design/g0D3oiWr0m1oipQbsihyEZ/Name?node-id=25-108&t=x"), { key: "g0D3oiWr0m1oipQbsihyEZ", node: "25:108" });
  assert.deepEqual(parseUrl("https://www.figma.com/file/AbCdEfGhIjKl/x"), { key: "AbCdEfGhIjKl", node: null });
  assert.throws(() => parseUrl("https://example.com/design/x"));
});

test("design-file habits are read as intent", () => {
  const s = normalize(desktop(), styles);
  const header = find(s, (x) => x.name === "Header");
  assert.equal(header.layout.justify, "between");
  assert.equal(header.layout.gap, null, "a 796px space-between gap is leftover space");
  assert.ok(header.notes.some((n) => n.includes("796")));
  const footer = find(s, (x) => x.name === "footer_12");
  assert.equal(footer.layout.align, "center");
  assert.deepEqual(footer.layout.pad, [0, 0, 0, 0], "padding that only centres becomes centring");
});

test("text keeps its real line height, vertical trim, overrides and typed line breaks", () => {
  const d = normalize(desktop(), styles);
  const name = find(d, (x) => x.text?.content === "Bernard Smith");
  assert.equal(name.text.trim, true, "leadingTrim CAP_HEIGHT is vertical trim");
  assert.equal(name.text.lineHeight, 24, "an 'auto' line height keeps Figma's rendered value");
  const button = find(d, (x) => x.text?.content === "Book Consultation");
  assert.equal(button.text.weight, 700, "the override covering most characters is the text's style");
  assert.ok(button.notes.some((n) => n.includes('"Book "') && n.includes("500")), "smaller overrides are reported");
  const title = find(normalize(mobile(), styles), (x) => x.kind === "text" && x.text.content.startsWith("Hey"));
  assert.equal(title.text.content, "Hey, I’m\nBernard Smith", "U+2028 is a line break");
});

test("icons drawn as groups of vectors are icons, photos are images, styles are tokens", () => {
  const d = normalize(desktop(), styles);
  assert.equal(find(d, (x) => x.name === "mi:email").kind, "vector");
  assert.equal(find(d, (x) => x.name === "image").kind, "image");
  const t = tokens([d]);
  assert.equal(t.colors["background-color-1"], "#F9DBC1");
  assert.equal(t.colors["text-headings"], "#000000");
  const families = new Set(typeStyles([d]).map((s) => s.family));
  assert.deepEqual(families, new Set(["Poppins", "Inter"]));
  const header = find(d, (x) => x.name === "Header");
  assert.deepEqual(header.border.width, [0, 0, 2, 0], "per-side strokes are kept");
});

test("breakpoints start where each frame's own layout should start", () => {
  assert.deepEqual(breakpoints([387, 1024, 1440]), ["base", "md", "xl"]);
  assert.deepEqual(breakpoints([375, 1440]), ["base", "lg"]);
  assert.deepEqual(breakpoints([390, 834, 1280]), ["base", "md", "lg"]);
});

test("frames are merged by what layers contain, not by their names", () => {
  const merged = merge([{ width: 1440, spec: normalize(desktop(), styles) }, { width: 387, spec: normalize(mobile(), styles) }]);
  assert.deepEqual(merged.breakpoints.map((b) => b.name), ["base", "lg"]);
  const nav = merged.root.children[0];
  assert.deepEqual(nav.hiddenAt, [], "'navbar' (mobile) and 'Header' (desktop) are the same layer");
  const name = nav.children.find((c) => c.kind === "text" && Object.values(c.values).some((v) => v.content === "Bernard Smith"));
  assert.equal(name.values.base.size, 16);
  assert.equal(name.values.lg.size, 24, "the size change becomes a breakpoint value");
  const md = specMarkdown(merged, "Test");
  assert.match(md, /size 16 → lg:24/);
  assert.match(md, /trim cap/);
  assert.match(md, /leftover space/);
});

test("colour styles keep their opacity, and a base style outweighed by a longer run is still listed", () => {
  const grey = { id: "8:1", name: "Card", type: "FRAME", absoluteBoundingBox: box(0, 0, 100, 40), fills: [{ type: "SOLID", color: { r: 0.098, g: 0.094, b: 0.145, a: 1 }, opacity: 0.5 }], styles: { fill: "S:grey50" }, children: [] };
  const t = tokens([normalize(grey, { "S:grey50": { name: "Grey/50", styleType: "FILL" } })]);
  assert.equal(t.colors["grey-50"], "#19182580");
  const name = {
    id: "8:2", name: "Name", type: "TEXT", characters: "Mark Smith / Travel Enthusiast", absoluteBoundingBox: box(0, 0, 400, 34),
    style: { fontFamily: "Circular Std", fontWeight: 700, fontSize: 28, lineHeightPx: 34 },
    characterStyleOverrides: [...Array(10).fill(0), ...Array(20).fill(7)], styleOverrideTable: { 7: { fontSize: 23, fontWeight: 400 } },
  };
  const spec = normalize(name, {});
  assert.equal(spec.text.size, 23, "the longer run is the main style");
  assert.ok(spec.notes.some((n) => n.startsWith('"Mark Smith" is styled differently (weight 700, 28px)')), spec.notes.join(" | "));
});
