import "@fontsource/fraunces/500.css";
import "@fontsource/fraunces/600.css";
import "@fontsource/source-sans-3/400.css";
import "@fontsource/source-sans-3/600.css";
import "./styles.css";
import { motion, MotionConfig } from "motion/react";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { ActiveMark } from "./motion/ActiveMark";
import { CountUp } from "./motion/CountUp";
import { PageTransition } from "./motion/PageTransition";
import { usePress } from "./motion/Press";
import { Reveal, RevealGroup, RevealItem } from "./motion/Reveal";
import { Sheet } from "./motion/Sheet";
import { Cells, Dots, Outline, Rule, Stamp, Underline } from "./motion/Signature";
import { Swap } from "./motion/Swap";
import { Toaster, ToastProvider, useToast } from "./motion/Toasts";

const ar = new URLSearchParams(location.search).get("lang") === "ar";
document.documentElement.lang = ar ? "ar" : "en";
document.documentElement.dir = ar ? "rtl" : "ltr";

const T = ar
  ? { title: "وصفات الحركة من lawha", lead: "كل حركة هنا تتبع اتجاه القراءة وتحترم «تقليل الحركة».", tabs: ["اليوم", "المواضيع", "الجلسات"], review: "راجع أولاً", concepts: ["تكلفة رموز الإخراج", "تاريخ انتهاء بيانات التدريب", "سبب التوقف"], counts: ["أخطأت", "متردد", "فهمت"], filters: "عوامل التصفية", open: "افتح الفلاتر", save: "احفظ", saved: "تم الحفظ", load: "حمّل الجلسات", sessions: ["الجلسة ٣: الرسائل والأدوار", "الجلسة ٢: الرموز والسياق", "الجلسة ١: التنبؤ بالكلمة التالية"], signatures: "التواقيع", known: "٣ من ٥ مفهومة", done: "٤ من ٧ منجزة", reviewed: "تمت المراجعة", body: "نص لوحة تحيط به حركة الإطار." }
  : { title: "lawha motion recipes", lead: "Every movement here follows the reading direction and respects “reduce motion”.", tabs: ["Today", "Topics", "Sessions"], review: "Review first", concepts: ["Output tokens cost more", "Training data cutoff", "stop_reason max_tokens"], counts: ["Missed", "Shaky", "Understood"], filters: "Filters", open: "Open filters", save: "Save", saved: "Saved", load: "Load sessions", sessions: ["Session 3: messages and roles", "Session 2: tokens and context", "Session 1: next-token prediction"], signatures: "Signatures", known: "3 of 5 known", done: "4 of 7 done", reviewed: "Reviewed", body: "A panel that the outline traces around." };

function Buttons() {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-wrap gap-3">
      <motion.button type="button" {...usePress()} onClick={() => toast(T.saved)} className="min-h-11 rounded-[var(--radius-control)] bg-primary px-5 font-semibold text-primary-foreground">{T.save}</motion.button>
      <motion.button type="button" {...usePress()} onClick={() => setOpen(true)} className="min-h-11 rounded-[var(--radius-control)] border border-border bg-card px-5 font-semibold">{T.open}</motion.button>
      <Sheet open={open} onClose={() => setOpen(false)} title={T.filters}><p>{T.lead}</p></Sheet>
    </div>
  );
}

function Sessions() {
  const [ready, setReady] = useState(false);
  useEffect(() => { const timer = setTimeout(() => setReady(true), 600); return () => clearTimeout(timer); }, []);
  const skeleton = <div className="grid gap-3">{T.sessions.map((s) => <div key={s} className="h-14 rounded-[var(--radius-card)] bg-border/60" />)}</div>;
  return (
    <Swap ready={ready} skeleton={skeleton} minHeight="12rem">
      <RevealGroup as="ul" className="grid gap-3">
        {T.sessions.map((s) => <RevealItem as="li" key={s} className="flex min-h-14 items-center rounded-[var(--radius-card)] border border-border bg-card px-4">{s}</RevealItem>)}
      </RevealGroup>
    </Swap>
  );
}

function App() {
  const [tab, setTab] = useState(0);
  return (
    <ToastProvider>
      <main className="mx-auto grid max-w-3xl gap-12 px-5 py-12">
        <Reveal as="header" className="grid gap-3">
          <h1 className="text-[clamp(2.2rem,7vw,3.4rem)] leading-[1.05] font-semibold">{T.title}</h1>
          <p className="text-lg text-muted-foreground">{T.lead}</p>
        </Reveal>

        <section className="grid gap-6">
          <nav aria-label="Tabs" className="flex border-b border-border">
            {T.tabs.map((label, i) => (
              <button key={label} type="button" onClick={() => setTab(i)} aria-current={tab === i ? "page" : undefined} className={`relative min-h-11 px-4 ${tab === i ? "font-semibold" : "text-muted-foreground"}`}>
                {label}
                {tab === i && <ActiveMark group="tabs" className="absolute inset-x-3 -bottom-px h-[3px] rounded-full bg-accent" />}
              </button>
            ))}
          </nav>
          <PageTransition id={String(tab)}>
            {tab === 0 && (
              <div className="grid gap-6">
                <p className="text-xl">{T.review}: <Underline><strong>{T.concepts[0]}</strong></Underline></p>
                <dl className="grid grid-cols-3 gap-4">
                  {[1, 2, 7].map((n, i) => (
                    <div key={i} className="grid gap-1 rounded-[var(--radius-card)] border border-border bg-card p-4">
                      <dt className="text-sm text-muted-foreground">{T.counts[i]}</dt>
                      <dd className="font-display text-3xl font-semibold"><CountUp value={n} /></dd>
                    </div>
                  ))}
                </dl>
                <RevealGroup as="ul" className="grid gap-2">
                  {T.concepts.map((c) => <RevealItem as="li" key={c} className="border-b border-border py-3">{c}</RevealItem>)}
                </RevealGroup>
              </div>
            )}
            {tab === 1 && <p className="text-lg">{T.concepts.join(" · ")}</p>}
            {tab === 2 && <Sessions />}
          </PageTransition>
        </section>

        <Buttons />

        <section className="grid gap-6">
          <Rule />
          <h2 className="text-2xl font-semibold">{T.signatures}</h2>
          <div className="flex flex-wrap items-center gap-8">
            <Cells value={3} total={5} label={T.known} />
            <Dots value={4} total={7} label={T.done} />
            <Stamp>{T.reviewed}</Stamp>
          </div>
          <Outline className="rounded-lg p-6"><p>{T.body}</p></Outline>
        </section>
      </main>
      <Toaster />
    </ToastProvider>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><MotionConfig reducedMotion="user"><App /></MotionConfig></StrictMode>);
