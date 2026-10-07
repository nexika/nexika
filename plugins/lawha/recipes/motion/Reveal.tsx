/**
 * lawha recipe: entrances in reading order.
 *
 *   <Reveal>…</Reveal>                     one block rises in
 *   <RevealGroup as="ul"> <RevealItem as="li">…</RevealItem> … </RevealGroup>
 *                                           children appear one after another
 *   <Reveal inView>…</Reveal>              waits until it scrolls into view (once)
 *
 * Reduced motion: content is shown at once (no movement, no fade). Only opacity and transform move.
 */
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { transition, useMotionTokens } from "./tokens";

type Tag = "div" | "section" | "ul" | "ol" | "li" | "article" | "header" | "p";

export function Reveal({ children, className, as = "div", inView = false, delay = 0 }: { children: ReactNode; className?: string; as?: Tag; inView?: boolean; delay?: number }) {
  const t = useMotionTokens();
  const M = motion[as];
  const shown = { opacity: 1, y: 0 };
  return (
    <M
      className={className}
      initial={t.reduce ? false : { opacity: 0, y: t.distance }}
      {...(inView ? { whileInView: shown, viewport: { once: true, margin: "0px 0px -10% 0px" } } : { animate: shown })}
      transition={{ ...transition(t, "base"), delay: t.reduce ? 0 : delay }}
    >
      {children}
    </M>
  );
}

export function RevealGroup({ children, className, as = "div", inView = false, gap = 0.06 }: { children: ReactNode; className?: string; as?: Tag; inView?: boolean; gap?: number }) {
  const t = useMotionTokens();
  const M = motion[as];
  const variants = { hidden: {}, shown: { transition: { staggerChildren: t.reduce ? 0 : gap, delayChildren: t.reduce ? 0 : 0.05 } } };
  return (
    <M
      className={className}
      variants={variants}
      initial={t.reduce ? false : "hidden"}
      {...(inView ? { whileInView: "shown", viewport: { once: true, margin: "0px 0px -10% 0px" } } : { animate: "shown" })}
    >
      {children}
    </M>
  );
}

export function RevealItem({ children, className, as = "div" }: { children: ReactNode; className?: string; as?: Tag }) {
  const t = useMotionTokens();
  const M = motion[as];
  return (
    <M
      className={className}
      variants={{ hidden: { opacity: 0, y: t.distance }, shown: { opacity: 1, y: 0, transition: transition(t, "base") } }}
    >
      {children}
    </M>
  );
}
