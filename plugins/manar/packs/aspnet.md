# manar pack: ASP.NET Core (Razor Pages, MVC, Blazor)

## Head tags
- **Razor Pages / MVC:** in `Pages/Shared/_Layout.cshtml` or `Views/Shared/_Layout.cshtml`:
  `<title>@ViewData["Title"] | Brand</title>`, `<meta name="description" content="@ViewData["Description"]">`,
  a canonical link built from a configured base URL plus `Context.Request.Path` (avoid trusting the
  Host header), and Open Graph. Each page sets `ViewData["Title"]` / `ViewData["Description"]`.
- **Blazor (.NET 8+):** `<PageTitle>` and `<HeadContent>` in each page; `<HeadOutlet />` in `App.razor`.
  Use static server rendering or prerendering for indexable pages so the HTML contains the text.
- **Language:** `<html lang="en">` in the layout (`lang="ar" dir="rtl"` with request localization).

## robots.txt, sitemap.xml, llms.txt
- Static files in `wwwroot/` (served by `app.UseStaticFiles()` / `MapStaticAssets()`), generated
  with `manar generate robots|sitemap|llms`.
- Dynamic sitemap: a minimal endpoint, e.g.
  `app.MapGet("/sitemap.xml", (...) => Results.Content(xml, "application/xml"));` built from your
  routes or database.

## JSON-LD
Serialize with `System.Text.Json` in the layout or page:
`<script type="application/ld+json">@Html.Raw(JsonSerializer.Serialize(data))</script>`.
Never build it by string concatenation with user data.

## Other
- `app.UseHttpsRedirection()` and HSTS in production; one canonical host (redirect www/non-www).
- `app.UseResponseCompression()` and output caching help performance signals.

## Verify
`dotnet run`, then `manar audit https://localhost:5001 --allow-local` (or the published `wwwroot`
output), then `manar diff`.
