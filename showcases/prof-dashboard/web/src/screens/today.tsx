import { Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import { useApi } from "../data";
import { useT } from "../i18n";
import { kind, type SessionCard, type Summary, type TopicCard } from "../lib";
import { Code, ConceptRow, CountUp, item, Loading, Mastery, PageHead, Problem, Stagger, StatusMark, Underline } from "../ui";
import { Empty } from "./empty";

export function Today() {
  const { t } = useT();
  const summary = useApi<Summary>("summary");
  const topics = useApi<TopicCard[]>("topics");
  const sessions = useApi<SessionCard[]>("sessions");
  if (summary.error) return <Problem error={summary.error} />;
  if (!summary.data) return <Loading />;
  const s = summary.data;
  if (!s.has_data) return (<><PageHead eyebrow={t.today.eyebrow} title={t.today.title(0)} /><Empty /></>);

  const review = s.today.review.filter((c) => kind(c) !== "understood");
  const first = review[0];
  const titleOf = (slug: string) => topics.data?.find((x) => x.slug === slug)?.title ?? slug;
  const counts = (["missed", "shaky", "stale", "understood"] as const).map((k) => ({ k, n: s.today.counts[k] }));
  const last = sessions.data?.[0];

  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_19rem] lg:gap-16">
      <div className="min-w-0">
        <PageHead eyebrow={t.date(new Date().toISOString().slice(0, 10))} title={t.today.title(review.length)}>
          {first && (
            <p className="text-lead leading-relaxed">
              {t.today.first} <Underline><strong className="font-semibold">{first.concept}</strong></Underline>
            </p>
          )}
          <p className="max-w-[58ch] text-muted-foreground">{t.today.lead}</p>
        </PageHead>

        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-[var(--radius-card)] border border-border bg-border sm:grid-cols-4">
          {counts.map(({ k, n }) => (
            <div key={k} className="grid gap-1 bg-card px-4 py-4">
              <dt className="flex items-center gap-1.5 text-sm text-muted-foreground"><StatusMark k={k} />{t.status[k]}</dt>
              <dd className="font-display text-h2 leading-none font-semibold"><CountUp value={n} /></dd>
            </div>
          ))}
        </dl>

        {review.length ? (
          <Stagger className="mt-8 border-t border-paper-line">
            {review.map((c) => <ConceptRow key={`${c.topic}/${c.concept}`} c={c} topicTitle={titleOf(c.topic)} />)}
          </Stagger>
        ) : (
          <p className="mt-8">{t.today.empty} <Code>/prof:learn</Code></p>
        )}

        {review.length > 0 && (
          <p className="mt-8 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-[var(--radius-card)] bg-primary px-5 py-4 text-primary-foreground">
            {t.today.hint} <code dir="ltr" className="rounded-[var(--radius-control)] bg-primary-foreground/15 px-1.5 py-0.5 font-mono">/prof:warmup</code> {t.today.hintAfter}
          </p>
        )}
      </div>

      <aside className="grid content-start gap-10">
        {last && (
          <section className="grid gap-3">
            <h2 className="text-sm font-semibold tracking-[0.12em] text-muted-foreground uppercase">{t.today.last}</h2>
            <Link to="/sessions/$id" params={{ id: last.id }} className="group grid gap-2 rounded-[var(--radius-card)] border border-border bg-card p-5 hover:border-primary">
              <time dateTime={last.date} className="tabular text-sm text-muted-foreground">{t.date(last.date)} · {last.time}</time>
              <ul className="grid gap-1.5">
                {last.learned.slice(0, 3).map((l) => <li key={l} className="leading-snug"><bdi>{l.split(":")[0]}</bdi></li>)}
              </ul>
            </Link>
          </section>
        )}
        {topics.data && (
          <section className="grid gap-4">
            <h2 className="text-sm font-semibold tracking-[0.12em] text-muted-foreground uppercase">{t.nav.topics}</h2>
            <Stagger as="div" className="grid gap-5">
              {topics.data.map((x) => (
                <motion.div key={x.slug} variants={item}>
                  <Link to="/topics/$slug" params={{ slug: x.slug }} className="grid gap-2 hover:text-primary">
                    <bdi className="font-semibold">{x.title}</bdi>
                    <Mastery value={x.mastery} label={t.topics.mastery} />
                  </Link>
                </motion.div>
              ))}
            </Stagger>
            <Link to="/topics" className="inline-flex min-h-11 items-center self-start text-sm font-semibold text-primary underline underline-offset-4">{t.today.all}</Link>
          </section>
        )}
      </aside>
    </div>
  );
}
