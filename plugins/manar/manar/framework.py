"""Which web framework a project uses, so fixes go in the right files (see packs/<pack>.md)."""
from __future__ import annotations

import json
from pathlib import Path


def _deps(root: Path) -> set[str]:
    out: set[str] = set()
    for pkg in [root / "package.json", *root.glob("*/package.json")]:
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out |= set(data.get("dependencies", {})) | set(data.get("devDependencies", {}))
    return out


def detect(root: Path) -> dict:
    deps = _deps(root)
    if "next" in deps:
        app = next((p for p in ("app", "src/app") if (root / p).is_dir()), None)
        return {"framework": "nextjs", "pack": "nextjs", "variant": "app router" if app else "pages router",
                "where": app or next((p for p in ("pages", "src/pages") if (root / p).is_dir()), "pages")}
    if "astro" in deps:
        return {"framework": "astro", "pack": "astro", "variant": "",
                "where": "src/layouts, src/pages, public/"}
    for name, label in (("nuxt", "nuxt"), ("@sveltejs/kit", "sveltekit"), ("gatsby", "gatsby")):
        if name in deps:
            return {"framework": label, "pack": "generic", "variant": "", "where": ""}
    if deps & {"react", "vue", "@angular/core", "svelte"} and not deps & {"next", "astro", "nuxt"}:
        return {"framework": "spa", "pack": "generic", "variant": "client-rendered single-page app",
                "where": "index.html; consider pre-rendering: crawlers may see an empty page"}
    for csproj in [*root.glob("*.csproj"), *root.glob("*/*.csproj"), *root.glob("src/*/*.csproj")]:
        text = csproj.read_text(encoding="utf-8", errors="replace")
        if "Microsoft.NET.Sdk.Web" in text or "Microsoft.NET.Sdk.Razor" in text:
            folder = csproj.parent
            layouts = [p for p in ("Pages/Shared/_Layout.cshtml", "Views/Shared/_Layout.cshtml",
                                   "Components/App.razor", "Components/Layout/MainLayout.razor")
                       if (folder / p).is_file()]
            variant = "blazor" if any(p.endswith(".razor") for p in layouts) else "razor pages / mvc"
            prefix = folder.relative_to(root).as_posix()
            files = [p if prefix == "." else f"{prefix}/{p}" for p in layouts]
            return {"framework": "aspnet", "pack": "aspnet", "variant": variant,
                    "where": ", ".join(files) or csproj.relative_to(root).as_posix()}
    if (root / "_config.yml").is_file():
        return {"framework": "jekyll", "pack": "static", "variant": "GitHub Pages / Jekyll",
                "where": "_layouts/"}
    for folder in (".", "docs", "site", "public"):
        if (root / folder / "index.html").is_file():
            return {"framework": "static", "pack": "static", "variant": "plain HTML",
                    "where": f"{folder}/" if folder != "." else "./"}
    return {"framework": "unknown", "pack": "generic", "variant": "", "where": ""}
