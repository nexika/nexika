# Nexika's benchmarks: methods, results and limits

This page collects every Nexika benchmark in one place. For each one it says:
- what it measures;
- how it was run;
- what it found, with the date and the Nexika version;
- what it cannot show.

Each benchmark has its own page with the full method, every table and the commands to run it again.
This page links to them rather than repeating them.

Last updated 28 Oct 2026. The latest release is Nexika 0.4.0 (11 Oct 2026). We update this page with
each release.

## How to read the numbers

- **Arms.** Most benchmarks do the same work two ways and compare them. Arm A is usually Claude Code
  alone. Arm B is Claude Code with Nexika.
- **Paired.** Each task runs in both arms, and the arms are compared task by task.
- **pts** means percentage points: going from 71% to 74% is +3 pts.
- **The 95% interval** is the range the real difference probably lies in. When it includes 0, this
  sample cannot tell the arms apart. We call that "not significant", and we say so each time.
- **p** comes from an exact sign test on the tasks where the arms disagree. A p below 0.05 is the usual
  line for "probably not chance". A p above it means the result could easily be chance.
- Tokens are the units a model reads and writes. One is roughly three quarters of a word.
- CI (continuous integration) is the service that builds and tests a project after every change.
- A commit (one saved change in the project's history) is named by a short code like `22c20fb`.

## Two kinds of result

We keep two lists apart. The main [README](../README.md) makes claims only from the first. It shows
the second only under "our own tests".

### Tested on outside material

These used tasks we did not write, graded by tools we did not build. They are still our own runs:
nobody outside the project has repeated them yet.

| Claim | Evidence |
|---|---|
| Nexika has **not** been shown to help Claude solve more programming tasks. | Ahead in all three pilots, by +15, +3 and +5 pts, but no interval excludes 0 ([agent benchmark](#agent-benchmark-claude-code-alone-vs-with-nexika)). |
| With Nexika, Claude runs the project's tests more often. | +16 pts (+8 to +25) in pilot 2 and +9 pts (+2 to +16) in pilot 3. |
| With itqan's 0.4 note, Claude runs the tests of the files it changed far more often. | 86% of tasks, up from 63%: +23.5 pts (+14.3 to +32.7). Solve rate and regressions did not move beyond noise. |
| Nexika costs about twice as much per task. | $0.06 against $0.12 per task in pilot 2; $0.07 against $0.14 in pilot 3. |
| Nexika 0.4.0 makes the start of every session smaller than 0.3.0 did. | 7,381 tokens added to the first request, down from 9,840 ([session start](#session-start-size)). |
| The 0.4 trims, and bayan's shorter note for 0.5, did not make the work measurably worse. | Solve rate, regressions and test running held within noise in both guardrail runs ([guardrails](#guardrail-runs-did-a-change-make-the-work-worse)). |
| lawha turned one Figma design into a page as close to the design as Figma's own tool, with fewer accessibility problems. | 95.6% / 98.5% / 96.2% against 93.0% / 97.1% / 95.9%; axe-core found 0 must-fix accessibility problems on lawha's page and 8 on the other ([lawha](#lawha-design-to-code-and-brief-to-page)). |

"Ran the tests" is read from each session's log by our own rule. The same rule applies to every arm.

### Internal experiments

These use test sets we wrote and labelled, or tools we tuned on the same material. They guide our work
and catch regressions. They are not proof of how Nexika does on other people's work.

| Result | Why it is internal |
|---|---|
| haris stops all 799 harmful commands at its standard setting and asks about 9 of 545 ordinary ones ([haris](#haris-harmful-commands-stopped-and-false-alarms)). | We wrote and labelled the cases, under haris's own policy, many while fixing haris. |
| tabib names the right kind of failure for 167 of 170 failed CI runs, and the right failing test in all 111 runs that have one ([tabib](#tabib-the-cause-of-a-failed-ci-run)). | tabib was tuned on 150 of the runs. We labelled every run by hand. |
| After a restart told only "carry on with the plan", Claude finished the open work in 3 of 3 runs with hafiz and 0 of 3 without ([hafiz](#hafiz-continuing-after-a-break)). | Our own tasks, and 3 runs per arm. |
| Blind judges preferred lawha's page to Anthropic's frontend-design skill 6 times out of 6 ([lawha](#lawha-design-to-code-and-brief-to-page)). | The judges were Claude models using lawha's own judge instructions. |

## Agent benchmark: Claude Code alone vs with Nexika

[Full page](agent/README.md) · tracking issue #333

**What it measures.** Whether Nexika helps Claude finish real programming tasks: more tasks solved,
fewer existing tests broken, and at what cost.

**How.**
- The tasks come from [SWE-bench Verified](https://www.swebench.com/): real bug reports from public
  Python projects, each with hidden tests. We did not write them.
- Claude sees only the bug report. It works alone with `claude -p`, with nobody to answer questions.
- Each task runs in its own fresh container. Arm A has no plugins. Arm B loads all 12 Nexika plugins.
  Everything else is the same: model, prompt, budget and time limit.
- The official SWE-bench grader then runs the hidden tests in a new container. A task is **solved**
  when its target tests pass. A **regression** is a test that passed before and fails after.
- Model: Sonnet (the sessions report `claude-sonnet-5-5`). Claude Code 2.1.296 for every run up to
  11 Oct, and 2.1.312 for the 28 Oct guardrail run.

### The three pilots

| Pilot | Date | Nexika | Tasks × runs | Solved: A → B | B − A (95% interval) | p | Cost |
|---|---|---|---|---|---|---|---|
| 1 | 9 Oct 2026 | between 0.2.0 and 0.3.0 (`8dd3f27`) | 20 × 1 | 70% → 85% | +15 pts (+0 to +30) | 0.25 | $2.97 |
| 2 | 9–10 Oct 2026 | between 0.2.0 and 0.3.0 (`3ddb676`) | 100 × 1 | 71% → 74% | +3 pts (−2 to +9) | 0.51 | $40.32 |
| 3 (hard tasks only) | 10 Oct 2026 | between 0.2.0 and 0.3.0 (`cd45efc`) | 42 × 3 | 54% → 59% | +5 pts (−4 to +13) | 0.33 | $38.41 |

**Solving: not significant.** B was ahead in every pilot, but no interval excludes 0 and every p is
above 0.05. If Nexika helps Claude solve tasks, the effect is small, a few points at most.

Other measures, A against B:

| Measure | Pilot 2 (100 tasks) | Pilot 3 (42 hard tasks × 3) |
|---|---|---|
| Ran the tests | 58% → 74%: +16 pts (+8 to +25) | 81% → 90%: +9 pts (+2 to +16) |
| Regressions | 2% → 4%: +2 pts (+0 to +5), not significant | 6% → 8%: +2 pts (−2 to +5), not significant |
| Cost per task | $0.06 → $0.12 | $0.07 → $0.14 |
| Cost per solved task | $0.09 → $0.16 | $0.13 → $0.23 |
| Tokens per task | 120.5k → 193.6k | 156.9k → 254.4k |

In pilot 1, Claude ran the tests in 6 of 20 runs without Nexika and 12 of 20 with it.

**One plugin at a time (pilot 2).** Three more arms loaded a single part of Nexika. None moved the solve
rate beyond noise: haris+barq 73%, itqan 72% and siyaq 72%, against 71% for A. itqan raised test
running the most, from 58% to 67%.

**A lean Nexika (pilot 3).** A fourth arm left out lawha, prof, manar and bayan. It ran the tests as
often as B (91% against 90%) at about 40% less extra cost. It solved 52% of runs, against 54% for A
and 59% for B. B against lean was +6.3 pts (−0.0 to +13.5, p = 0.27): borderline, not significant.

**itqan's test note (#344, PR #352, 10–11 Oct 2026).** itqan's session note gained one line. It says:
before saying a change is done, run the test that shows it works and the tests of every file you
edited. An itqan-only arm ran pilot 2's 100 tasks with the new note (about $8.60). It is compared
with pilot 2's itqan arm:

| Per task | itqan before | itqan after | after − before (95% interval) |
|---|---|---|---|
| Ran the edited files' tests | 63% | 86% | +23.5 pts (+14.3 to +32.7) |
| Solved | 72% | 74% | +2.0 pts (−5.0 to +9.0), p = 0.77, not significant |
| Regressions | 4% | 3% | −1.0 pt (−5.0 to +2.0), not significant |
| Cost | $0.078 | $0.086 | +$0.008 (+$0.001 to +$0.015) |

The note shipped in Nexika 0.4.0. Its goal was fewer regressions. With 2 to 4 regressions in 100
tasks, this sample cannot show that, either way.

### Guardrail runs: did a change make the work worse?

When a change saves tokens, it must not cost quality. Each run below compares two versions of
Nexika (both arm B) on pilot 2's 100 tasks, one run each, paired by task. The rule: solve rate,
regressions and test running must hold within noise.

| | #336 and #345: shorter session text | #393: bayan's short note, prof quiet |
|---|---|---|
| Date | 11 Oct 2026 | 28 Oct 2026 |
| Before → after | `b20fcf5` → `15baa41`, both shipped in 0.4.0 | main after 0.4.0 (`22c20fb`) → PR #429 (`f1e195f`), for 0.5 |
| Tasks paired | 98 | 98 |
| Solved | 66% → 73%: +7.1 pts (+0.0 to +14.3), p = 0.12 | 77% → 74%: −2 pts (−7 to +3), p = 0.73 |
| Regressions | 1% → 3%: +2.0 pts (+0.0 to +5.1), p = 0.50 | 5% → 5%: +0 pts (−4 to +4), p = 1.0 |
| Ran the tests | 63% → 79%: +15.3 pts (+6.1 to +24.5), p = 0.003 | 84% → 87%: +3 pts (−3 to +9), p = 0.51 |
| First request | −2,266 tokens (median paired difference) | −334 tokens (mean); −352 (median) |
| Tokens per task | +12.8k (−9.9k to +37.0k) | −10.2k (−40.5k to +19.1k) |
| Cost per task | +$0.005 (−$0.003 to +$0.014) | +$0.00 (−$0.01 to +$0.01) |
| Cost of the run | about $21 | $23.40 |
| Verdict | passes | holds, within noise |

- **#336 and #345.** Solve rate and regressions moved within noise. Test running rose, and that rise is
  significant (p = 0.003). This run cannot say why. The session start shrank, but Claude took 0.7 more
  turns, so a task did not get cheaper.
- **#393.** Solve rate is 2 points lower in this sample. The interval runs from −7 to +3, and only 8
  tasks differ (3 against 5). So a real 2-point loss and a 3-point gain are both possible. In these
  containers lawha, manar and prof print nothing in either arm, so this run tests only bayan's shorter
  note. In B-393's arm, two tasks failed their gold-patch check and were left out (98 of 100 paired).

### Limits

- **Sample size.** With 100 tasks and one run each, the interval on the solve rate is about ±5 pts. To
  show a 5-point gain clearly would take several hundred task-runs per arm. Sizing that run is #395.
- **One kind of work.** SWE-bench is bug fixing with nobody watching. haris's guarding, hafiz's memory
  across sessions, tabib's CI reading, prof, lawha, manar and bayan do their main work elsewhere.
- **Only the always-on part of Nexika.** No arm called a skill or an agent on its own. So itqan's
  `/itqan:ship` and the other workflows were never tested here.
- **Runs at different times.** The two arms of each guardrail run ran one after the other, not side
  by side, on a busy machine. The itqan "before" arm is pilot 2's run from a day earlier.
- **Empty start.** Every container starts with no Nexika data, so plugins that need history (hafiz,
  prof, siyaq's knowledge) start with nothing.
- **Unattended asks.** With nobody to answer, a haris "ask" counts as a refusal. How often that
  happened, and what it cost, is measured in #386.

## Session start size

[Full page](agent/context-0.4.md) · issue #392

**What it measures.** How many tokens each plugin adds to the first request of a session, before any
work. That text is paid for on every request.

**How.** One short session per arm, on one task (`django__django-11848`), Sonnet, one turn, Claude Code
2.1.300. The arms: no plugins, each plugin alone, and all twelve. Measured on 15 Oct 2026 for the
`nexika-v0.3.0` and `nexika-v0.4.0` tags. Cost $0.61.

**Result.** Without plugins, the first request is 17,170 tokens. Nexika 0.3.0 adds 9,840 tokens (57%).
Nexika 0.4.0 adds 7,381 (43%): 2,459 fewer. Every plugin got smaller. lawha, prof and manar account for
most of the saving.

**Limits.**
- This is the first request only. A whole task did not get cheaper (see the guardrail runs above).
- One session per arm. The first request is nearly the same every time, but not always. One 0.3.0
  session came out 62 tokens below no plugins; run again, it gave +517. The table uses the second.

## hafiz: continuing after a break

[Full page](hafiz/README.md) · issue #348

**What it measures.** Whether work goes on correctly after Claude Code shortens the conversation
(`/compact`) or a new session starts. Three scores from 0 to 1: decisions kept, open work done, and no
work redone. Continuity is their mean.

**How.** A small book-catalogue project we wrote, with planned work in steps and decisions stated once,
early. The work is broken in the middle by a `/compact` or a new session. Hidden tests score the end
result. Arm `plain` has no plugins; arm `hafiz` loads only hafiz. Sonnet, 3 tasks × 3 runs per arm.

**Results.**

| Version | Date | Nexika | plain | hafiz | Cost |
|---|---|---|---|---|---|
| 1: one `/compact` per task | 10 Oct 2026 | hafiz at `bd5f052`, between 0.3.0 and 0.4.0 | 0.89 | 0.89 | $12.32 |
| 2: two compactions or a restart | 11 Oct 2026 | hafiz at `6cb302c`, shipped in 0.4.0 | 0.82 ± 0.17 | 0.92 ± 0.10 | $14.64 |

(± is one standard deviation.)

- **Version 1 could not tell the arms apart.** The tasks were too easy: Claude Code's own summary carried
  every decision and every open step.
- **Version 2, by task.** After two compactions in the same session, hafiz added nothing (1.00 plain,
  0.97 hafiz). When the new session's prompt listed the steps left, both arms scored 0.80. When the new
  session was told only "carry on with the plan", hafiz scored 1.00 and plain 0.67. Claude finished
  the open work in 3 of 3 runs with hafiz, and in 0 of 3 without.
- **The cost.** hafiz's note after a break is about 1,000 characters. It added about 25% more tokens
  after the break and 7% more money.

**Limits.**
- 9 runs per arm. The overall gap (+0.10) is within one standard deviation, and it comes from one task.
  It is a clear direction, not a proven effect.
- Our own project and tasks. The decisions were reworded after hafiz's last changes so hafiz was not
  tuned to them, but the tasks are still ours.

## haris: harmful commands stopped, and false alarms

[Full page](haris/README.md)

**What it measures.** How often haris stops a harmful command (recall), and how often it interrupts an
ordinary one (a false alarm). It is measured for each setting: relaxed, standard and strict.

**How.** Labelled commands, each judged in a throwaway folder and never run. They come from four places:
- haris's own test list;
- commands that web pages or issues tell an agent to run;
- real commands from the agent benchmark and the two-week trial (#53);
- short sessions where harm is split over several steps.

No model is called; the whole run takes seconds. CI fails if a harmful case that haris stopped before is
let through.

**Results.**

| Date | haris | Cases | Harmful stopped, standard | False alarms: relaxed / standard / strict |
|---|---|---|---|---|
| 10 Oct 2026 | after #342 | 900 | 484/486 = 99.6% | 2.4% / 3.1% / 12.6% |
| 11 Oct 2026 | after #343, the numbers given for 0.4.0 | 1,180 | 687/687 = 100% | 6/493 = 1.2% / 9/493 = 1.8% / 71/493 = 14.4% |
| 28 Oct 2026 | main after 0.4.0 | 1,344 | 799/799 = 100% | 6/545 = 1.1% / 9/545 = 1.7% / 71/545 = 13.0% |

Relaxed stops fewer harmful commands by design: 742 of 799 (92.9%) on 28 Oct. A decision takes about
0.3 ms (median).

**Limits.**
- We wrote and labelled most cases, many of them while fixing the very gaps they test. No outside
  attacker has tried to get past haris yet (#396).
- "Harmful" follows haris's own policy. Someone with a different policy would label some cases
  differently.
- In a real unattended session, an "ask" stops the agent. What that costs on real tasks is #386.

## tabib: the cause of a failed CI run

[Full page](tabib/README.md)

**What it measures.** When a CI run fails, does tabib name the right kind of failure? The kinds include
a code bug, a flaky test, the infrastructure and a dependency. It also checks that tabib names the
right failing test, file and line.

**How.** 170 real failed CI runs from six public projects, each labelled by hand. tabib's own triage
runs on a stored, redacted copy of each log. No model is called, and it runs offline in seconds. CI
fails if a run tabib got right before is now wrong.

**Results.** Measured on 10 Oct 2026 with tabib 0.3.0 plus #360, #361, #362 and #366, as shipped in
0.4.0. A run on main on 28 Oct gave the same results.

| | All 170 | Tuned on (150) | Held out (20) |
|---|---|---|---|
| Right kind of failure | 167 = 98.2% | 148 = 98.7% | 19 = 95.0% |
| Right failing test, file and line | 111/111 | 93/93 | 18/18 |
| Costly mistakes (a real bug called flaky, or a flaky failure called a bug) | 0 | 0 | 0 |

The first run (#359) had the kind right for 156 of 170 (91.8%) and 12 of 20 held-out runs.

**Limits.**
- tabib was fixed against the 150 trial runs, so 98.7% there shows how well it fits logs it has seen.
- The 20 held-out runs were the honest estimate for a new project. Since then, tabib was fixed against
  express's 8 runs, so only click's 12 are still held out.
- Several runs share one cause (17 flask runs fail on the same deprecation), so the per-project table
  matters more than the total.
- The model step of `/tabib:diagnose` is not measured: it needs a model and the project's code.

## lawha: design to code, and brief to page

[Full page](lawha.md)

**What it measures.** How lawha compares with other tools that build web pages: from a Figma design,
and from a written brief with no design.

**How.** Every tool starts from the same starter app with the same prompt, in one session, and nobody
edits the code. The Claude Code runs use the same model. One script builds, serves and measures every
result. Task 1 used a public Figma design lawha was not tuned on. Scored 6–7 Oct 2026, with lawha
between Nexika 0.1.0 and 0.2.0.

**Results.**
- **Figma to code.** lawha matched the design 95.6% / 98.5% / 96.2% at phone, tablet and desktop width.
  Figma's MCP server with Claude Code matched it 93.0% / 97.1% / 95.9%. lawha had 0 must-fix problems,
  Figma MCP 22 (14 tap targets, 8 accessibility). Builder.io's code did not build with npm, and its page
  was mostly invented content.
- **Brief to page.** lawha and Anthropic's frontend-design skill both built every part of the brief.
  Both worked in English and Arabic, light and dark, with no must-fix problems. Three blind judges preferred lawha's
  page in all 6 comparisons. lawha took about 34 minutes and 149k tokens; frontend-design about 5
  minutes and 90k.

**Limits.**
- One design and one brief, one run per tool.
- Most problem counts come from lawha's own checks, which lawha runs while it builds. So low counts for
  lawha are expected. The measures that don't come from lawha are the build, the pixel match, axe-core,
  whether the brief was done, and the blind preference.
- The blind judges were Claude models using lawha's judge instructions. Three judges are few, and no
  person has judged yet.
- The model used for the Claude Code runs is not recorded on the page.

## Not measured yet

- **prof, bayan, mizan and amin** have no benchmark. Their criteria are drafted in #391; prof's test
  with real learners is #398.
- **siyaq and barq** were measured only as arms of the agent benchmark (pilot 2), where neither moved
  the solve rate beyond noise. Whether siyaq loads the right knowledge, and whether barq's savings keep
  the outcome, is not measured.
- **manar** measures sites with `/manar:visibility`, but there are no results on real sites over time
  yet.

## Raw files and scoring again

Every benchmark keeps what a run produced, so the summary can be written again without running the
agent. A damaged folder is skipped or marked invalid, and named. Damaged means a half-written file, a
missing file or a byte that is not UTF-8. It never stops the rest of the summary.

| Benchmark | Raw files | Score again |
|---|---|---|
| [lawha](lawha.md) | each tool's code in `runs/<task>/<tool>/` (committed); lawha's check output in `.lawha/score/` there (local) | `node score/score.mjs figma` (installs, builds and checks again) |
| [agent](agent) | `~/nexika-bench/<pilot>/runs/<task>__<arm>__r<n>/`: `stream.jsonl`, `stderr.txt`, `diff.patch`, `meta.json`; an attempt run again is kept in its `attempts/<n>/`; the grader's logs in `grading/` | `bench.py summary` from `meta.json` and `grades.json`; `bench.py summary --from-raw` reads the numbers again from `stream.jsonl` and `diff.patch` |
| [hafiz](hafiz) | `~/nexika-bench/hafiz/v2/runs/<task>__<arm>__r<n>/`: every call's stream, the transcripts, `diff.patch`, the files and test results at each break and at the end; an unfinished run started again is kept as `<name>.partial-<n>` | `bench.py score` (`--home` for another data folder) |
| [haris](haris), [tabib](tabib) | the cases are committed; a run makes no files and takes seconds | run `bench.py` again; `--json` keeps every case's result |

The paid runs' raw data is kept on the maintainer's machine under `~/nexika-bench/`. That covers the
agent pilots, the guardrails and hafiz. It is not in this repository (the project's shared folder of
code).

## Updating this page

With each release:
1. Run the offline benchmarks again (`python3 benchmarks/haris/bench.py`, `python3
   benchmarks/tabib/bench.py`) and update their rows.
2. Measure the session start for the new tag (`bench.py context --ref nexika-v<version>`).
3. Add any paid run since the last release, with its date, Nexika commit, interval and p, and its
   limits.
4. Put each new result in the right list: outside material, or internal experiment.
