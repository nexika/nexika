---
name: check
description: Check a text or file for what makes it hard to read or machine-sounding (filler, stiff phrases, unexplained technical words, long or same-length sentences, hidden characters, AI signature lines) in English and Arabic, line by line. Use when the user says "check this text", "does this sound like AI", "is this clear enough", "راجع النص", or "bayan check".
argument-hint: "<file or text> [no-code|junior|developer]"
---

# Check

The bayan helper is in the session note; below it is written `bayan`.

1. Input: $ARGUMENTS (a file, or the text: pass it on stdin with `bayan check -`). A level word
   becomes `--level <word>`.
2. Run `bayan check ...`.
3. Explain the result in plain words:
   - the plainness score counts known habits; it is not an AI detector and doesn't predict
     GPTZero or Copyleaks;
   - "fixed by bayan clean" items are mechanical and safe to fix automatically;
   - "to rewrite" items need a new sentence: show the two or three most important ones with a
     better version.
4. Offer `/bayan:write` to fix everything, or `bayan clean <file> --write` for the safe fixes only.
