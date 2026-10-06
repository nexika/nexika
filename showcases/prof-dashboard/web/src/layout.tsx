import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";
import { type Lang, useT } from "./i18n";
import { cn, demoOn, setDemo } from "./lib";

type Theme = "light" | "dark" | "system";

function applyTheme(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

export function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem("prof-theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch { /* ignore */ }
  return "system";
}

function ThemeSwitch() {
  const { t } = useT();
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => {
    applyTheme(theme);
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const follow = () => theme === "system" && applyTheme("system");
    mq.addEventListener("change", follow);
    return () => mq.removeEventListener("change", follow);
  }, [theme]);
  const next: Theme = document.documentElement.classList.contains("dark") ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => {
        try { localStorage.setItem("prof-theme", next); } catch { /* ignore */ }
        setTheme(next);
      }}
      className="grid size-11 place-items-center rounded-[var(--radius-control)] text-muted-foreground hover:bg-card hover:text-foreground"
      aria-label={`${t.theme}: ${next === "dark" ? t.dark : t.light}`}
    >
      <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
        {next === "dark" ? <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" /> : (<><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>)}
      </svg>
    </button>
  );
}

function LangSwitch() {
  const { lang, setLang, t } = useT();
  const langs: [Lang, string, string][] = [["en", "EN", "English"], ["ar", "ع", "العربية"], ["fr", "FR", "Français"]];
  return (
    <div role="group" aria-label={t.language} className="flex">
      {langs.map(([code, short, name]) => (
        <button
          key={code}
          type="button"
          lang={code}
          aria-pressed={lang === code}
          aria-label={name}
          onClick={() => setLang(code)}
          className={cn("grid h-11 min-w-11 place-items-center px-2 text-sm font-semibold text-muted-foreground hover:text-foreground", lang === code && "text-foreground underline decoration-accent decoration-2 underline-offset-[6px]")}
        >
          {short}
        </button>
      ))}
    </div>
  );
}

export function Layout() {
  const { t } = useT();
  const reduce = useReducedMotion();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const demo = demoOn();
  const nav = [
    { to: "/", label: t.nav.today },
    { to: "/topics", label: t.nav.topics },
    { to: "/course", label: t.nav.course },
    { to: "/sessions", label: t.nav.sessions },
    { to: "/profile", label: t.nav.profile },
  ] as const;
  const active = (to: string) => (to === "/" ? path === "/" : path.startsWith(to));
  const section = nav.find((n) => active(n.to))?.to ?? path;

  return (
    <div className="min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-50 focus:rounded focus:bg-card focus:px-4 focus:py-2">{t.skip}</a>
      {demo && (
        <div className="border-b border-border bg-accent/20 px-5 py-2 text-center text-sm">
          {t.demoOn}{" "}
          <button type="button" onClick={() => setDemo(false)} className="inline-flex min-h-11 items-center font-semibold underline underline-offset-4 sm:min-h-6">{t.demoOff}</button>
        </div>
      )}
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-1 px-5 pt-3 md:px-8 md:py-3">
          <Link to="/" className="flex items-baseline gap-2 py-2 me-auto">
            <span className="font-display text-2xl font-semibold tracking-[-0.01em]">{t.brand}</span>
            <span className="text-sm text-muted-foreground">{t.brandSub}</span>
          </Link>
          <nav aria-label={t.menu} className="order-last -mx-5 w-[calc(100%+2.5rem)] overflow-x-auto px-3 md:order-none md:mx-0 md:w-auto md:px-0">
            <ul className="flex">
              {nav.map((n) => (
                <li key={n.to}>
                  <Link
                    to={n.to}
                    aria-current={active(n.to) ? "page" : undefined}
                    className={cn("relative grid h-11 place-items-center px-2.5 whitespace-nowrap text-muted-foreground hover:text-foreground", active(n.to) && "font-semibold text-foreground")}
                  >
                    {n.label}
                    {active(n.to) && <motion.span layoutId={reduce ? undefined : "nav-mark"} className="absolute inset-x-2.5 bottom-1.5 h-[3px] rounded-full bg-accent" aria-hidden="true" />}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div className="flex items-center">
            <LangSwitch />
            <ThemeSwitch />
            {!demo && (
              <button type="button" onClick={() => setDemo(true)} className="h-11 px-2 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">{t.demo}</button>
            )}
          </div>
        </div>
      </header>
      <AnimatePresence mode="wait" initial={false}>
        <motion.main
          id="main"
          key={section}
          className="mx-auto max-w-6xl px-5 pt-10 pb-20 md:px-8 md:pt-14"
          initial={reduce ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduce ? undefined : { opacity: 0 }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
        >
          <Outlet />
        </motion.main>
      </AnimatePresence>
    </div>
  );
}
