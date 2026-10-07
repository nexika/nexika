import { useEffect, useState } from "react";
import { copy, type Lang } from "./copy";
import { Sheet } from "./Sheet";

type Theme = "light" | "dark";

function readLang(): Lang {
  return new URLSearchParams(window.location.search).get("lang") === "ar" ? "ar" : "en";
}

function currentTheme(): Theme {
  const set = document.documentElement.dataset.theme;
  if (set === "light" || set === "dark") return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function hrefFor(lang: Lang) {
  const url = new URL(window.location.href);
  if (lang === "ar") url.searchParams.set("lang", "ar");
  else url.searchParams.delete("lang");
  return url.pathname + url.search + url.hash;
}

function ThemeIcon({ theme }: { theme: Theme }) {
  // Shows what you will switch to: a moon in light, a sun in dark.
  return theme === "light" ? (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  ) : (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function App() {
  const [lang] = useState<Lang>(readLang);
  const [theme, setTheme] = useState<Theme>(currentTheme);
  const t = copy[lang];
  const other: Lang = lang === "ar" ? "en" : "ar";
  const digits = (n: number) => n.toLocaleString(lang === "ar" ? "ar-EG" : "en-US");

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    document.title = lang === "ar" ? "قلم: محرّر هادئ للعربية والإنجليزية" : "Qalam: a calm editor for Arabic and English";
  }, [lang]);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (!document.documentElement.dataset.theme) setTheme(mq.matches ? "dark" : "light");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggleTheme = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("qalam-theme", next);
    } catch {
      /* storage unavailable: the choice lasts for this visit only */
    }
    setTheme(next);
  };

  return (
    <>
      <a className="skip" href="#main">
        {lang === "ar" ? "انتقل إلى المحتوى" : "Skip to content"}
      </a>

      <header className="wrap top">
        <a className="mark" href={hrefFor(lang)} aria-label={lang === "ar" ? "قلم، الصفحة الرئيسية" : "Qalam, home"}>
          <span>{lang === "ar" ? "قلم" : "Qalam"}</span>
          <span className="mark-ar" aria-hidden="true">
            {lang === "ar" ? "Qalam" : "قلم"}
          </span>
        </a>
        <nav className="top-links" aria-label={lang === "ar" ? "أقسام الصفحة" : "Page sections"}>
          <a href="#features">{t.nav.features}</a>
          <a href="#how">{t.nav.how}</a>
          <a href="#pricing">{t.nav.pricing}</a>
        </nav>
        <div className="top-tools">
          <a className="lang-switch" href={hrefFor(other)} lang={other} hrefLang={other} aria-label={t.nav.switchLabel}>
            {t.nav.switchTo}
          </a>
          <button
            type="button"
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? t.nav.themeLight : t.nav.themeDark}
          >
            <ThemeIcon theme={theme} />
          </button>
        </div>
      </header>

      <main id="main">
        <section className="wrap hero" aria-labelledby="hero-line">
          <h1 id="hero-line" className="hero-line">
            {t.hero.line}
          </h1>
          <div className="hero-echo-wrap">
            <p className="hero-echo write" lang={other} dir={other === "ar" ? "rtl" : "ltr"}>
              {t.hero.echo}
            </p>
          </div>

          <div className="hero-foot">
            <div>
              <p className="hero-sub">{t.hero.sub}</p>
              <div className="hero-actions">
                <a className="btn btn-primary" href="#start">
                  {t.hero.primary}
                </a>
                <a className="btn btn-quiet" href="#pricing">
                  {t.hero.secondary}
                </a>
              </div>
              <p className="hero-free">{t.hero.free}</p>
            </div>
            <Sheet sheet={t.sheet} digits={digits} />
          </div>
        </section>

        <section id="features" className="section" aria-labelledby="features-h">
          <div className="wrap">
            <h2 id="features-h" className="h2">
              {t.features.heading}
            </h2>
            <ul className="features">
              {t.features.items.map((f) => (
                <li key={f.title} className="feature">
                  <h3 className="feature-title">{f.title}</h3>
                  <p className="feature-body">{f.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="how" className="section" aria-labelledby="how-h">
          <div className="wrap">
            <h2 id="how-h" className="h2">
              {t.how.heading}
            </h2>
            <ol className="steps">
              {t.how.steps.map((s) => (
                <li key={s.title} className="step">
                  <h3 className="step-title">{s.title}</h3>
                  <p className="step-body">{s.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="section" aria-label={lang === "ar" ? "رأي كاتبة" : "What a writer says"}>
          <div className="wrap">
          <figure className="quote">
            <blockquote style={{ margin: 0 }}>
              <p className="quote-original" lang="ar" dir="rtl">
                {t.quote.original}
              </p>
              {t.quote.translation && (
                <p className="quote-translation" lang="en" dir="ltr">
                  {t.quote.translation}
                  <span className="quote-note">{t.quote.translatedNote}</span>
                </p>
              )}
            </blockquote>
            <figcaption className="quote-by">
              <span className="quote-name">{t.quote.name}</span>
              <span className="quote-role">{t.quote.role}</span>
            </figcaption>
          </figure>
          </div>
        </section>

        <section id="pricing" className="section" aria-labelledby="pricing-h">
          <div className="wrap">
            <div className="price-head">
              <h2 id="pricing-h" className="h2">
                {t.pricing.heading}
              </h2>
              <p className="price-sub">{t.pricing.sub}</p>
            </div>
            <div className="plans">
              {(["free", "pro"] as const).map((key) => {
                const plan = t.pricing[key];
                return (
                  <article key={key} className={key === "pro" ? "plan plan-pro" : "plan"} aria-labelledby={`plan-${key}`}>
                    <h3 id={`plan-${key}`} className="plan-name">
                      {plan.name}
                    </h3>
                    <p className="plan-for">{plan.for}</p>
                    <p className="plan-price">
                      <span className="plan-amount">{plan.price}</span>
                      <span className="plan-per">{plan.per}</span>
                    </p>
                    <ul className="plan-list">
                      {plan.items.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                    <a className={key === "pro" ? "btn btn-primary" : "btn btn-quiet"} href="#start">
                      {plan.cta}
                    </a>
                    {"note" in plan && <p className="plan-note">{plan.note}</p>}
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section id="start" className="final" aria-labelledby="final-h">
          <div className="wrap">
            <h2 id="final-h" className="final-line">
              {t.cta.heading}
            </h2>
            <p className="final-body">{t.cta.body}</p>
            <a className="btn btn-primary" href="#start">
              {t.cta.button}
            </a>
          </div>
        </section>
      </main>

      <footer className="wrap foot">
        <span>{t.footer.made}</span>
        <nav aria-label={lang === "ar" ? "روابط" : "Links"}>
          <a href="#">{t.footer.privacy}</a>
          <a href="#">{t.footer.terms}</a>
          <a href="mailto:hello@example.com">{t.footer.contact}</a>
        </nav>
      </footer>
    </>
  );
}
