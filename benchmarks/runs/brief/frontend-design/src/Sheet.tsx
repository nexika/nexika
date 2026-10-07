import { useEffect, useState } from "react";
import type { Copy } from "./copy";

const CHAR_MS = 38;
const PAUSE_MS = 650;
const START_MS = 700;

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * The hero's one moment of motion: a paragraph is written in one language, then
 * the next paragraph is written in the other, and the caret and the pilcrow move
 * to the other margin on their own.
 */
export function Sheet({ sheet, digits }: { sheet: Copy["sheet"]; digits: (n: number) => string }) {
  const paras = sheet.paragraphs.map((p) => Array.from(p.text));
  const total = paras.reduce((n, p) => n + p.length, 0);
  const [typed, setTyped] = useState(() => (prefersReducedMotion() ? total : 0));

  useEffect(() => {
    if (prefersReducedMotion()) {
      setTyped(total);
      return;
    }
    setTyped(0);
    let count = 0;
    let timer: number;
    const breakAt = paras[0].length;
    const tick = () => {
      count += 1;
      setTyped(count);
      if (count >= total) return;
      timer = window.setTimeout(tick, count === breakAt ? PAUSE_MS : CHAR_MS);
    };
    timer = window.setTimeout(tick, START_MS);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheet]);

  let remaining = typed;
  const shown = paras.map((chars) => {
    const n = Math.min(chars.length, Math.max(remaining, 0));
    remaining -= chars.length;
    return n;
  });
  const active = shown.findIndex((n, i) => n < paras[i].length);
  const caretIn = active === -1 ? paras.length - 1 : active;
  const wordCount = sheet.paragraphs
    .map((p, i) => paras[i].slice(0, shown[i]).join(""))
    .join(" ")
    .split(/\s+/)
    .filter(Boolean).length;

  return (
    <figure className="sheet" style={{ margin: 0 }} aria-label={sheet.label}>
      <div className="sheet-bar" aria-hidden="true">
        <span>{sheet.title}</span>
        <span className="sheet-saved">{sheet.saved}</span>
      </div>
      <div className="sheet-body">
        <p className="sheet-title write">{sheet.title}</p>
        <div className="sr-only">
          {sheet.paragraphs.map((p) => (
            <p key={p.lang} lang={p.lang} dir={p.dir}>
              {p.text}
            </p>
          ))}
        </div>
        <div aria-hidden="true">
          {sheet.paragraphs.map((p, i) => {
            const started = shown[i] > 0 || caretIn === i;
            return (
              <p
                key={p.lang}
                lang={p.lang}
                dir={p.dir}
                className="para write"
                style={{ ["--mark-opacity" as string]: started ? 1 : 0 }}
              >
                <span className="para-stack">
                  <span className="para-ghost">{p.text}</span>
                  <span>
                    {paras[i].slice(0, shown[i]).join("")}
                    {caretIn === i && <span className="caret" />}
                  </span>
                </span>
              </p>
            );
          })}
        </div>
      </div>
      <div className="sheet-foot" aria-hidden="true">
        <span>
          {digits(wordCount)} {sheet.words}
        </span>
        <span>{sheet.paragraphs[caretIn].dir === "rtl" ? sheet.rtl : sheet.ltr}</span>
      </div>
    </figure>
  );
}
