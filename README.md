# Nexika

[![CI](https://github.com/nexika/nexika/actions/workflows/ci.yml/badge.svg)](https://github.com/nexika/nexika/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

> **The next wisdom for Claude Code.** *Nex*t + h*ika* (from *hikma*, حكمة: wisdom).

Nexika is a set of twelve add-ons for **Claude Code**, an AI assistant that writes and fixes
software. Each add-on gives Claude one skill a careful human colleague would have. One is a guard
that stops it from doing damage, another a memory that keeps track of the work. Others are a
doctor that finds out why a build failed, and a teacher for people learning to code.

You don't need to be a programmer to understand what Nexika does. This page explains it in plain
words. The technical details for people who build Nexika are at the end, under
[For developers](#for-developers).

**Current release: Nexika 0.4** (11 October 2026). [What's new](#whats-new-in-04).

## The idea in one minute

Claude Code is like a very fast new colleague who can read and change a whole software project.
It is capable, but it starts every conversation knowing nothing about your project. It can run
commands that delete files or publish things. And it can't always tell which of its checks matter.

Nexika adds the habits that make such a colleague trustworthy:

- **Safety.** Before Claude runs a command, Nexika checks what it would do. Harmless work goes
  ahead. Anything risky waits for your yes. Anything dangerous, like deleting your home folder
  or sending a password to a website, is refused, with a reason in plain words.
- **Quality.** Claude is told to prove its work. It writes a check that fails first, runs the
  checks of every file it changed, and gets a review before saying "done".
- **Memory.** Decisions, open problems and the plan survive when a long conversation is
  shortened, or when you start a new one tomorrow.
- **Clarity.** Claude explains itself in clear English or Arabic, for the reader you choose.

Each add-on works on its own. You can install one, a few, or all twelve.

## The twelve add-ons

Each add-on has an Arabic name that says what it does. Click a name for its own guide.

### Keeping you safe

| Add-on | In plain words |
|---|---|
| [**haris**](plugins/haris/README.md) (حارس, *guard*) | Reads every command before Claude runs it and judges what it would really do. Ordinary work passes, risky actions ask you first, and dangerous ones are refused: deleting outside the project, sending secrets out, publishing, rewriting shared history. It also notices when a web page or file tries to give Claude orders. Only you can approve, by typing; Claude can never approve for itself. |

### Doing the work well

| Add-on | In plain words |
|---|---|
| [**itqan**](plugins/itqan/README.md) (إتقان, *doing work with excellence*) | A careful way of working: plan first, write a test that fails, make it pass, check everything, and have a specialist review the change. It reminds Claude to run the tests of every file it touched before calling the work done, and it learns your project's rules from your corrections. |
| [**tabib**](plugins/tabib/README.md) (طبيب, *doctor*) | When the automatic checks on a project fail (people call this "CI"), tabib finds out why, with evidence: which test failed, where, and whether it is a real bug, a flaky test, a server problem or a missing package. It only diagnoses; it never changes code by itself. |
| [**lawha**](plugins/lawha/README.md) (لوحة, *board* or *canvas*) | For websites and apps: opens every page in a real browser, on a phone, a tablet and a wide screen, in light and dark mode, left-to-right and right-to-left (for Arabic). It finds text that is cut off, buttons too small to tap, and colours too faint to read, then fixes them. |
| [**barq**](plugins/barq/README.md) ⚡ (برق, *lightning*) | Makes Claude faster and cheaper on routine reading: many files in one step, only the part of a long test report that matters, and a short project status. Passwords and keys in what it shows are masked. |

### Remembering and knowing

| Add-on | In plain words |
|---|---|
| [**hafiz**](plugins/hafiz/README.md) (حافظ, *the one who keeps and remembers*) | Keeps a notebook of the work as it happens: the decisions you made, the plan and its open steps, the problems still open, the files that matter. When a long conversation is shortened, or you start a new one, hafiz hands Claude the notebook so it carries on instead of starting over. Secrets are removed before anything is saved. |
| [**siyaq**](plugins/siyaq/README.md) (سياق, *context*) | Gives Claude the right page of your project's documentation at the right moment, only when a question or a file needs it, in Arabic or English, instead of everything every time. |
| [**mizan**](plugins/mizan/README.md) (ميزان, *scale* or *balance*) | A small bar above where you type that keeps the session in balance: which line of work (branch) you're on, whether the last checks passed, how full Claude's memory of the conversation is, the computer's memory and disk, and what the session has cost so far. It warns you before something runs out. |

### Learning and writing

| Add-on | In plain words |
|---|---|
| [**prof**](plugins/prof/README.md) (*professor*) | A personal programming teacher: step-by-step lessons, a guided tour of an unfamiliar project for newcomers, a short warm-up quiz at the start of a session, and a report of what you learned at the end. |
| [**bayan**](plugins/bayan/README.md) (بيان, *clarity*) | Makes Claude write like a clear, friendly person, in English or Arabic, for the reader you choose: someone who has never written code, someone learning, or a developer. It removes the habits that make text sound machine-written. This page was written with it. |

### Running a project and being found

| Add-on | In plain words |
|---|---|
| [**amin**](plugins/amin/README.md) (أمين, *the trustworthy keeper*) | Helps look after a project on GitHub: sorts new requests and bug reports, turns one into a finished, tested change ready for review, and prepares releases with version numbers and a list of what changed. A person always gives the final approval; amin never does. |
| [**manar**](plugins/manar/README.md) (منار, *lighthouse*) | Helps a website be found, by Google and by AI assistants like ChatGPT and Gemini. It checks the site, fixes what search engines need, and measures how often AI assistants mention and cite it, compared with the last release. |

## What's new in 0.4

Nexika 0.4 came out of a test. We ran Claude Code with and without Nexika on hundreds of real
programming tasks. We looked at where Nexika helped and where it got in the way, and fixed what
we found. Every change had to show, with numbers, that it didn't make the work worse.

- **Claude tests what it changed.** itqan now tells Claude, before it says "done", to run the
  tests of every file it edited. On 100 real tasks, Claude did so in 86% of them, up from 63%,
  with the same share of tasks solved.
- **A lighter start.** The add-ons say less at the start of each conversation, and only what
  changes how Claude works. That opening text is about 2,500 tokens shorter than in 0.3 (a token
  is roughly three quarters of a word; [each add-on's share](benchmarks/agent/context-0.4.md)). The quality of the work held, and Claude ran tests more often. A
  task did not get cheaper overall, though: Claude used the room for more steps, so the total
  stayed about the same.
- **A better memory after a break.** hafiz now keeps the plan and its open steps, and every
  decision, across a fresh conversation. In one test, Claude restarted halfway through a job and
  was told only "carry on". With hafiz it finished the remaining work in all 3 runs; without
  hafiz, in none of 3.
- **A stricter, quieter guard.** haris now catches more tricks. Some split a harmful action over
  two steps; others hide a command inside a program or send secrets out in disguise. It also
  interrupts less for ordinary work. On its test set it asks about 9 of 493 ordinary commands,
  down from 22, and it still stops all 687 harmful ones.
- **A sharper doctor.** tabib now reads more kinds of test reports and failures. On 170 real
  failed builds from six public projects, it names the right kind of failure 167 times and the
  right failing test every time.

The full lists are in [CHANGELOG.md](CHANGELOG.md) and in each add-on's own changelog.

## How we know it works

We measure the add-ons and publish the results, including where an add-on doesn't help yet. Every
method, result and limit is collected on one page: [benchmarks](benchmarks/README.md).

We keep two kinds of result apart, and we say how sure each one is.

**Tested on outside material.** These used tasks we did not write, graded by tools we did not build.
Nobody outside the project has repeated them yet.

| What we measured | How | Result |
|---|---|---|
| Does Nexika help Claude solve programming tasks? | The same tasks from public software projects, with and without Nexika ([benchmarks/agent](benchmarks/agent/README.md)) | Not shown. Claude solved about 3 to 5 more tasks in 100 with Nexika, but the difference is small enough to be chance. |
| Does Claude check its work more? | The same tasks | Yes. With Nexika, Claude runs the project's tests more often. With itqan's 0.4 guidance, it tests the files it changed in 86% of tasks, up from 63%. |
| What does it cost? | The same tasks | About twice as much per task. |
| Does lawha follow a design? | One public Figma design, the same for each tool ([benchmarks/lawha](benchmarks/lawha.md)) | As closely as Figma's own tool, with fewer accessibility problems. |

**Our own tests.** These use test sets we wrote, or material an add-on was tuned on. They guide our
work and catch mistakes, but they don't prove how an add-on does on your work.

| What we measured | How | Result |
|---|---|---|
| Does haris stop real harm without getting in the way? | 1,344 commands we labelled, harmful and ordinary ([benchmarks/haris](benchmarks/haris/README.md)) | Stops all 799 harmful ones at the standard setting, asks about 9 of 545 ordinary ones, and decides in under a thousandth of a second. |
| Does tabib find the real cause of a failed build? | 170 real failures from six public projects, labelled by hand; tabib was tuned on 150 of them ([benchmarks/tabib](benchmarks/tabib/README.md)) | Right kind of failure 98% of the time, right failing test every time, with no misleading answers left. |
| Does hafiz keep the work going after a break? | Our own long tasks with a forced break, with and without hafiz ([benchmarks/hafiz](benchmarks/hafiz/README.md)) | No difference after a shortened conversation. After a restart in a new conversation, Claude finished the open work in all 3 runs with hafiz and in none without. Only 3 runs each, so it is a strong sign, not a proof. |
| Do people prefer lawha's pages? | One brief, built by lawha and by another design skill ([benchmarks/lawha](benchmarks/lawha.md)) | Three judges preferred lawha's page every time. The judges were AI models, not people. |

## Cost and privacy

- Your work stays on your computer. The add-ons keep their notes in a folder in your home
  folder. Passwords, keys and tokens are removed before anything is saved.
- There is no hidden AI spending. Almost everything Nexika does runs without calling an AI model, so
  it costs nothing extra. The few features that do call one ask your permission first, once.
  prof's automatic learning reports and itqan's learning from your corrections use your Claude
  plan or credits. manar's AI-visibility check uses keys you give it; one free Gemini key is
  enough to start.
- Being more thorough costs more. Because Claude checks its work more often with Nexika, a task
  can take more steps. In our tests, a task cost about twice as much with all twelve add-ons
  installed. Install only the ones you need, or turn some off per project (below).

## Installing

You need Claude Code installed first ([Anthropic's guide](https://docs.claude.com/en/docs/claude-code)).
Then, inside Claude Code, type these lines one at a time. The first adds the Nexika catalogue;
each of the others installs one add-on, so skip the ones you don't want:

```
/plugin marketplace add nexika/nexika
/plugin install haris@nexika
/plugin install itqan@nexika
/plugin install hafiz@nexika
/plugin install tabib@nexika
/plugin install barq@nexika
/plugin install siyaq@nexika
/plugin install mizan@nexika
/plugin install bayan@nexika
/plugin install prof@nexika
/plugin install amin@nexika
/plugin install manar@nexika
/plugin install lawha@nexika
```

Then close Claude Code and open it again, so the add-ons start.

The first time, Nexika asks one question: are you a developer, learning to code, or a writer? The
add-ons use your answer to decide how to talk to you. You can change it later.

### Lean sessions: what each plugin adds, and turning one off per project

Every installed add-on adds a little text to each conversation. Some stay quiet when they have
nothing to do:

- lawha speaks up only in a project that has a website or app front end.
- manar speaks up only in a website project.
- prof speaks up only when a lesson is due, or when you've said you are learning.

Their commands still work everywhere. You can also turn an add-on off completely in one project,
so it adds nothing there. Set it to `false` in that project's `.claude/settings.json` file (shared
with your team), or in `.claude/settings.local.json` (only for you):

```json
{
  "enabledPlugins": {
    "lawha@nexika": false,
    "manar@nexika": false
  }
}
```

For example, lawha and manar off in a project with no website, or prof off where nobody is
learning. Typing `/plugin` in Claude Code shows what is on where.

## Words you will meet

| Word | Meaning |
|---|---|
| **Claude Code** | Anthropic's AI assistant for software work. It reads a project, runs commands and changes files when you ask. |
| **Add-on (plugin)** | An extra skill you install into Claude Code. Nexika is a collection of twelve. |
| **Project, repository** | The folder that holds a piece of software, with its full history of changes. |
| **Command** | An instruction typed into the computer's terminal, such as "run the tests" or "delete this folder". |
| **Test** | A small program that checks another program does what it should. "The tests pass" means the checks found no problem. |
| **CI** | The automatic checks that run on a server each time someone proposes a change. |
| **Pull request (PR)** | A proposed change, waiting for a person to review and accept it. |
| **Branch** | A separate line of work in a project, so a change can be made without touching the main version until it's ready. |
| **Token** | The unit AI models read and write in, roughly three quarters of a word. Fewer tokens means faster and cheaper. |
| **Compaction** | When a conversation gets too long, Claude Code shortens it to a summary so it can continue. Details can be lost; hafiz keeps them. |
| **Prompt injection** | Text in a web page or file that tries to give Claude orders. haris warns about it and treats it as information, never as an instruction. |

## For developers

Everything below is for people who build or change Nexika itself.

### Repository layout

```
nexika/
├─ .claude-plugin/marketplace.json   ← the catalogue: lists every plugin
├─ common/                           ← shared code, copied into the plugins that use it
├─ benchmarks/                       ← agent, haris, tabib, hafiz and lawha benchmarks
└─ plugins/
   └─ prof/                          ← one folder per plugin
      ├─ .claude-plugin/plugin.json
      ├─ output-styles/  skills/  agents/  hooks/  scripts/
      └─ README.md
```

To add a plugin: create `plugins/<name>/` with its own `.claude-plugin/plugin.json`, then add
it to `.claude-plugin/marketplace.json`.

Versions in Nexika 0.4:

| amin | barq | bayan | hafiz | haris | itqan | lawha | manar | mizan | prof | siyaq | tabib |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.4.0 | 0.4.0 | 0.3.0 | 0.3.0 | 0.4.0 | 0.5.0 | 0.2.0 | 0.3.0 | 0.4.0 | 0.3.0 | 0.3.0 | 0.4.0 |

### The family profile: who the user is

The family settings file, `~/.claude/nexika/settings.json` (`NEXIKA_HOME` moves the folder),
holds one role, `developer`, `learner` or `writer`, so the plugins agree on who they work for: bayan picks its reader level
from it, prof decides whether to teach or just answer, and siyaq how loosely it matches docs. A
setting made in a plugin itself still wins. The first session asks once; change it later with
`python3 common/family.py role <role>` (each plugin ships a copy and prints its path). The same
file holds `background_calls`, the consent for the family's background model calls (#45), and
`mizan doctor` shows both. An older `profile.json` is moved into it once and kept as
`profile.json.migrated`.

### Status files: how the plugins talk to each other

A plugin that knows something the others can use publishes it as a small JSON file under
`~/.claude/nexika/status/` (`NEXIKA_STATUS_HOME` moves it): `<plugin>.json` for what holds across
sessions, `<plugin>/<session>.json` for one session. Every file carries
`"schema": "nexika.<plugin>/1"` and `"updated"` (seconds since the epoch); a reader ignores a file
with another schema or one too old, and a missing file means "nothing known". haris protects the
folder, so only the plugins write there, never Claude.

| File | Written by | Read by |
|---|---|---|
| `mizan/<session>.json` | mizan: context level, cost, device, tasks | siyaq (loads less as the context fills), mizan's daily cost |
| `haris/<session>.json` | haris: profile and mode | mizan's band |
| `itqan.json` | itqan: the latest proof per project | mizan's proof pane |
| `tabib.json` | tabib: the latest CI diagnosis per project and branch | mizan's band and pane, itqan's proof |
| `lawha.json` | lawha: the latest check of each project's pages on every screen (a pointer into lawha's own folder) | mizan's band and pane, itqan's proof |
| `amin.json` | amin: the projects of each repository ready to release (after plan, a note, prepare or publish) | mizan's band and pane |
| `manar.json` | manar: the last audit's checklist score per project | mizan's pane |
| `barq.json` | barq: today's calls and bytes saved, with the bytes it sent beyond the built-in tools kept apart | mizan's pane |
| `prof.json` | prof: retention checks due and open items (at session start and after a report) | mizan's band and pane |

### Develop locally

```bash
claude --plugin-dir ./plugins/prof          # run one plugin without installing
claude plugin validate .                    # check the marketplace
claude plugin validate ./plugins/prof/.claude-plugin/plugin.json
claude plugin test ./plugins/mizan          # a mod's own tests (*.test.ts)
pytest                                      # tests (pip install pytest)
ruff check .                                # lint (pip install ruff)
```

### Contributing

`main` is protected: every change goes through a pull request that must pass CI.

1. Branch from `main`: `git switch -c feat/<short-name>` (or `fix/`, `docs/`, `chore/`).
2. If you change a plugin, add a change note for it (see [changelog.d/](changelog.d/README.md)):
   `python3 plugins/amin/bin/amin fragment add <plugin> <type> "<what changed>" --id <PR>`.
3. Commit, push the branch, and open a pull request.
4. CI runs lint, tests (Python 3.10-3.14, Linux and macOS), `claude plugin validate`, the mod
   tests (`claude plugin test`) and the change-notes rule. The **CI passed** check must be green
   before merging.
5. Squash-merge; the branch is deleted automatically.
6. Releases are cut with `/amin:release`: one version, CHANGELOG and tag per plugin.

## License

MIT © 2026 Loai Elattar
