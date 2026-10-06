/**
 * lawha recipe: the direction's signature movement, one per page. Each direction has a `motif`
 * (`.lawha/design.json`); use the matching component once, on the thing that matters most.
 *
 *   underline  <Underline>the concept to review</Underline>       a highlight draws under the words
 *   rule       <Rule />                                            a line draws across a section's top
 *   cells      <Cells value={3} total={5} label="3 of 5 known" />  cells fill one by one
 *   dots       <Dots value={4} total={7} label="4 of 7 done" />    dots appear and settle
 *   stamp      <Stamp>Reviewed</Stamp>                             a label lands like a stamp
 *   outline    <Outline>…</Outline>                                a frame traces around a block
 *
 * All draw once, from where reading starts (the right in Arabic). Reduced motion: drawn at once.
 */
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { transition, useMotionTokens } from "./tokens";

const view = { once: true, margin: "0px 0px -10% 0px" } as const;

export function Underline({ children, className = "bg-accent/70" }: { children: ReactNode; className?: string }) {
  const t = useMotionTokens();
  return (
    <span className="relative inline-block">
      <bdi className="relative z-10">{children}</bdi>
      <motion.span
        aria-hidden="true"
        className={`absolute inset-x-0 bottom-[0.08em] z-0 h-[0.32em] rounded-[2px] ${className}`}
        style={{ transformOrigin: t.rtl ? "right" : "left" }}
        initial={t.reduce ? false : { scaleX: 0 }}
        whileInView={{ scaleX: 1 }}
        viewport={view}
        transition={{ ...transition(t, "slow"), delay: t.reduce ? 0 : 0.3 }}
      />
    </span>
  );
}

export function Rule({ className = "h-0.5 bg-accent" }: { className?: string }) {
  const t = useMotionTokens();
  return (
    <motion.div
      aria-hidden="true"
      className={className}
      style={{ transformOrigin: t.rtl ? "right" : "left" }}
      initial={t.reduce ? false : { scaleX: 0 }}
      whileInView={{ scaleX: 1 }}
      viewport={view}
      transition={transition(t, "slow")}
    />
  );
}

export function Cells({ value, total, label, className = "h-2.5 w-5 rounded-[2px]" }: { value: number; total: number; label: string; className?: string }) {
  const t = useMotionTokens();
  return (
    <motion.span role="img" aria-label={label} className="inline-flex gap-1" initial={t.reduce ? false : "hidden"} whileInView="shown" viewport={view}
      variants={{ hidden: {}, shown: { transition: { staggerChildren: t.reduce ? 0 : 0.07 } } }}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={`relative overflow-hidden bg-muted-foreground/20 ${className}`}>
          {i < value && (
            <motion.span className="absolute inset-0 bg-primary" style={{ transformOrigin: t.rtl ? "right" : "left" }}
              variants={{ hidden: { scaleX: 0 }, shown: { scaleX: 1, transition: transition(t, "fast") } }} />
          )}
        </span>
      ))}
    </motion.span>
  );
}

export function Dots({ value, total, label, className = "size-2 rounded-full" }: { value: number; total: number; label: string; className?: string }) {
  const t = useMotionTokens();
  return (
    <motion.span role="img" aria-label={label} className="inline-flex items-center gap-1.5" initial={t.reduce ? false : "hidden"} whileInView="shown" viewport={view}
      variants={{ hidden: {}, shown: { transition: { staggerChildren: t.reduce ? 0 : 0.06 } } }}>
      {Array.from({ length: total }, (_, i) => (
        <motion.span key={i} className={`${className} ${i < value ? "bg-primary" : "bg-muted-foreground/25"}`}
          variants={{ hidden: { opacity: 0, scale: 0.4 }, shown: { opacity: 1, scale: 1, transition: { type: "spring", bounce: 0.45, duration: t.base } } }} />
      ))}
    </motion.span>
  );
}

export function Stamp({ children, className = "inline-block rounded-[3px] border-2 border-current px-2 py-0.5 text-xs font-bold tracking-wider uppercase text-primary" }: { children: ReactNode; className?: string }) {
  const t = useMotionTokens();
  return (
    <motion.span className={className}
      initial={t.reduce ? false : { opacity: 0, scale: 1.25, rotate: t.rtl ? 6 : -6 }}
      whileInView={{ opacity: 1, scale: 1, rotate: t.rtl ? 2 : -2 }}
      viewport={view}
      transition={t.reduce ? { duration: 0 } : { type: "spring", bounce: 0.4, duration: t.base }}>
      {children}
    </motion.span>
  );
}

export function Outline({ children, className, stroke = "var(--accent)", radius = 8 }: { children: ReactNode; className?: string; stroke?: string; radius?: number }) {
  const t = useMotionTokens();
  return (
    <div className={`relative ${className ?? ""}`}>
      <svg aria-hidden="true" className="pointer-events-none absolute inset-0 size-full overflow-visible">
        <motion.rect x="1" y="1" rx={radius} style={{ width: "calc(100% - 2px)", height: "calc(100% - 2px)" }} fill="none" stroke={stroke} strokeWidth="2"
          initial={t.reduce ? false : { pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={view} transition={transition(t, "slow")} />
      </svg>
      {children}
    </div>
  );
}
