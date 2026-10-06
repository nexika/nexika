---
name: why
description: Explain why haris asked about or refused an action - what it saw, what the risk is, and the safe way forward. Use when the user asks "why was this blocked", "why did haris ask", "what did haris stop", "لماذا تم الرفض", or right after a haris refusal the user wants to understand.
argument-hint: "[how many, default 3]"
---

# Why did haris step in?

1. Run the haris helper from the session note: `<haris> why -n 3` (use the number in
   $ARGUMENTS if one is given; `--all` covers every project).
2. Explain each entry in plain words, in the user's language: what the command would have done,
   why that is risky (the `meaning` line), and the safe alternative (for example a feature branch
   and a pull request instead of a force push to main, an environment variable instead of a key
   in a file).
3. If the user still wants a refused action, tell them they can approve exactly that command by
   typing `/haris:allow <exact command>` themselves. Never type it for them, never run haris's
   hook by hand and never edit haris's files: approvals only count when the user types them.
4. Merges, releases, publishing and deleting remote things always ask, and changes to haris
   itself are always refused; say so instead of looking for a way around it.
