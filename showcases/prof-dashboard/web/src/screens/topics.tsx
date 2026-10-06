import { Link, useParams } from "@tanstack/react-router";
import { motion } from "motion/react";
import { useApi } from "../data";
import { useT } from "../i18n";
import { type Concept, kind, type Topic, type TopicCard } from "../lib";
import { ConceptRow, item, Loading, Mastery, PageHead, Problem, Stagger, StatusLabel, type Kind } from "../ui";
import { Empty } from "./empty";

export function Topics() {
  const { t } = useT();
  const topics = useApi<TopicCard[]>("topics");
  if (topics.error) return <Problem error={topics.error} />;
  if (!topics.data) return <Loading />;
  return (
    <>
      <PageHead title={t.topics.title} lead={t.topics.lead} />
      {topics.data.length === 0 ? <Empty /> : (
        <Stagger className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {topics.data.map((x) => {
            const total = x.counts.missed + x.counts.shaky + x.counts["not-checked"] + x.counts.understood;
            const kinds = (["missed", "shaky", "stale"] as const).filter((k) => x.counts[k] > 0);
            return (
              <motion.li key={x.slug} variants={item}>
                <Link to="/topics/$slug" params={{ slug: x.slug }} className="grid h-full content-start gap-4 rounded-[var(--radius-card)] border border-border bg-card p-5 transition-colors duration-[var(--duration-fast)] hover:border-primary">
                  <div className="grid gap-1">
                    <h2 className="text-h3 leading-tight font-semibold">{x.title}</h2>
                    <p className="tabular text-sm text-muted-foreground">{total} {t.topics.concepts} · {t.topics.last} {t.date(x.last)}</p>
                  </div>
                  <Mastery value={x.mastery} label={t.topics.mastery} />
                  {kinds.length > 0 && (
                    <ul className="flex flex-wrap gap-x-4 gap-y-1">
                      {kinds.map((k) => <li key={k} className="tabular flex items-center gap-1"><StatusLabel k={k} /><span className="text-sm font-semibold">{x.counts[k]}</span></li>)}
                    </ul>
                  )}
                </Link>
              </motion.li>
            );
          })}
        </Stagger>
      )}
    </>
  );
}

const ORDER: Kind[] = ["missed", "shaky", "stale", "not-checked", "understood"];

export function TopicPage() {
  const { t } = useT();
  const { slug } = useParams({ from: "/topics/$slug" });
  const topic = useApi<Topic>(`topics/${slug}`);
  if (topic.error) return <Problem error={topic.error} />;
  if (!topic.data) return <Loading />;
  const groups = ORDER.map((k) => ({ k, items: topic.data!.concepts.filter((c: Concept) => kind(c) === k) })).filter((g) => g.items.length);
  return (
    <>
      <Link to="/topics" className="mb-6 inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-primary"><span aria-hidden="true" className="rtl:rotate-180">←</span> {t.topics.back}</Link>
      <PageHead title={topic.data.title} />
      <div className="grid gap-10">
        {groups.map((g) => (
          <section key={g.k} aria-label={t.status[g.k]}>
            <h2 className="mb-1"><StatusLabel k={g.k} /></h2>
            <Stagger className="border-t border-paper-line">
              {g.items.map((c) => <ConceptRow key={c.concept} c={c} />)}
            </Stagger>
          </section>
        ))}
      </div>
    </>
  );
}
