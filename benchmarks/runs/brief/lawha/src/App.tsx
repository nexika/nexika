import { motion } from "motion/react";
import { type ReactNode, useState } from "react";
import { Reveal, RevealGroup, RevealItem } from "./components/motion/Reveal";
import { Rule } from "./components/motion/Signature";
import { transition, useMotionTokens } from "./components/motion/tokens";
import { content, currentLang } from "./content";

/* Note: this direction's spacing step is 8px (--spacing: 0.5rem), so p-3 is 24px, py-12 is 96px. */

const lang = currentLang();
const t = content[lang];

function Arrow() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="size-[1em] shrink-0 rtl:-scale-x-100" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 8h11M9 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** The signature: a thin margin rule drawn down the side of a block, from the top. */
function MarginRule({ className = "" }: { className?: string }) {
  const m = useMotionTokens();
  return (
    <motion.span
      aria-hidden="true"
      className={`absolute inset-y-0 start-0 w-px bg-accent ${className}`}
      style={{ transformOrigin: "top" }}
      initial={m.reduce ? false : { scaleY: 0 }}
      whileInView={{ scaleY: 1 }}
      viewport={{ once: true, margin: "0px 0px -10% 0px" }}
      transition={transition(m, "slow")}
    />
  );
}

function ThemeToggle() {
  const [dark, setDark] = useState(() => typeof document !== "undefined" && document.documentElement.classList.contains("dark"));
  function toggle() {
    const next = !dark;
    setDark(next);
    const d = document.documentElement;
    d.classList.toggle("dark", next);
    d.style.colorScheme = next ? "dark" : "light";
    try {
      localStorage.setItem("qalam-theme", next ? "dark" : "light");
    } catch {
      /* private mode: the choice lasts for this visit only */
    }
  }
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? t.theme.toLight : t.theme.toDark}
      className="inline-flex size-[44px] items-center justify-center rounded-control text-foreground transition-colors duration-200 hover:bg-card"
    >
      {dark ? (
        <svg aria-hidden="true" viewBox="0 0 24 24" className="size-[20px]" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" strokeLinecap="round" />
        </svg>
      ) : (
        <svg aria-hidden="true" viewBox="0 0 24 24" className="size-[20px]" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}

function Header() {
  const langHref = lang === "ar" ? (typeof location !== "undefined" ? location.pathname : "/") : t.switchLang.href;
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur-sm">
      <div className="mx-auto flex h-[64px] max-w-6xl items-center gap-1 px-2 md:px-4">
        <a href="#top" className="me-auto flex min-h-[44px] items-baseline gap-1 font-display text-[1.5rem] font-semibold tracking-tight">
          <span>Qalam</span>
          <span lang="ar" className="font-arabic text-[1.25rem] font-bold text-primary">قلم</span>
        </a>
        <nav aria-label={lang === "ar" ? "الرئيسية" : "Main"} className="hidden items-center gap-3 md:flex">
          <a className="py-1 text-muted-foreground transition-colors hover:text-foreground" href="#features">{t.nav.features}</a>
          <a className="py-1 text-muted-foreground transition-colors hover:text-foreground" href="#how">{t.nav.how}</a>
          <a className="py-1 text-muted-foreground transition-colors hover:text-foreground" href="#pricing">{t.nav.pricing}</a>
        </nav>
        <a
          href={langHref}
          hrefLang={t.switchLang.hreflang}
          lang={t.switchLang.hreflang}
          aria-label={t.switchLang.aria}
          className={`inline-flex min-h-[44px] items-center px-1 text-foreground underline decoration-accent decoration-1 underline-offset-[6px] md:ms-2 ${t.switchLang.hreflang === "ar" ? "font-arabic text-[1.125rem]" : ""}`}
        >
          {t.switchLang.label}
        </a>
        <ThemeToggle />
        <a
          href="#pricing"
          className="hidden min-h-[44px] items-center rounded-control bg-primary px-2 font-semibold text-primary-foreground transition-opacity hover:opacity-90 sm:inline-flex"
        >
          {t.start}
        </a>
      </div>
    </header>
  );
}

function EditorMock() {
  const e = t.editor;
  return (
    <figure
      aria-label={lang === "ar" ? "مثال على محرر قلم" : "An example page in the Qalam editor"}
      className="relative rounded-card border border-border bg-card shadow-[0_24px_60px_-30px_rgb(30_26_22/0.35)] dark:shadow-[0_24px_60px_-30px_rgb(0_0_0/0.8)]"
    >
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5 text-[1rem] text-muted-foreground md:text-[0.875rem]">
        <span dir="ltr" className="truncate font-mono text-[0.875rem] md:text-[0.8125rem]">{e.file}</span>
        <span className="inline-flex shrink-0 items-center gap-1">
          <span aria-hidden="true" className="size-[6px] rounded-full bg-accent" />
          {e.saved}
        </span>
      </div>
      <div className="relative px-3 py-3 md:px-5 md:py-4">
        <span aria-hidden="true" className="absolute inset-y-3 start-[12px] w-px bg-primary/40 md:start-[24px]" />
        <h3 dir="auto" className="font-display text-[1.75rem] leading-tight font-semibold [&:lang(ar)]:leading-[1.35]">{e.heading}</h3>
        <p dir="auto" className="mt-2 text-foreground">
          {e.p1} <q lang="ar" className="whitespace-nowrap font-arabic font-bold text-primary"><bdi>{e.p1q}</bdi></q> {e.p1end}
        </p>
        <p dir="auto" lang={lang === "ar" ? "en" : "ar"} className={`mt-2 border-s-2 border-accent ps-2 text-foreground ${lang === "ar" ? "" : "font-arabic text-[1.25rem] leading-[1.9]"}`}>
          {e.p2}
        </p>
        <p className="mt-3 text-[1rem] text-muted-foreground md:text-[0.875rem]">{e.count}</p>
      </div>
    </figure>
  );
}

function Hero() {
  const h = t.hero;
  return (
    <section id="top" className="mx-auto max-w-6xl px-2 pt-6 pb-8 md:px-4 md:pt-10 md:pb-12">
      <Reveal>
        <p className="text-[1rem] font-semibold tracking-wide text-primary">{h.kicker}</p>
      </Reveal>
      <Reveal delay={0.08}>
        <h1 className="mt-2 max-w-[18ch] font-display text-[2.75rem] leading-[1.05] font-semibold tracking-[-0.02em] [&:lang(ar)]:leading-[1.35] text-balance md:text-h1 lg:text-display">
          {h.title} <span className="text-primary">{h.titleEnd}</span>
        </h1>
      </Reveal>
      {/* The bilingual line: the same sentence in the other script, set across the margin rule. */}
      <Reveal delay={0.16}>
        <p
          lang={h.other.lang}
          dir={h.other.lang === "ar" ? "rtl" : "ltr"}
          className={`relative mt-3 w-fit max-w-[40ch] ps-2 text-muted-foreground ${h.other.lang === "ar" ? "font-arabic text-[1.5rem] md:text-[1.75rem]" : "font-display text-[1.25rem] italic md:text-[1.5rem]"}`}
        >
          <MarginRule />
          {h.other.text}
        </p>
      </Reveal>
      <div className="mt-6 grid items-start gap-6 md:mt-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-8">
        <Reveal delay={0.24}>
          <p className="max-w-[46ch] text-[1.125rem] text-muted-foreground md:text-lead">{h.sub}</p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <a href="#pricing" className="inline-flex min-h-[48px] items-center gap-1 rounded-control bg-primary px-3 font-semibold text-primary-foreground transition-opacity hover:opacity-90">
              {t.start} <Arrow />
            </a>
            <a href="#how" className="inline-flex min-h-[48px] items-center rounded-control border border-border px-3 font-semibold text-foreground transition-colors hover:bg-card">
              {h.secondary}
            </a>
          </div>
          <p className="mt-2 text-[1rem] text-muted-foreground">{h.note}</p>
        </Reveal>
        <Reveal delay={0.32}>
          <EditorMock />
        </Reveal>
      </div>
    </section>
  );
}

/** A section with its label in the margin and the margin rule down the side of its content. */
function MarginSection({ id, eyebrow, title, other, children, n }: { id: string; eyebrow: string; title: string; other: { lang: string; text: string }; children: ReactNode; n: string }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="mx-auto max-w-6xl scroll-mt-[80px] px-2 py-8 md:px-4 md:py-12">
      <div className="grid gap-3 md:grid-cols-[minmax(0,10rem)_minmax(0,1fr)] md:gap-6">
        <div className="flex items-baseline gap-2 md:block">
          <span className="font-display text-[1rem] text-accent-foreground/70 tabular-nums dark:text-muted-foreground">{n}</span>
          <p className="text-[1rem] font-semibold tracking-wide text-primary md:mt-1">{eyebrow}</p>
          {/* The signature: the heading in the other script, across the margin rule. */}
          <p
            lang={other.lang}
            dir={other.lang === "ar" ? "rtl" : "ltr"}
            className={`mt-3 hidden text-balance text-muted-foreground md:block ${other.lang === "ar" ? "font-arabic text-[1.5rem] leading-[1.6]" : "font-display text-[1.25rem] leading-[1.35] italic"}`}
          >
            {other.text}
          </p>
        </div>
        <div className="relative min-w-0 ps-3 md:ps-5">
          <MarginRule />
          <Reveal inView>
            <h2 id={`${id}-title`} className="max-w-[22ch] font-display text-[2rem] leading-[1.1] font-semibold tracking-[-0.015em] [&:lang(ar)]:leading-[1.35] text-balance md:text-h2">
              {title}
            </h2>
          </Reveal>
          <div className="mt-4 md:mt-6">{children}</div>
        </div>
      </div>
    </section>
  );
}

function Features() {
  const f = t.features;
  return (
    <MarginSection id="features" n="I" eyebrow={f.eyebrow} title={f.title} other={f.other}>
      <RevealGroup inView as="ul" className="grid gap-4 md:grid-cols-3 md:gap-4">
        {f.items.map((it) => (
          <RevealItem as="li" key={it.n} className="border-t border-border pt-2">
            <span className="font-display text-[1rem] text-primary tabular-nums">{it.n}</span>
            <h3 className="mt-1 font-display text-[1.5rem] leading-tight font-semibold [&:lang(ar)]:leading-[1.35]">{it.title}</h3>
            <p className="mt-1 text-muted-foreground">{it.body}</p>
          </RevealItem>
        ))}
      </RevealGroup>
    </MarginSection>
  );
}

function How() {
  const h = t.how;
  const nums = lang === "ar" ? ["١", "٢", "٣"] : ["1", "2", "3"];
  return (
    <MarginSection id="how" n="II" eyebrow={h.eyebrow} title={h.title} other={h.other}>
      <RevealGroup inView as="ol" className="grid gap-3">
        {h.steps.map((s, i) => (
          <RevealItem as="li" key={s.title} className="grid grid-cols-[48px_minmax(0,1fr)] items-baseline gap-2 border-b border-border pb-3 last:border-b-0 md:grid-cols-[72px_minmax(0,16rem)_minmax(0,1fr)] md:gap-4">
            <span aria-hidden="true" className="font-display text-[2.5rem] leading-none font-semibold text-accent md:text-h2">{nums[i]}</span>
            <h3 className="font-display text-[1.375rem] leading-tight font-semibold [&:lang(ar)]:leading-[1.35] md:text-[1.5rem]">{s.title}</h3>
            <p className="col-start-2 text-muted-foreground md:col-start-3">{s.body}</p>
          </RevealItem>
        ))}
      </RevealGroup>
    </MarginSection>
  );
}

function Testimonial() {
  const q = t.quote;
  return (
    <section aria-label={lang === "ar" ? "رأي كاتبة" : "What a writer says"} className="border-y border-border bg-card">
      <div className="mx-auto max-w-6xl px-2 py-8 md:px-4 md:py-12">
        <Reveal inView>
          <figure className="grid gap-2 md:grid-cols-[minmax(0,10rem)_minmax(0,1fr)] md:gap-6">
            <span aria-hidden="true" className="block font-display text-[5rem] leading-[0.6] text-accent md:pt-1 md:text-end md:text-[6rem]">{lang === "ar" ? "”" : "“"}</span>
            <div className="relative min-w-0 ps-3 md:ps-5">
              <MarginRule />
              <blockquote className={`max-w-[34ch] font-display leading-[1.3] text-balance ${lang === "ar" ? "text-[1.625rem] md:text-[2.25rem]" : "text-[1.5rem] italic md:text-[2.125rem]"}`}>
                <p>{q.text}</p>
              </blockquote>
              <figcaption className="mt-4 flex items-center gap-2">
                <span aria-hidden="true" className="h-px w-5 bg-accent" />
                <span>
                  <span className="block font-semibold">{q.name}</span>
                  <span className="block text-[1rem] text-muted-foreground">{q.role}</span>
                </span>
              </figcaption>
            </div>
          </figure>
        </Reveal>
      </div>
    </section>
  );
}

function Pricing() {
  const p = t.pricing;
  return (
    <MarginSection id="pricing" n="III" eyebrow={p.eyebrow} title={p.title} other={p.other}>
      <RevealGroup inView className="grid gap-3 md:grid-cols-2 md:gap-4">
        {p.plans.map((plan) => (
          <RevealItem
            key={plan.name}
            className={`relative flex flex-col rounded-card border bg-card p-3 md:p-4 ${plan.featured ? "border-primary shadow-[0_20px_50px_-30px_rgb(122_46_31/0.45)]" : "border-border"}`}
          >
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-display text-[1.75rem] font-semibold">{plan.name}</h3>
              {plan.featured && (
                <span className="rounded-control bg-primary px-1 py-0.5 text-[1rem] font-semibold md:text-[0.875rem] text-primary-foreground">{p.badge}</span>
              )}
            </div>
            <p className="mt-1 text-muted-foreground">{plan.blurb}</p>
            <p className="mt-3 flex items-baseline gap-1">
              <span className="font-display text-h2 leading-none font-semibold tabular-nums">{plan.price}</span>
              <span className="text-muted-foreground">{p.period}</span>
            </p>
            <ul className="mt-3 mb-4 grid gap-1 border-t border-border pt-3">
              {plan.items.map((item) => (
                <li key={item} className="flex gap-1.5">
                  <svg aria-hidden="true" viewBox="0 0 16 16" className="mt-[0.4em] size-[14px] shrink-0 text-primary" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 8.5l3 3 7-7" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <a
              href="#start"
              className={`mt-auto inline-flex min-h-[48px] items-center justify-center gap-1 rounded-control px-3 font-semibold transition-opacity ${plan.featured ? "bg-primary text-primary-foreground hover:opacity-90" : "border border-border text-foreground hover:bg-background"}`}
            >
              {plan.cta}
            </a>
          </RevealItem>
        ))}
      </RevealGroup>
    </MarginSection>
  );
}

function FinalCta() {
  const c = t.cta;
  return (
    <section id="start" aria-labelledby="start-title" className="mx-auto max-w-6xl px-2 py-8 md:px-4 md:py-12">
      <div className="relative overflow-hidden rounded-card bg-primary px-3 py-6 text-primary-foreground md:px-8 md:py-10">
        <span aria-hidden="true" className="pointer-events-none absolute -bottom-[0.35em] end-[-0.05em] select-none font-arabic text-[12rem] leading-none font-bold opacity-[0.08] after:content-['قلم'] md:text-[20rem]" />
        <div className="relative max-w-3xl">
          <Rule className="mb-4 h-px w-12 bg-primary-foreground/60" />
          <h2 id="start-title" className="font-display text-[2.25rem] leading-[1.08] font-semibold tracking-[-0.015em] [&:lang(ar)]:leading-[1.35] text-balance md:text-h1">{c.title}</h2>
          <p lang={c.other.lang} dir={c.other.lang === "ar" ? "rtl" : "ltr"} className={`mt-2 w-fit opacity-90 ${c.other.lang === "ar" ? "font-arabic text-[1.5rem]" : "font-display text-[1.25rem] italic"}`}>
            {c.other.text}
          </p>
          <a href="#top" className="mt-5 inline-flex min-h-[48px] items-center gap-1 rounded-control bg-primary-foreground px-3 font-semibold text-primary transition-opacity hover:opacity-90">
            {c.button} <Arrow />
          </a>
        </div>
      </div>
    </section>
  );
}

export default function App() {
  return (
    <>
      <a href="#main" className="sr-only rounded-control bg-primary text-primary-foreground focus:not-sr-only focus:fixed focus:start-2 focus:top-2 focus:z-50 focus:inline-flex focus:min-h-[44px] focus:items-center focus:px-2">
        {t.skip}
      </a>
      <Header />
      <main id="main" className="overflow-x-clip">
        <Hero />
        <Features />
        <How />
        <Testimonial />
        <Pricing />
        <FinalCta />
      </main>
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col gap-1 px-2 py-4 text-[1rem] text-muted-foreground md:flex-row md:items-center md:justify-between md:px-4">
          <p>{t.footer.made}</p>
          <p>{t.footer.rights}</p>
        </div>
      </footer>
    </>
  );
}
