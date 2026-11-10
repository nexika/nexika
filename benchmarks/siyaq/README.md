# siyaq benchmark: does it load the right docs?

siyaq adds doc sections to Claude's context when a prompt or a file Claude reads or edits matches
them. This benchmark checks whether those sections help, and whether siyaq stays quiet when nothing
helps.
It runs offline in about a second: no model calls, nothing fetched.

```bash
python3 benchmarks/siyaq/bench.py                  # the report as Markdown, with every wrong prompt
python3 benchmarks/siyaq/bench.py --json           # the same as JSON, with every prompt
python3 benchmarks/siyaq/bench.py --check          # exit 1 if a prompt the baseline got right is now wrong
python3 benchmarks/siyaq/bench.py --save-baseline  # after a change that gets more right
python3 benchmarks/siyaq/bench.py --set heldout    # the 40 held-out prompts, same options
python3 benchmarks/siyaq/bench.py --set files      # 96 files read or edited, same options
```

`tests/test_siyaq_bench.py` runs `--check` on all three sets in CI.

It measures prompt matching as it works when turned on. Since #455 it is off by default (see
"What we changed").

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

`heldout.tsv` has 40 more prompts (12 need no docs, 3 are in Arabic), labelled the same way on
1 Nov 2026 before any ranking change was tried. Use it to check a change; never tune on it.

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

### Held-out set (2026-11-01, siyaq at `20678b4`)

| Measure | Result |
|---|---|
| Precision | 21/95 = 22% |
| Labelled prompts with a relevant section loaded | 17/28 = 61% |
| Prompts that need nothing and got nothing | 5/12 = 42% |

## What we changed (#455)

We tried to raise precision by changing siyaq's ranking: a bonus for prompt words in a section's own
and parent headings, a cutoff relative to the best match, stricter rules for matches in the body
only, and fewer slots. Tuned on the 100 prompts, the best setting reached 56% precision with 53 of
75 found. On the 40 held-out prompts it reached 30% (from 22%) and found 12 of 28 (from 17). Most of
the gain was fitted to the tuning prompts, and no setting met all three targets in #455 even there.

So prompt matching is now opt-in: `"prompts": true` in `.siyaq.json`, or `SIYAQ_PROMPTS=on`. Docs
still load when Claude reads or edits a file, measured below.

## File matching (2026-11-10, siyaq at `97b1de1`)

When Claude reads or edits a file, siyaq loads the sections whose prose names that file, or a
folder of at most 15 files that holds it (`rank.select_for_path`). This is on by default.

`files.tsv` has 96 files that Claude read or edited on this repo, taken from the Read and Edit
calls in the session logs on this machine (all files that still existed at `f20ce94`). Each is
labelled with up to three sections that help work on that file, or `-` for none.
`files-f20ce94.txt` lists every file of the repo at the snapshot: the benchmark creates them empty,
because a doc's path only becomes a trigger when the file or folder exists.

A fresh agent wrote the labels. It read the files and the docs, and was told not to open siyaq's
code, so it labelled without knowing how siyaq matches files. Nothing was changed after the first
run.

| Measure | Result |
|---|---|
| Precision: loaded sections that are relevant | 36/56 = 64% |
| Labelled files with a relevant section loaded | 35/86 = 41% |
| Files that need nothing and got nothing | 6/10 = 60% |
| Tokens added per file (mean) | 64 |
| Time per file (median) | 0.1 ms |

File matching is much more precise than prompt matching (64% against 28%), and stays small: 64
tokens per file, against 357 per prompt. It is still under the 70% pass line, and it misses more
than half the files a section would help with. 55 of the 96 are wrong: 51 labelled files with no
relevant section, and 4 files that need nothing but got something. 48 of the 51 loaded nothing at all:

- **Plugin code (25).** `plugins/haris/haris/classify.py`, `plugins/hafiz/hafiz/capture.py` and
  others. The READMEs describe what the code does but rarely name its files: 16 of the 126 path
  triggers point inside a plugin (READMEs aside), and none of them is one of these 25 files.
- **Skills (7).** No doc names a `SKILL.md`.
- **Tests (10).** No doc names these test files.
- **Benchmark code (5).** `benchmarks/hafiz/bench.py`, `benchmarks/routing/bench.py`: their READMEs
  name them only in command examples, inside code blocks, which siyaq skips on purpose.
- `common/background.py`.

8 of the 20 extra sections are the root README's "How we know it works", which links to many
benchmark files.

## Limits

- **Internal.** Nexika's own docs, and prompts and labels we wrote. siyaq's matching was not tuned
  on these prompts, but the same team wrote both.
- One person labelled every prompt. The labels are strict: a section counts only if it helps answer the prompt.
  A second labeller would disagree on some, mostly broad sections such as a plugin's opening.
- One agent labelled every file. It labelled more files than expected (86 of 96), and it saw the
  head of `plugins/siyaq/siyaq/index.py` while reading the case files.
- The 96 files come from the session logs left on this machine, which over-represent haris, hafiz
  and the benchmarks.
- Whether a wrong section makes Claude's work worse needs the agent benchmark.
