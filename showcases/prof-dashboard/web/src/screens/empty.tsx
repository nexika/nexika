import { useT } from "../i18n";
import { setDemo } from "../lib";
import { Code } from "../ui";

export function Empty() {
  const { t } = useT();
  return (
    <section className="grid max-w-[58ch] gap-3 rounded-[var(--radius-card)] border border-border bg-card p-6">
      <h2 className="text-h3 font-semibold">{t.empty.title}</h2>
      <p>{t.empty.body} <Code>/prof:learn</Code>,{" "}
        <button type="button" onClick={() => setDemo(true)} className="font-semibold text-primary underline underline-offset-4">{t.empty.orDemo}</button>
      </p>
    </section>
  );
}
