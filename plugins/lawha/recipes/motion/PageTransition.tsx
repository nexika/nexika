/**
 * lawha recipe: a calm cross-fade between pages, keyed by the route's section.
 *
 *   <PageTransition id={pathname}><Outlet /></PageTransition>
 *
 * Fades and moves a few pixels only: big page slides make people lose their place. Reduced motion:
 * pages swap at once.
 */
import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";
import { transition, useMotionTokens } from "./tokens";

export function PageTransition({ id, children, className }: { id: string; children: ReactNode; className?: string }) {
  const t = useMotionTokens();
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={id}
        className={className}
        initial={t.reduce ? false : { opacity: 0, y: Math.round(t.distance / 2) }}
        animate={{ opacity: 1, y: 0 }}
        exit={t.reduce ? undefined : { opacity: 0, transition: { duration: t.fast * 0.6 } }}
        transition={transition(t, "fast")}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
