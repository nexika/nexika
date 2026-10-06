# Showcase: prof's learner dashboard, built with lawha

A local, read-only dashboard for [prof](../../plugins/prof/README.md):
- **Today:** what to review today.
- **Topics:** each topic, with how well it is known.
- **Sessions:** the session reports.
- **Course:** the course, module by module.
- **Profile:** prof's profile of the learner.

It works in English, Arabic (right to left) and French, light and dark. It was designed in
[DESIGN.md](DESIGN.md) before lawha existed, then built **with** lawha, as its first real app.

```sh
cd web && npm install && npm run build      # React 19, TanStack Router, Tailwind 4, Motion
python3 ../scripts/lawha_server.py start    # prints http://127.0.0.1:PORT/#t=TOKEN
```

The server needs only Python. It listens on 127.0.0.1, needs a one-time token, and never writes to prof's files.
**Demo data** (the switch in the header) shows it with sample sessions.

## How lawha built it

1. **`/lawha:direct`.** Three directions were proposed, checked and rendered at phone and desktop size
   ([directions.json](directions.json)). The user chose **A, Ink and saffron**:
   - Fraunces headings and Source Sans 3 text;
   - ink blue with one saffron highlight;
   - a saffron underline that draws itself under the first concept to review.

   `lawha direct choose` wrote `web/src/lawha-theme.css` (Tailwind and shadcn tokens, light and dark).
2. **`/lawha:check`, round 1.** lawha found:
   - two links too short to tap;
   - layout shift on phones (CLS 0.22). lawha now names what moved: the demo banner and header rewrapping when the fonts arrived.

   lawha's own false positive was also fixed: a visually hidden "Skip to content" link is not cut-off text.
3. **Looking, not only measuring.** In Arabic, the learner's English notes had their quote marks
   flipped (`"…“`). Text from the data is now isolated with `<bdi>`.
4. **`/lawha:elevate`.** The art director proposed three changes, and each one went through a blind A/B with a judge that never knew which side was new:

   | Proposal | Judge | Kept? |
   |---|---|---|
   | Saffron only for the signature (white banner, ink nav marks) | preferred the current version | no |
   | The four boxed counts as a quiet inline line | preferred the current: on phones "7 Understood" wrapped alone | no |
   | A bigger headline on phones (41.5px instead of 34px) | preferred the change (low confidence) | **yes** |

5. **`/lawha:check`, final.** Two more shifts on Arabic phones, both from the app's own code:
   - the page set `dir="rtl"` after the first paint;
   - Latin fonts were asked for Arabic sample text, so they loaded late.

   Both are fixed. Now all **7 screens pass with 0 problems**, each at 360, 390, 768, 1024, 1280 and 1536px, light and dark, English and Arabic, and with reduced motion.

`web/dist/` and `.lawha/runs/` are not committed: build the app to run it.
