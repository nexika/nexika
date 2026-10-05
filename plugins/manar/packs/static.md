# manar pack: static sites and GitHub Pages (plain HTML or Jekyll)

- **Plain HTML:** edit each page's `<head>`: unique `<title>`, `<meta name="description">`,
  `<link rel="canonical">` (absolute URL), Open Graph, viewport, `<html lang>`. Put shared
  JSON-LD (Organization/WebSite/SoftwareApplication) on the home page.
- **Jekyll (GitHub Pages):** use the `jekyll-seo-tag` plugin (`{% seo %}` in the head layout)
  and `jekyll-sitemap`; set `url`, `title`, `description`, `lang` in `_config.yml`.
- **robots.txt, sitemap.xml, llms.txt:** files at the site root (from `manar generate ...`).
  GitHub Pages serves them as-is; use the real domain (`https://user.github.io/repo` or a custom
  domain via `CNAME`).
- **A GitHub repository as a "site":** the README is the landing page AI tools read. Start it
  with one plain sentence saying what the project is and who it is for; set the repo
  description, topics and website link; add a docs site on GitHub Pages for more pages to cite.

## Verify
`manar audit <site folder> --base-url https://domain` before publishing, then `manar diff`.
