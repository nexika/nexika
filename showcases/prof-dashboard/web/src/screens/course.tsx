import { motion } from "motion/react";
import { useApi } from "../data";
import { pick, useT } from "../i18n";
import { cn, type Course as CourseData } from "../lib";
import { Code, item, Loading, PageHead, Problem, Stagger } from "../ui";

const STATUS_STYLE: Record<string, string> = {
  planned: "border-dashed text-muted-foreground",
  draft: "text-muted-foreground",
  checked: "text-foreground",
  reviewed: "border-primary text-primary",
  verified: "border-primary bg-primary text-primary-foreground",
};

/** A planned lesson with no title yet: its id, readable ("l0-set-up-claude-code" -> "Set up claude code"). */
function untitled(id: string): string {
  const words = id.replace(/^l\d+-/, "").replace(/-/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function Course() {
  const { t, lang } = useT();
  const course = useApi<CourseData>("course");
  if (course.error) return <Problem error={course.error} />;
  if (!course.data) return <Loading />;
  const c = course.data;
  if (!c.available || !c.course) {
    return (<><PageHead title={t.course.title} /><p className="max-w-[58ch]">{t.course.missing} {t.course.missingHow.split("LAWHA_COURSES")[0]}<Code>LAWHA_COURSES</Code>{t.course.missingHow.split("LAWHA_COURSES")[1]}</p></>);
  }
  return (
    <>
      <PageHead eyebrow={t.course.title} title={pick(c.course.title, lang, c.course.id)} lead={t.course.lead} />
      <Stagger as="ol" className="grid gap-12">
        {c.modules.map((m) => (
          <motion.li key={m.id} variants={item} className="grid gap-4 md:grid-cols-[12rem_minmax(0,1fr)] md:gap-10">
            <div className="grid content-start gap-1 border-t-2 border-accent pt-3">
              <span className="tabular text-sm font-semibold tracking-[0.12em] text-muted-foreground uppercase">{t.course.level} {m.level}</span>
              <h2 className="text-h3 leading-tight font-semibold">{pick(m.title, lang, m.id)}</h2>
              <span className="tabular text-sm text-muted-foreground">{t.course.lessons(m.lessons.length)}</span>
            </div>
            <ol className="border-t border-paper-line">
              {m.lessons.map((l, i) => (
                <li key={l.id} className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-baseline gap-3 border-b border-paper-line py-3">
                  <span className="tabular text-sm text-muted-foreground">{i + 1}</span>
                  <span className={cn("min-w-0", l.status === "planned" && "text-muted-foreground")}>
                    {pick(l.title, lang, untitled(l.id))}
                    {l.minutes && <span className="tabular ms-2 text-sm text-muted-foreground">{l.minutes} {t.course.minutes}</span>}
                  </span>
                  <span className={cn("rounded-full border border-border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap", STATUS_STYLE[l.status] ?? "")}>{t.course.status[l.status] ?? l.status}</span>
                </li>
              ))}
            </ol>
          </motion.li>
        ))}
      </Stagger>
    </>
  );
}
