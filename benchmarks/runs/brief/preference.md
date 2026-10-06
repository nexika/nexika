# Blind preference: brief to page

**Setup:**
- Three judge agents, each with its own pairs: lawha's and frontend-design's pages side by side, the order shuffled per pair.
- Each judge saw English and Arabic, phone (390px) and desktop (1280px), under reduced motion, every page shown in full.
- The judges saw only the images, never the key. They used lawha's judge instructions ([`plugins/lawha/agents/judge.md`](../../../plugins/lawha/agents/judge.md)).

| Judge | English | Arabic |
|---|---|---|
| 1 | lawha (medium) | lawha (medium) |
| 2 | lawha (high) | lawha (high) |
| 3 | lawha (high) | lawha (high) |

**lawha 6, frontend-design 0, same 0.**

What the judges said, in short:
- **lawha:**
  - a two-tone serif headline;
  - numbered sections with notes in the other script in the margin;
  - a highlighted Pro plan and a strong red closing call to action;
  - the same identity carried into Arabic.
- **frontend-design:**
  - clean, with no defects, correctly mirrored;
  - but generic, low in contrast and airy "to the point of feeling empty";
  - its blue, gold and navy accents are scattered.

The pairs from judge 1 are in [`pairs/`](pairs); each file name says which side is which.

**Run 1 was discarded.** It also gave 6 to 0 for lawha, but `lawha ab` cut both pages at 4000px, so frontend-design's longer page lost its pricing ending and call to action. lawha now shows both pages in full, with a test for it, and this table is from the re-run.

**Limits:**
- The judges are Claude models, from the same family that built both pages.
- Three judges are few.
- A human blind pick is the next step.
