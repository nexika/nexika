import { animate, motion, useInView, useReducedMotion } from "motion/react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { useT } from "./i18n";
import { type Concept, cn, kind, type Status } from "./lib";

export type Kind = Status | "stale";

const KIND_TEXT: Record<Kind, string> = {
  missed: "text-missed", shaky: "text-shaky", "not-checked": "text-not-checked", understood: "text-understood", stale: "text-stale",
};

/** Each status has its own shape as well as its colour: a cross, a half disc, a ring, a disc, a dashed ring. */
export function StatusMark({ k, className }: { k: Kind; className?: string }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className={cn("size-3.5 shrink-0", KIND_TEXT[k], className)}>
      {k === "missed" && (<><circle cx="8" cy="8" r="7" fill="currentColor" /><path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="var(--background)" strokeWidth="1.8" strokeLinecap="round" /></>)}
      {k === "shaky" && (<><circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.6" /><path d="M8 1.8a6.2 6.2 0 0 1 0 12.4z" fill="currentColor" /></>)}
      {k === "not-checked" && <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.6" />}
      {k === "understood" && <circle cx="8" cy="8" r="7" fill="currentColor" />}
      {k === "stale" && <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.6" strokeDasharray="2.6 2.2" />}
    </svg>
  );
}

export function StatusLabel({ k }: { k: Kind }) {
  const { t } = useT();
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm font-semibold", KIND_TEXT[k])}>
      <StatusMark k={k} />
      {t.status[k]}
    </span>
  );
}

/** The direction's signature: a saffron underline that draws itself under the one thing to look at first. */
export function Underline({ children }: { children: ReactNode }) {
  const { lang } = useT();
  const reduce = useReducedMotion();
  return (
    <span className="relative inline-block whitespace-nowrap">
      <bdi className="relative z-10">{children}</bdi>
      <motion.span
        aria-hidden="true"
        className="absolute inset-x-0 bottom-[0.08em] z-0 h-[0.32em] rounded-[2px] bg-accent/70"
        style={{ transformOrigin: lang === "ar" ? "right" : "left" }}
        initial={reduce ? false : { scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 0.9, delay: 0.35, ease: [0.22, 1, 0.36, 1] }}
      />
    </span>
  );
}

/** A number that counts up once when it scrolls into view (shown at once with reduced motion). */
export function CountUp({ value, className }: { value: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? value : 0);
  useEffect(() => {
    if (reduce || !inView) {
      if (reduce) setShown(value);
      return;
    }
    const controls = animate(0, value, { duration: 0.8, ease: [0.22, 1, 0.36, 1], onUpdate: (v) => setShown(Math.round(v)) });
    return () => controls.stop();
  }, [inView, reduce, value]);
  return <span ref={ref} className={cn("tabular", className)}>{shown}</span>;
}

/** Share of a topic that is known and fresh: a thin bar that fills once, on the paper's ruled line. */
export function Mastery({ value, label }: { value: number; label: string }) {
  const reduce = useReducedMotion();
  const pct = Math.round(value * 100);
  return (
    <div className="grid gap-1.5">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular font-semibold">{pct}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-paper-line" role="img" aria-label={`${pct}% ${label}`}>
        <motion.div
          className="h-full rounded-full bg-primary"
          style={{ width: `${Math.max(pct, 2)}%`, transformOrigin: "var(--origin, left)" }}
          initial={reduce ? false : { scaleX: 0 }}
          whileInView={{ scaleX: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
    </div>
  );
}

/** Children appear one after another, in reading order. */
export function Stagger({ children, className, as = "ul" }: { children: ReactNode; className?: string; as?: "ul" | "ol" | "div" }) {
  const Tag = as === "ul" ? motion.ul : as === "ol" ? motion.ol : motion.div;
  return (
    <Tag className={className} initial="hidden" animate="shown" variants={{ hidden: {}, shown: { transition: { staggerChildren: 0.06, delayChildren: 0.1 } } }}>
      {children}
    </Tag>
  );
}

export const item = { hidden: { opacity: 0, y: 8 }, shown: { opacity: 1, y: 0, transition: { duration: 0.42, ease: [0.22, 1, 0.36, 1] as const } } };

export function PageHead({ eyebrow, title, lead, children }: { eyebrow?: string; title: ReactNode; lead?: string; children?: ReactNode }) {
  return (
    <header className="grid gap-3 pb-8 md:pb-10">
      {eyebrow && <p className="text-sm font-semibold tracking-[0.12em] text-muted-foreground uppercase">{eyebrow}</p>}
      <h1 className="text-[clamp(var(--text-h1),9vw,var(--text-display))] leading-[1.08] font-semibold tracking-[-0.02em]">{title}</h1>
      {lead && <p className="max-w-[58ch] text-lead leading-relaxed text-muted-foreground">{lead}</p>}
      {children}
    </header>
  );
}

export function Code({ children }: { children: ReactNode }) {
  return <code dir="ltr" className="rounded-[var(--radius-control)] border border-border bg-card px-1.5 py-0.5 font-mono text-[0.9em]">{children}</code>;
}

export function ConceptRow({ c, topicTitle }: { c: Concept; topicTitle?: string }) {
  const { t } = useT();
  const k = kind(c);
  return (
    <motion.li variants={item} className="grid gap-1 border-b border-paper-line py-4 sm:grid-cols-[9rem_minmax(0,1fr)_auto] sm:items-baseline sm:gap-6">
      <StatusLabel k={k} />
      <div className="grid min-w-0 gap-0.5">
        {/* The learner's own words may be in another language than the page: isolate their direction. */}
        <bdi className="text-lg font-semibold">{c.concept}</bdi>
        {topicTitle && <bdi className="text-sm text-muted-foreground">{topicTitle}</bdi>}
        {c.evidence && <bdi className="text-muted-foreground italic">“{c.evidence}”</bdi>}
      </div>
      <time dateTime={c.date} className="tabular text-sm text-muted-foreground">{t.date(c.date)}</time>
    </motion.li>
  );
}

export function Loading() {
  return <div className="grid gap-3 py-10" aria-busy="true"><div className="h-10 w-2/3 animate-pulse rounded bg-paper-line motion-reduce:animate-none" /><div className="h-5 w-1/2 animate-pulse rounded bg-paper-line motion-reduce:animate-none" /></div>;
}

export function Problem({ error }: { error: Error }) {
  const { t } = useT();
  return <p role="alert" className="max-w-[58ch] rounded-[var(--radius-card)] border border-border bg-card p-5">{error.message === "token" ? t.error.token : t.error.other}</p>;
}
