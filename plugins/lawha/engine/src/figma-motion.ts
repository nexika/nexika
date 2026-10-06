/**
 * Motion from a Figma prototype. The REST API returns each layer's `interactions`: a trigger (click,
 * hover, press, a timeout...) and actions (go to a frame, change to a variant, open an overlay,
 * scroll to...), each with a transition (dissolve, Smart Animate, move in, slide, push), a duration,
 * an easing (a curve or a spring) and, for slides, a direction.
 *
 * Here they become what Claude builds: a Motion transition, the lawha recipe that fits, the direction
 * written logically (a slide "from the right" in an English design comes from the end of the line, so
 * it mirrors in Arabic), and, when the destination was fetched too, what changes between the two.
 */
import type { Spec } from "./normalize.js";

interface FEasing {
  type: string;
  easingFunctionCubicBezier?: { x1: number; y1: number; x2: number; y2: number };
  easingFunctionSpring?: { mass: number; stiffness: number; damping: number };
}
interface FTransition { type: string; duration?: number; easing?: FEasing; direction?: string; matchLayers?: boolean }
interface FAction { type: string; destinationId?: string | null; navigation?: string; transition?: FTransition | null; url?: string; overlayRelativePosition?: unknown }
interface FTrigger { type: string; delay?: number; timeout?: number; keyCodes?: number[] }
export interface FInteraction { trigger: FTrigger | null; actions?: FAction[] | null }
interface FLayer { id: string; name: string; type: string; children?: FLayer[]; interactions?: FInteraction[] }

/** Figma's named curves (cubic Bézier) and spring presets. A custom curve or spring is read exactly. */
const CURVES: Record<string, [number, number, number, number]> = {
  LINEAR: [0, 0, 1, 1],
  EASE_IN: [0.42, 0, 1, 1],
  EASE_OUT: [0, 0, 0.58, 1],
  EASE_IN_AND_OUT: [0.42, 0, 0.58, 1],
  EASE_IN_BACK: [0.3, -0.05, 0.7, -0.5],
  EASE_OUT_BACK: [0.45, 1.45, 0.8, 1],
  EASE_IN_AND_OUT_BACK: [0.7, -0.4, 0.4, 1.4],
};
const SPRINGS: Record<string, { mass: number; stiffness: number; damping: number }> = {
  GENTLE: { mass: 1, stiffness: 100, damping: 15 },
  QUICK: { mass: 1, stiffness: 300, damping: 20 },
  BOUNCY: { mass: 1, stiffness: 600, damping: 15 },
  SLOW: { mass: 1, stiffness: 80, damping: 20 },
};

const TRIGGERS: Record<string, string> = {
  ON_CLICK: "click", ON_HOVER: "hover (the change stays)", WHILE_HOVERING: "while hovering", MOUSE_ENTER: "pointer enters", MOUSE_LEAVE: "pointer leaves",
  ON_PRESS: "press", WHILE_PRESSING: "while pressing", MOUSE_DOWN: "pointer down", MOUSE_UP: "pointer up", ON_DRAG: "drag",
  AFTER_TIMEOUT: "after a delay", ON_KEY_DOWN: "key press", ON_MEDIA_HIT: "video reaches a time", ON_MEDIA_END: "video ends",
};

export interface MotionStep {
  layer: string;
  id: string;
  trigger: string;
  action: string; // what happens, in words
  destination?: { id: string; name?: string };
  transition: {
    figma: string; // e.g. "SMART_ANIMATE, 300ms, EASE_OUT"
    motion: Record<string, unknown> | null; // a Motion transition object, null for "instant"
    from?: "start" | "end" | "top" | "bottom"; // for slides, written logically
  };
  recipe: string;
  changes: string[]; // what differs between the layer and its destination, when both are known
}

/** Figma documents the duration in seconds in the plugin API; values above 20 are milliseconds. */
function ms(duration: number | undefined): number {
  if (!duration) return 0;
  return Math.round(duration > 20 ? duration : duration * 1000);
}

export function motionTransition(t: FTransition | null | undefined): MotionStep["transition"] {
  if (!t || t.type === "INSTANT") return { figma: "instant", motion: null };
  const duration = ms(t.duration);
  const e = t.easing;
  let motion: Record<string, unknown>;
  let easing = e?.type ?? "EASE_OUT";
  if (e?.type === "CUSTOM_SPRING" && e.easingFunctionSpring) {
    motion = { type: "spring", ...e.easingFunctionSpring };
  } else if (e && SPRINGS[e.type]) {
    motion = { type: "spring", ...SPRINGS[e.type] };
  } else if (e?.type === "CUSTOM_CUBIC_BEZIER" && e.easingFunctionCubicBezier) {
    const b = e.easingFunctionCubicBezier;
    motion = { duration: duration / 1000, ease: [b.x1, b.y1, b.x2, b.y2] };
    easing = `cubic-bezier(${b.x1}, ${b.y1}, ${b.x2}, ${b.y2})`;
  } else {
    motion = { duration: duration / 1000, ease: CURVES[easing] ?? CURVES.EASE_OUT };
  }
  // Figma's LEFT/RIGHT are physical. The designer drew the English (left-to-right) page: "from the
  // right" means from the end of the line, which is the left in Arabic.
  const from = t.direction === "LEFT" ? "end" : t.direction === "RIGHT" ? "start" : t.direction === "TOP" ? "bottom" : t.direction === "BOTTOM" ? "top" : undefined;
  return { figma: [t.type, motion.type === "spring" ? null : `${duration}ms`, easing].filter(Boolean).join(", "), motion, ...(from ? { from } : {}) };
}

/** The lawha recipe (or Motion feature) that builds this kind of interaction. */
function recipeFor(trigger: string, navigation: string | undefined, kind: string): string {
  if (navigation === "OVERLAY") return "Sheet (or a dialog) from recipes/motion, with this transition";
  if (navigation === "SCROLL_TO") return "scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' })";
  if (navigation === "CHANGE_TO" || navigation === "SWAP") {
    if (["WHILE_HOVERING", "ON_HOVER", "MOUSE_ENTER"].includes(trigger)) return "whileHover on a motion element (only the properties that change), or usePress('lift')";
    if (["WHILE_PRESSING", "ON_PRESS", "MOUSE_DOWN"].includes(trigger)) return "whileTap on a motion element, or usePress()";
    return "animate between two states (variants), with layout for size and position";
  }
  if (navigation === "NAVIGATE") {
    if (kind === "SMART_ANIMATE") return "shared layout: give matching layers the same layoutId on both pages; PageTransition for the rest";
    if (kind.startsWith("SLIDE") || kind.startsWith("PUSH") || kind.startsWith("MOVE")) return "PageTransition with a slide along the reading direction";
    return "PageTransition (cross-fade)";
  }
  return "Motion (transform and opacity only)";
}

function action(a: FAction, names: Map<string, string>): string {
  const to = a.destinationId ? `"${names.get(a.destinationId) ?? a.destinationId}"` : "";
  switch (a.navigation ?? a.type) {
    case "NAVIGATE": return `goes to ${to}`;
    case "CHANGE_TO": return `changes to the variant ${to}`;
    case "SWAP": return `swaps the overlay for ${to}`;
    case "OVERLAY": return `opens ${to} as an overlay`;
    case "SCROLL_TO": return `scrolls to ${to}`;
    case "BACK": return "goes back";
    case "CLOSE": return "closes the overlay";
    case "URL": return `opens ${a.url ?? "a link"}`;
    default: return (a.navigation ?? a.type).toLowerCase().replace(/_/g, " ");
  }
}

/** What differs between two normalised layers: the properties a hover or variant change animates. */
export function differences(a: Spec, b: Spec): string[] {
  const out: string[] = [];
  const fill = (s: Spec) => s.fills.map((f) => f.token ?? f.hex ?? f.kind).join(" + ");
  if (fill(a) !== fill(b)) out.push(`fill ${fill(a) || "none"} → ${fill(b) || "none"}`);
  if (a.opacity !== b.opacity) out.push(`opacity ${a.opacity} → ${b.opacity}`);
  if (JSON.stringify(a.radius) !== JSON.stringify(b.radius)) out.push(`radius ${JSON.stringify(a.radius)} → ${JSON.stringify(b.radius)}`);
  if (a.shadow !== b.shadow) out.push(`shadow ${a.shadow ?? "none"} → ${b.shadow ?? "none"}`);
  if (a.width.px !== b.width.px) out.push(`width ${a.width.px}px → ${b.width.px}px`);
  if (a.height.px !== b.height.px) out.push(`height ${a.height.px}px → ${b.height.px}px`);
  const bc = (s: Spec) => (s.border?.color ? s.border.color.token ?? s.border.color.hex ?? "" : "");
  if (bc(a) !== bc(b)) out.push(`border ${bc(a) || "none"} → ${bc(b) || "none"}`);
  if (a.text && b.text && a.text.content !== b.text.content) out.push(`text "${a.text.content.slice(0, 30)}" → "${b.text.content.slice(0, 30)}"`);
  return out;
}

/**
 * Every interaction under a frame. `specs` maps node ids to normalised layers (the fetched frames and
 * any destinations fetched with them), so changes can be listed.
 */
export function extractMotion(root: FLayer, names: Map<string, string>, specs: Map<string, Spec>): MotionStep[] {
  const out: MotionStep[] = [];
  const walk = (n: FLayer) => {
    for (const i of n.interactions ?? []) {
      const trigger = i.trigger?.type ?? "ON_CLICK";
      for (const a of i.actions ?? []) {
        if (!a) continue;
        const t = motionTransition(a.transition);
        const kind = a.transition?.type ?? "INSTANT";
        const from = specs.get(n.id), to = a.destinationId ? specs.get(a.destinationId) : undefined;
        out.push({
          layer: n.name,
          id: n.id,
          trigger: `${TRIGGERS[trigger] ?? trigger.toLowerCase()}${i.trigger?.timeout ? ` (${ms(i.trigger.timeout)}ms)` : ""}${i.trigger?.delay ? ` after ${ms(i.trigger.delay)}ms` : ""}`,
          action: action(a, names),
          ...(a.destinationId ? { destination: { id: a.destinationId, name: names.get(a.destinationId) } } : {}),
          transition: t,
          recipe: recipeFor(trigger, a.navigation, kind),
          changes: from && to ? differences(from, to) : [],
        });
      }
    }
    for (const c of n.children ?? []) walk(c);
  };
  walk(root);
  return out;
}

/** Every layer's id and name in a fetched tree, to name destinations. */
export function layerNames(root: FLayer, into = new Map<string, string>()): Map<string, string> {
  into.set(root.id, root.name);
  for (const c of root.children ?? []) layerNames(c, into);
  return into;
}

/** A transition as it is written in code: { type: "spring", stiffness: 100 } and [0.22, 1, 0.36, 1]. */
function literal(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(literal).join(", ")}]`;
  if (v && typeof v === "object") return `{ ${Object.entries(v).map(([k, x]) => `${k}: ${literal(x)}`).join(", ")} }`;
  return JSON.stringify(v);
}

export function motionMarkdown(steps: MotionStep[], unresolved: number): string {
  if (!steps.length) return "\n## Motion\n\nThis design has no prototype interactions. Use lawha's motion recipes with the direction's timing.\n";
  const lines = ["", "## Motion (from the Figma prototype)", "",
    "Each line: the layer, what triggers it, what happens, the transition as Figma has it, then the Motion transition to use and the recipe.",
    "Directions are logical: `from end` is from the right in English and from the left in Arabic. Under reduced motion, change state without moving (`MotionConfig reducedMotion=\"user\"`).", ""];
  for (const s of steps) {
    const motion = s.transition.motion ? `\`transition={${literal(s.transition.motion)}}\`` : "no animation";
    lines.push(`- **${s.layer}**: on ${s.trigger}, ${s.action}. Figma: ${s.transition.figma}${s.transition.from ? `, from ${s.transition.from}` : ""}. Motion: ${motion}. Build with: ${s.recipe}.`);
    for (const c of s.changes) lines.push(`  - ${c}`);
  }
  if (unresolved) lines.push("", `${unresolved} destination(s) were not fetched, so what changes there is not listed: open them in Figma, or add their ids to the spec command.`);
  return lines.join("\n") + "\n";
}
