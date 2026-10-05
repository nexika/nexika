---
name: recall
description: Search what hafiz remembers about this project - past decisions, tasks, problems, changed files and links - in Arabic or English, and answer from it with dates and sources. Use when the user asks "what did we decide about X", "when did we change Y", "last time", "did we already fix this", "تذكر", "ماذا قررنا", or before redoing work that may have been done in an earlier session.
argument-hint: "[what to look for]"
---

# Recall from memory

Looking for: $ARGUMENTS (if empty, use the topic of the user's last message).

1. **Search.** Run the hafiz helper from the session note:
   `<hafiz> recall "<words>"`. Matching is by words, not meaning, so search twice when it helps:
   once in the user's words and once with synonyms or the other language
   (e.g. `recall "discount coupon"` and `recall "خصم كوبون"`). Narrow with
   `--type decision|task|problem|file|link`, `--here` (this branch only) or `--days N`.
2. **Check before trusting.** A memory says what was true when it was written. For anything you
   will act on, confirm it in the code, `git log`, or the transcript line in its source
   (`transcript <session> L<line>`). If the code disagrees, trust the code and say so.
3. **Answer** briefly: what was found, with its date and branch, e.g. "On 5 Oct, on feat/12-login,
   we chose argon2 for password hashing (m5782fd9)." Say plainly when nothing was found; do
   not guess what an earlier session did.
4. If a memory is wrong or outdated, offer to remove it with `/hafiz:memory forget <id>`.
