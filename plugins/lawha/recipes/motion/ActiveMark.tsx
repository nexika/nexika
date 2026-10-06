/**
 * lawha recipe: the mark under the active tab or nav item glides to the new one (shared layout).
 *
 *   {items.map((i) => (
 *     <a key={i.to} className="relative" aria-current={active ? "page" : undefined}>
 *       {i.label}
 *       {active && <ActiveMark group="nav" className="absolute inset-x-2 bottom-1 h-[3px] rounded-full bg-accent" />}
 *     </a>
 *   ))}
 *
 * Reduced motion: the mark jumps. `group` keeps several tab bars on one page apart.
 */
import { motion } from "motion/react";
import { transition, useMotionTokens } from "./tokens";

export function ActiveMark({ group, className }: { group: string; className?: string }) {
  const t = useMotionTokens();
  return <motion.span aria-hidden="true" layoutId={t.reduce ? undefined : `lawha-mark-${group}`} className={className} transition={transition(t, "base")} />;
}
