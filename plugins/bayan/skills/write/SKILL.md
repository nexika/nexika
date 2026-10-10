---
name: write
description: Rewrite a text or file to read clear and natural for the chosen reader, in English or Arabic, without changing facts. Use when the user says "make this simpler", "humanize this", "this sounds like AI", "اكتبها بشكل أبسط", or "bayan write".
argument-hint: "<file or text> [no-code|junior|developer]"
---

# Write

The bayan helper and the full guide path are in the session note ("Helper: ... Full guide ...");
below the helper is written `bayan`.

1. Input: $ARGUMENTS. A file path, or the text itself. A level word overrides the saved reader
   level for this run; otherwise use the level from the session note.
2. Read the full guide once (the path in the session note).
3. Run `bayan check <file>` (or `bayan check -` with the text on stdin) and note the score and
   the lines it lists.
4. Rewrite:
   - Keep every fact, number, name, link, command and code block exactly as it is.
   - Keep the language of the original (Arabic stays Arabic, English stays English).
   - Follow the guide for the reader level: answer first, plain words, explained terms, varied
     sentence length, no filler, no machine habits.
   - Keep the structure (headings, lists, tables) unless it is what makes the text hard to read.
5. For a file, write the new version, then run `bayan clean <file> --write` and `bayan check <file>`.
   Fix any line it still lists, at most two more rounds.
6. Report in a few lines: the score before and after, the three biggest changes, and any fact
   you were unsure how to simplify (ask instead of guessing).

Never claim the text will pass an AI detector. The score measures clarity and the habits in the
guide, nothing else.
