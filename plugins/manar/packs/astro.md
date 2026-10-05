# manar pack: Astro

- **Head tags:** one SEO component (e.g. `src/components/SEO.astro`) used by the base layout:
  `<title>`, description, canonical (`new URL(Astro.url.pathname, Astro.site)`), Open Graph.
  Set `site: "https://domain"` in `astro.config.mjs` (needed for canonical and sitemap URLs).
- **Language:** `<html lang={lang} dir={lang === "ar" ? "rtl" : "ltr"}>` in the base layout.
- **Sitemap:** the official `@astrojs/sitemap` integration (`astro add sitemap`).
- **robots.txt / llms.txt:** static files in `public/` (from `manar generate robots|llms`), or an
  endpoint `src/pages/robots.txt.ts` if it must use `site`.
- **JSON-LD:** `<script type="application/ld+json" set:html={JSON.stringify(data)} />` in the layout
  (Organization/WebSite) and in content pages (Article).
- **Rendering:** Astro ships HTML by default; keep content out of client-only islands.

## Verify
`astro build`, then `manar audit dist --base-url https://domain`, then `manar diff`.
