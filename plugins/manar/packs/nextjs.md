# manar pack: Next.js

Check the version in package.json and whether the project uses the **App Router** (`app/`) or the
**Pages Router** (`pages/`). Use Next.js's own APIs; never hand-write `<head>` tags in the App Router.

## App Router
- **Titles, descriptions, Open Graph, canonical:** `export const metadata` (static) or
  `export async function generateMetadata()` (dynamic) in `layout.tsx` / `page.tsx`.
  Set `metadataBase: new URL("https://domain")` once in the root layout so relative URLs become
  absolute; set `alternates: { canonical: "/path" }` per page; `title: { template: "%s | Brand" }`.
- **Language:** `<html lang="en">` in `app/layout.tsx` (`lang="ar" dir="rtl"` for Arabic routes).
- **robots.txt:** `app/robots.ts` returning `MetadataRoute.Robots` (rules + `sitemap`); mirror
  the policy from `manar generate robots`.
- **sitemap.xml:** `app/sitemap.ts` returning `MetadataRoute.Sitemap` from your routes / CMS.
- **llms.txt:** a static file in `public/llms.txt` (from `manar generate llms`), or a route handler
  `app/llms.txt/route.ts` returning `text/plain` if it must be dynamic.
- **JSON-LD:** render `<script type="application/ld+json" dangerouslySetInnerHTML={{ __html:
  JSON.stringify(data) }} />` in the page or root layout (Organization/WebSite in the root layout).
- **Rendering:** keep content pages server-rendered or statically generated; `"use client"` only for
  interactive parts, so the HTML that crawlers receive contains the text.

## Pages Router
- `next/head` in each page (`<title>`, meta, canonical), `_document.tsx` for `<html lang>`.
- `public/robots.txt`, `public/sitemap.xml` (or generate at build), `public/llms.txt`.
- Prefer `getStaticProps` / `getServerSideProps` over client-only fetching for indexable content.

## Verify
`next build && next start`, then `manar audit http://localhost:3000 --allow-local`, then `manar diff`.
