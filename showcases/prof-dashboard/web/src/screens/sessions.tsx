import { Link, useParams } from "@tanstack/react-router";
import { motion } from "motion/react";
import { useApi } from "../data";
import { useT } from "../i18n";
import { type Session, type SessionCard } from "../lib";
import { ConceptRow, item, Loading, PageHead, Problem, Stagger } from "../ui";
import { Empty } from "./empty";

const topicOf = (line: string) => line.split(":")[0];

export function Sessions() {
  const { t } = useT();
  const sessions = useApi<SessionCard[]>("sessions");
  if (sessions.error) return <Problem error={sessions.error} />;
  if (!sessions.data) return <Loading />;
  return (
    <>
      <PageHead title={t.sessions.title} lead={t.sessions.lead} />
      {sessions.data.length === 0 ? <Empty /> : (
        <Stagger as="ol" className="relative grid gap-8 border-s-2 border-paper-line ps-6 md:ps-8">
          {sessions.data.map((s) => (
            <motion.li key={s.id} variants={item} className="relative">
              <span aria-hidden="true" className="absolute -start-[calc(1.5rem+7px)] top-2 size-3 rounded-full border-2 border-background bg-primary md:-start-[calc(2rem+7px)]" />
              <Link to="/sessions/$id" params={{ id: s.id }} className="group grid gap-3 rounded-[var(--radius-card)] border border-border bg-card p-5 hover:border-primary md:grid-cols-[10rem_minmax(0,1fr)] md:gap-8">
                <time dateTime={s.date} className="tabular font-display text-lg font-semibold">{t.date(s.date)}<span className="block font-sans text-sm font-normal text-muted-foreground">{s.time}</span></time>
                <div className="grid gap-3">
                  <div>
                    <h2 className="text-sm font-semibold text-muted-foreground">{t.sessions.learned}</h2>
                    <ul className="mt-1 grid gap-1">{s.learned.map((l) => <li key={l} className="font-semibold"><bdi>{topicOf(l)}</bdi></li>)}</ul>
                  </div>
                  {s.review_next.length > 0 && (
                    <div>
                      <h2 className="text-sm font-semibold text-muted-foreground">{t.sessions.next}</h2>
                      <ul className="mt-1 grid gap-1">{s.review_next.map((l) => <li key={l}><bdi>{l}</bdi></li>)}</ul>
                    </div>
                  )}
                </div>
              </Link>
            </motion.li>
          ))}
        </Stagger>
      )}
    </>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <section className="grid gap-2">
      <h2 className="text-h3 font-semibold">{title}</h2>
      <ul className="grid list-disc gap-1.5 ps-5 marker:text-accent">{items.map((x) => <li key={x}><bdi>{x}</bdi></li>)}</ul>
    </section>
  );
}

export function SessionPage() {
  const { t } = useT();
  const { id } = useParams({ from: "/sessions/$id" });
  const session = useApi<Session>(`sessions/${id}`);
  if (session.error) return <Problem error={session.error} />;
  if (!session.data) return <Loading />;
  const s = session.data.sections;
  return (
    <>
      <Link to="/sessions" className="mb-6 inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-primary"><span aria-hidden="true" className="rtl:rotate-180">←</span> {t.sessions.back}</Link>
      <PageHead eyebrow={`${session.data.time}`} title={t.date(session.data.date)} />
      <div className="grid max-w-3xl gap-10">
        <List title={t.sessions.learned} items={s.learned} />
        <List title={t.sessions.did} items={s.did} />
        {s.checks.length > 0 && (
          <section className="grid gap-3">
            <h2 className="text-h3 font-semibold">{t.sessions.checks}</h2>
            <div className="overflow-x-auto rounded-[var(--radius-card)] border border-border" role="region" aria-label={t.sessions.checks} tabIndex={0}>
              <table className="w-full min-w-[34rem] border-collapse bg-card text-start">
                <thead><tr className="border-b border-border text-sm text-muted-foreground">
                  <th scope="col" className="px-4 py-3 text-start font-semibold">{t.sessions.question}</th>
                  <th scope="col" className="px-4 py-3 text-start font-semibold">{t.sessions.answer}</th>
                  <th scope="col" className="px-4 py-3 text-start font-semibold">{t.sessions.verdict}</th>
                </tr></thead>
                <tbody>
                  {s.checks.map((c) => (
                    <tr key={c.q} className="border-b border-paper-line last:border-0 align-top">
                      <td className="px-4 py-3"><bdi>{c.q}</bdi></td>
                      <td className="px-4 py-3 text-muted-foreground italic"><bdi>{c.answer}</bdi></td>
                      <td className={`px-4 py-3 font-semibold ${c.verdict === "correct" ? "text-understood" : c.verdict === "wrong" ? "text-missed" : "text-shaky"}`}>{c.verdict}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
        <List title={t.sessions.weak} items={s.weak} />
        <List title={t.sessions.levels} items={s.levels} />
        <List title={t.sessions.next} items={s.review_next} />
        {s.checklist.length > 0 && (
          <section className="grid gap-2">
            <h2 className="text-h3 font-semibold">{t.sessions.checklist}</h2>
            <Stagger className="border-t border-paper-line">{s.checklist.map((c) => <ConceptRow key={`${c.topic}/${c.concept}`} c={c} />)}</Stagger>
          </section>
        )}
      </div>
    </>
  );
}
