# Task 1: Figma to code

Give every tool this same prompt, in a copy of `benchmarks/starter` (React 19, TypeScript, Tailwind CSS 4),
with only the tool's own method added (see each tool's notes below). One session, no human edits to
the code, no follow-up prompts except "continue" if the tool stops before it says it is done.

> Build this Figma design as a responsive page in this app (React 19, TypeScript, Tailwind CSS 4).
> The design has three frames: phone FRAME_PHONE, tablet FRAME_TABLET and desktop FRAME_DESKTOP.
> Match the design at each of those widths, and keep it usable at every width in between. Use the
> design's text, images and icons. Do not ask me questions. When you are done, `npm run build` must pass.

The links are the frames in the benchmark file (see README, "The design").

## Each tool's method
- **lawha:** in Claude Code with the nexika marketplace's lawha plugin, start the prompt with `/lawha:figma`.
- **Figma MCP:** in Claude Code with Figma's MCP server connected (remote: `claude mcp add --transport http figma https://mcp.figma.com/mcp`), add "Use the Figma MCP tools to read the design." Same model as the other runs.
- **Builder.io Visual Copilot:** in Figma, run the Builder.io plugin on each frame, choose React + Tailwind, and use its code export (`npx builder.io@latest ...` command it gives) in the run folder. If it offers to adapt the code to the codebase, accept its default. No other edits.
