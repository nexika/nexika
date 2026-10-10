---
name: allow
description: Approve one exact command or path that haris asked about or refused - typed by the user only, never by Claude. Forms - /haris:allow <exact command>, /haris:allow read <path>, /haris:allow write <path>, --project to keep it for this project, --remove to take one back, nothing to list them.
argument-hint: "[--project] <exact command> | read <path> | write <path> | --remove <value>"
disable-model-invocation: true
---

# Approve one action

The approval was recorded by haris's own hook from what the user typed, before this skill ran.
This skill only reports it.

1. Run `<haris> approvals` (the helper path is in the session note) and show the user what is
   approved now, with its scope (this session, or this project with `--project`).
2. Remind them in one line that an approval covers exactly this command or path and nothing
   else, and that merges, releases, publishing and changes to haris still ask or stay refused.
   If haris answered that it was NOT approved, explain that this action is refused in every
   profile (deleting home or the system, persistence, sending secrets out, ...) and that only
   the user can do it, outside Claude.
3. For a lasting approval (`--project`), offer to record it as a decision in hafiz if it is
   installed (`<hafiz> remember decision "haris: approved <what> because <why>" --project`), so
   later sessions know why it is allowed.
4. If nothing was approved (empty arguments, or the list did not change), show the forms:
   `/haris:allow git push --force origin feat/login`, `/haris:allow read ~/.aws/config`,
   `/haris:allow --project make release-notes`, `/haris:allow --remove <the same text>`.

Never try to approve something on the user's behalf: haris ignores approvals that do not come
from the user's own message.
