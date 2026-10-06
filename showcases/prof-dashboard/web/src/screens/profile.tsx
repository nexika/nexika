import { Fragment, type ReactNode } from "react";
import { useApi } from "../data";
import { useT } from "../i18n";
import { Loading, PageHead, Problem } from "../ui";

/** Inline **bold** and `code`, rendered as elements (never as HTML). */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>
      : part.startsWith("`") && part.endsWith("`") ? <code key={i} dir="ltr" className="font-mono text-[0.9em]">{part.slice(1, -1)}</code>
        : <Fragment key={i}>{part}</Fragment>);
}

/** Just enough markdown for prof's profile: headings, bullet lists and paragraphs. */
function Markdown({ source }: { source: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) blocks.push(<ul key={blocks.length} className="grid list-disc gap-1.5 ps-5 marker:text-accent">{list.map((l, i) => <li key={i}>{inline(l)}</li>)}</ul>);
    list = [];
  };
  for (const line of source.split("\n")) {
    if (/^\s*[-*] /.test(line)) { list.push(line.replace(/^\s*[-*] /, "")); continue; }
    flush();
    if (line.startsWith("# ")) continue; // the page has its own title
    if (line.startsWith("## ")) blocks.push(<h2 key={blocks.length} className="mt-4 text-h3 font-semibold">{inline(line.slice(3))}</h2>);
    else if (line.trim()) blocks.push(<p key={blocks.length}>{inline(line)}</p>);
  }
  flush();
  return <div className="grid max-w-[62ch] gap-4 text-lg">{blocks}</div>;
}

export function Profile() {
  const { t } = useT();
  const profile = useApi<{ markdown: string | null }>("profile");
  if (profile.error) return <Problem error={profile.error} />;
  if (!profile.data) return <Loading />;
  return (
    <>
      <PageHead title={t.profile.title} lead={t.profile.lead} />
      {profile.data.markdown ? <Markdown source={profile.data.markdown} /> : <p>{t.profile.empty}</p>}
    </>
  );
}
