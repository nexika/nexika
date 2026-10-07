# Results: Figma to code

Scored 2026-10-07 at 430, 768, 1024, 1280, 1440px. Problems are counted once per check and element (must fix / should fix).

| Tool | Builds | Looks like the design (430 / 1024 / 1440) | layout | phone | accessibility | motion | Colours hard-coded |
|---|---|---|---|---|---|---|---|
| lawha | yes | 95.6% / 98.5% / 96.2% | 0 / 0 | 0 / 2 | 0 / 0 | 0 / 0 | 28 |
| figma-mcp | yes | 93% / 97.1% / 95.9% | 0 / 0 | 14 / 9 | 8 / 0 | 0 / 0 | 19 |
| builder-io | **no** | – / – / – | – | – | – | – | – |

builder-io: npm install failed (npm crashes: 'Cannot read properties of null (reading edgesOut)'); the download is Builder's pnpm-based agent-native app, not the starter. Outside the scorer, unchanged: pnpm install + pnpm build pass, and pnpm start serves the page; lawha check on it gives looks 75.6% / 85.8% / 74.5% (430/1024/1440), must fix 3 (1 tap target, 2 accessibility: contrast, zoom disabled), should fix 1; the failing tap target is the template's own 'Configuration error' panel. Builder.io was given the desktop frame only (its plugin takes one frame), and its AI agent rewrote the page: invented text, three Pexels stock photos, 3 of the design's 9 sections. Colours hard-coded reads 0 only because the counter scans src/, which this project does not have.
