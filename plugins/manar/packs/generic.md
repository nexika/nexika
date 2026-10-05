# manar pack: other frameworks

Find where the framework renders the document head (a root layout, document or template) and
where it serves static files. Then apply, in that order:

1. Server-rendered or pre-rendered HTML for every page that should be found (client-only
   rendering is the biggest blocker for AI fetchers).
2. Per-page title, description, canonical (absolute), Open Graph; `<html lang>`.
3. robots.txt, sitemap.xml, llms.txt at the site root (`manar generate ...`).
4. JSON-LD for the entity on the home page; Article/Product on content pages.

Nuxt: `useHead` / `useSeoMeta`, `@nuxtjs/sitemap`. SvelteKit: `<svelte:head>`, prerender routes.
Gatsby: the Head API, `gatsby-plugin-sitemap`. SPA (React/Vue/Angular without SSR): add
pre-rendering or move content pages to an SSR/SSG framework.
