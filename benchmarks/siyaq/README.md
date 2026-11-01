# siyaq benchmark: does it load the right docs?

siyaq adds doc sections to Claude's context when a prompt matches them. This benchmark checks
whether those sections help with the prompt, and whether siyaq stays quiet when nothing helps.
It runs offline in about a second: no model calls, nothing fetched.

```bash
python3 benchmarks/siyaq/bench.py                  # the report as Markdown, with every wrong prompt
python3 benchmarks/siyaq/bench.py --json           # the same as JSON, with every prompt
python3 benchmarks/siyaq/bench.py --check          # exit 1 if a prompt the baseline got right is now wrong
python3 benchmarks/siyaq/bench.py --save-baseline  # after a change that gets more right
```

`tests/test_siyaq_bench.py` runs `--check` in CI.

## What it measures

- **Precision.** Of all the sections siyaq loads across the 100 prompts, the share labelled
  relevant. #391's draft pass line is 70%.
- Found: labelled prompts where at least one relevant section loads.
- Quiet: prompts that need no docs ("merged", "go", "sort this list") where nothing loads.
- Tokens added per prompt, and time per prompt.

Each prompt runs through `rank.select_for_prompt`, the function siyaq's prompt hook calls, with
the default settings and nothing shown before (the first prompt of a session).

## The prompts and labels

`prompts.tsv` has 100 prompts:
- 25 need no docs: acknowledgements, ordinary coding requests, and the short prompts of a real
  session on this repo on 1 Nov 2026.
- 75 ask about Nexika: how a plugin works, settings, benchmarks, contributing. 7 are in Arabic.

Each labelled prompt lists the sections that would help answer it, as `source :: heading`. A
prompt counts as found if any one of them loads. All labels were written on 1 Nov 2026, before
siyaq was run on any prompt.

## The corpus

`corpus/` is a snapshot of the 30 docs siyaq indexes in this repo at `f20ce94`: 196 sections. The
files end in `.txt` so siyaq doesn't index them a second time in this repo. The benchmark copies
them into a throwaway git repo with their real names.

## Results (2026-11-01, siyaq at `f20ce94`)

| Measure | Result |
|---|---|
| Precision: loaded sections that are relevant | 68/244 = 28% |
| Labelled prompts with a relevant section loaded | 56/75 = 75% |
| Prompts that need nothing and got nothing | 13/25 = 52% |
| Tokens added per prompt (mean) | 357 |
| Time per prompt (median) | 0.2 ms |

siyaq misses the 70% pass line by far. It loads up to three sections for almost every prompt, so
even when the right one is there, two weaker ones come with it. It loaded three sections for
"what is the next issue" and for "write a unit test for parse_duration".

## Limits

- **Internal.** Nexika's own docs, and prompts and labels we wrote. siyaq's matching was not tuned
  on these prompts, but the same team wrote both.
- One person labelled every prompt. The labels are strict: a section counts only if it helps answer the prompt.
  A second labeller would disagree on some, mostly broad sections such as a plugin's opening.
- Only prompt matching is measured. siyaq also loads docs when Claude reads or edits a file. That is not
  covered here.
- Whether a wrong section makes Claude's work worse needs the agent benchmark.
