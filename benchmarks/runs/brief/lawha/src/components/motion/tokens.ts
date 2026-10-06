/**
 * lawha recipe: the motion personality of the chosen direction, read from the theme.
 *
 * `lawha direct choose` writes --lawha-motion (calm | lively | precise), --lawha-ease and the
 * durations into :root; every recipe takes its timing from here, so the whole app moves alike.
 */
import { type Transition, useReducedMotion } from "motion/react";
import { useMemo } from "react";

export type Personality = "calm" | "lively" | "precise";

export interface MotionTokens {
  personality: Personality;
  ease: [number, number, number, number];
  fast: number; // seconds
  base: number;
  slow: number;
  distance: number; // px an entrance travels
  rtl: boolean;
  reduce: boolean;
}

const DEFAULTS = { calm: [0.22, 1, 0.36, 1], lively: [0.34, 1.56, 0.64, 1], precise: [0.2, 0, 0, 1] } as const;

function cssVar(name: string): string {
  if (typeof document === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function bezier(value: string, fallback: readonly number[]): [number, number, number, number] {
  const n = value.match(/-?[\d.]+/g)?.map(Number);
  return (n && n.length === 4 ? n : [...fallback]) as [number, number, number, number];
}

export function readTokens(): Omit<MotionTokens, "reduce"> {
  const p = cssVar("--lawha-motion");
  const personality: Personality = p === "lively" || p === "precise" ? p : "calm";
  const ms = (name: string, fallback: number) => (Number(cssVar(name)) || fallback) / 1000;
  return {
    personality,
    ease: bezier(cssVar("--lawha-ease"), DEFAULTS[personality]),
    fast: ms("--lawha-fast", 220),
    base: ms("--lawha-base", 420),
    slow: ms("--lawha-slow", 700),
    distance: Number(cssVar("--lawha-distance")) || 10,
    rtl: typeof document !== "undefined" && document.documentElement.dir === "rtl",
  };
}

/** Read once per component and kept stable, so effects that depend on the tokens do not restart. */
export function useMotionTokens(): MotionTokens {
  const reduce = useReducedMotion() ?? false;
  const tokens = useMemo(readTokens, []);
  return useMemo(() => ({ ...tokens, reduce }), [tokens, reduce]);
}

/** The transition for a given speed: a soft spring for "lively", a tuned curve otherwise. */
export function transition(t: MotionTokens, speed: "fast" | "base" | "slow" = "base"): Transition {
  if (t.reduce) return { duration: 0 };
  if (t.personality === "lively") return { type: "spring", bounce: 0.32, duration: t[speed] * 1.2 };
  return { duration: t[speed], ease: t.ease };
}

/** A distance along the reading direction: +x is "towards the end of the line" in LTR and RTL. */
export function inline(t: MotionTokens, px: number): number {
  return t.rtl ? -px : px;
}
