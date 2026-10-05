---
name: level
description: Show or set who Claude is writing for - no-code (never written code), junior (learning) or developer - so every answer, report and note uses the right words. Use when the user says "explain like I'm not a developer", "I'm a developer, skip the basics", "set the reader level", or "bayan level".
argument-hint: "[no-code|junior|developer]"
---

# Level

The bayan helper is in the session note; below it is written `bayan`.

1. With an argument ($ARGUMENTS): run `bayan level <level>`. Without one: run `bayan level` and
   ask which reader fits, in one short question:
   - **no-code**: has never written code (founder, client, designer);
   - **junior**: learning to code;
   - **developer**: writes code every day.
2. Confirm in one sentence, and use the new level for the rest of this session. It is saved for
   future sessions too.
