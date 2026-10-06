/**
 * lawha recipe: hover and press feedback that says "this is clickable".
 *
 *   <motion.button {...usePress()}>Save</motion.button>
 *   <motion.a {...usePress("lift")} href="…">A card</motion.a>
 *
 * "press" (buttons): a slight squeeze when pressed. "lift" (cards): rises 2px on hover, settles when
 * pressed. Pointer hover only (no sticky hover on touch); keyboard focus keeps the focus ring.
 * Reduced motion: no movement; style the hover with colour instead.
 */
import type { MotionProps } from "motion/react";
import { transition, useMotionTokens } from "./tokens";

export function usePress(kind: "press" | "lift" = "press"): Pick<MotionProps, "whileHover" | "whileTap" | "transition"> {
  const t = useMotionTokens();
  if (t.reduce) return {};
  return kind === "lift"
    ? { whileHover: { y: -2 }, whileTap: { y: 0, scale: 0.99 }, transition: transition(t, "fast") }
    : { whileTap: { scale: 0.97 }, transition: transition(t, "fast") };
}
