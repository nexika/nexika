# lawha benchmark

How does lawha compare with the leading tools that turn designs into frontend code? Two tasks, the same
inputs for every tool, scored by one script, with every tool's output kept here so anyone can check.

| Task | Tools | What it shows |
|---|---|---|
| **1. Figma to code**: one responsive Figma design (phone, tablet, desktop frames) | lawha (`/lawha:figma`), Figma's MCP server with Claude Code, Builder.io Visual Copilot | how closely each matches the design, and whether the page holds up on every screen |
| **2. Brief to page**: a written brief, no design | lawha (`/lawha:direct` → build → `check` → `elevate`), Anthropic's frontend-design skill | whether the page does what was asked, in English and Arabic, light and dark, and which one a blind judge prefers |

frontend-design is not in task 1 because it cannot read Figma, and Figma MCP and Builder.io are not in
task 2 because they need a design to start from. Each tool is compared where it is meant to be used.

## Results so far

### Task 2: brief to page (scored 2026-10-07)

| | frontend-design | lawha |
|---|---|---|
| Builds | yes | yes |
| Did the brief: parts / Arabic RTL / dark | 5/5 · yes · yes | 5/5 · yes · yes |
| Must fix (layout, phone, accessibility, motion, RTL) | 0 | 0 |
| Should fix | 6 (tap targets of 24–43px on phones) | 1 (layout shift on Arabic phones) |
| Colours hard-coded in components | 0 | 3 |
| Blind preference, 3 judges × English and Arabic | 0 | **6** ([details](runs/brief/preference.md)) |
| Time and tokens | about 5 minutes, 90k | about 34 minutes, 149k |

Both tools did what was asked:
- both pages built and did every part of the brief;
- neither has a must-fix problem.

The difference is in the design: every blind pick went to lawha. lawha costs about seven times the time, because it renders directions, checks and A/B-tests its own work.
[Full table](runs/brief/results.md).

### Task 1: Figma to code (scored 2026-10-07)

The design is the Responsive Travel Landing Page, with phone 430, tablet 1024 and desktop 1440 frames.

| | lawha | Figma MCP + Claude Code | Builder.io |
|---|---|---|---|
| Builds | yes | yes | **no** (npm install fails; builds with pnpm) |
| Looks like the design (430 / 1024 / 1440) | **95.6% / 98.5% / 96.2%** | 93.0% / 97.1% / 95.9% | 75.6% / 85.8% / 74.5%* |
| Must fix | **0** | 22 (14 tap targets, 8 accessibility) | 3* (1 tap target, 2 accessibility) |
| Should fix | 2 | 9 | 1* |
| Colours hard-coded in components | 28 | **19** | not counted (no `src/`) |

Both match the design closely, and lawha is 0.3 to 2.6 points closer.

The real difference is what each did with the design's own flaws:
- **Text contrast:** the pink and grey text fail WCAG contrast. Figma MCP copied them; lawha darkened them, at a small cost to pixel match.
- **Tap targets:** the nav links and the email field are under 24px tall. Figma MCP kept them; lawha made them big enough.
- **Keyboard:** Figma MCP left two scrolling regions that the keyboard cannot reach.

Figma MCP hard-coded fewer colours.

**Builder.io did not convert the design.** Its Figma plugin takes one frame (desktop), and the code it hands back
("Download code") is its AI agent's own page inside Builder's agent-native app template (React Router, server, database,
pnpm), not the starter:
- the text is mostly invented ("Plan a trip", "Find your next escape", "Amalfi Coast · from $1,240");
- the images are three Pexels stock photos, none from the design;
- it has 3 of the design's 9 sections (no partners, services, travel point, key features, testimonials or newsletter).

`npm install` crashes on its `package.json`, so the scorer records it as not building. \*The Builder.io figures are from
running it unchanged with its own `pnpm install`, `pnpm build` and `pnpm start`, then the same lawha check, outside the
scorer. One of its must-fix problems is the template's own "Configuration error" panel.

[Full table](runs/figma/results.md).

## Rules
- **Same start:** every run starts from [`starter/`](starter): Vite, React 19, TypeScript, Tailwind CSS 4.
- **Same prompt:** each tool gets the task's prompt ([`prompts/`](prompts)), with only its own method added.
- **One session, no human help:** no follow-up prompts except "continue", and nobody edits the code by hand.
- **Same model:** Claude Code runs (lawha, Figma MCP, frontend-design) use the same model.
- **A design no tool has seen:** task 1 uses a community file lawha was not tuned on. lawha's own showcase
  file is not used.

## Scoring

```sh
node score/score.mjs figma    # or: brief
```

Each run folder is installed, built and served. It is then measured with lawha's engine:
- Playwright renders the page;
- axe-core checks accessibility;
- pixelmatch compares it with the design.

The results are written to `runs/<task>/results.md` and `results.json`.

| Measure | How |
|---|---|
| Builds | `npm run build` passes |
| Looks like the design (task 1) | pixel comparison with each Figma frame at its width, with content aligned so one taller section does not hide everything below it |
| Did the brief (task 2) | the asked-for parts are there; `?lang=ar` is Arabic and right to left; dark mode changes the page |
| Layout | sideways scrolling, text cut off or overlapping, layout shift, at every width |
| Phone | tap targets (WCAG 2.2: 24px, 44px comfortable), text size |
| Accessibility | axe-core, WCAG 2.2 A and AA |
| Motion | motion that ignores "reduce motion", never stops, or animates layout |
| RTL (task 2) | left/right CSS that does not mirror, icons that point the wrong way in Arabic |
| Colours hard-coded | literal colours in components instead of design tokens |
| Blind preference (task 2) | judge agents see the two pages side by side in random order and pick one |

Problems are counted once per check and element, whatever the number of widths it appears at, and
they are shown as must fix / should fix.

**A known bias, stated plainly:** most measures come from lawha's own checks, and lawha's method runs
those checks while it builds. That is lawha's point (it checks its work; the others do not), but it
means low problem counts for lawha are expected. The measures that do not come from lawha's method are:
- whether the build passes;
- the pixel comparison with Figma;
- axe-core;
- whether the brief was done;
- the blind preference.

## The design (task 1)

**Responsive Travel Landing Page** from the Figma Community
([file](https://www.figma.com/community/file/1533371523286432790/responsive-travel-landing-page-free-figma-template-desktop-tablet-mobile)),
duplicated into a draft. The design's photos and renders are not committed (`public/design/` is
ignored); `lawha figma spec` writes them to reproduce the scores.

## Running the tools you need an account for

**Figma MCP** (about five minutes):
1. `cp -r benchmarks/starter benchmarks/runs/figma/figma-mcp && cd benchmarks/runs/figma/figma-mcp && npm install`
2. `claude mcp add --transport http figma https://mcp.figma.com/mcp`, then start `claude` there and authorise Figma when asked.
3. Paste the task 1 prompt with the three frame links, adding "Use the Figma MCP tools to read the design."
4. Let it work until it says it is done (type "continue" if it stops early). Do not edit anything.

**Builder.io Visual Copilot** (about five minutes):
1. `cp -r benchmarks/starter benchmarks/runs/figma/builder-io && cd benchmarks/runs/figma/builder-io && npm install`
2. In Figma, open the draft, run the **Builder.io: AI-Powered Figma to Code** plugin, and select the desktop frame (then tablet and phone, if it offers responsive export).
3. Choose React + Tailwind, click export, and run the `npx builder.io@latest ...` command it gives inside the folder. Accept its defaults.
4. Do not edit the code.

Then tell Claude, and it runs `node score/score.mjs figma`.
