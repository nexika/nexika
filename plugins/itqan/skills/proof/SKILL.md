---
name: proof
description: Make the proof that a change is done and save it as JSON - itqan runs the project's own tests, lint and build checks itself, and records the review verdict and the requirement checklist as reported. Use when the work is finished, after /itqan:ship, or when the user says "proof", "prove it", "show me it works", "أثبت", "وريني الدليل". mizan shows the latest proof in its pane.
argument-hint: "[what was asked, if not clear from the conversation]"
---

# Make the proof

The helper is named in the session note ("itqan proof (for /itqan:proof): python3
.../itqan_proof.py"); below it is written `itqan_proof.py`. Run it from the project directory.

1. **See what will run.** `itqan_proof.py checks` lists the checks itqan found in the project's
   files (tests, lint, build: pytest, ruff, mypy, pre-commit, tox environments, package scripts).
   It never runs a command you pass in; if a check is missing, say so instead of running it
   yourself and claiming it. Lines starting `not run:` are checks the project defines that the
   proof cannot run (a tool not installed): a test or lint check not run keeps the proof from
   passing, so tell the user what to install.

2. **Gather what only you know.**
   - The review verdict: the result of the latest `itqan:review` on this change (`approve` when no
     critical or high finding is left, else `changes`), with each finding still open as a note.
     No review yet: run `itqan:review` first, or leave `--review` out and say the proof has none.
   - The requirements: each thing the user asked for (from the plan or the task list), and
     whether it is met. Mark one done only when you can point to the code or test that shows it.

   - Pages: when the change touched the UI and lawha is installed, run `/lawha:check` on the
     changed pages first, at the commit you are proving. The proof picks up lawha's latest check of
     this project at this commit by itself (shown as "pages on every screen"); a failing one fails
     the proof. Never claim pages were checked when the proof shows no lawha check.

3. **Run it.**
   `itqan_proof.py run --review approve --done "<requirement met>" --open "<requirement not met>" --note "<open finding>"`
   Repeat `--done`, `--open` and `--note` as needed. Start each note with its severity, as the
   review gave it: `--note "[high] token written to the log"`. It exits 1 when a check failed,
   and refuses `--review approve` (exit 2, nothing saved) while a `[critical]` or `[high]` note is
   open: fix it, or record `--review changes`.

4. **Tell the user** in two or three plain lines: checks passed or which failed, the review
   verdict, requirements met out of total. With mizan installed they can open it with
   `/mizan proof`; otherwise show `itqan_proof.py show`.

Never edit a proof file by hand, and never describe a check as passed that the proof does not
show as passed.
