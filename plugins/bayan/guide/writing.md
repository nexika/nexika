<!-- bayan: off (this guide quotes the phrases it warns about) -->
# The bayan writing guide

Write the way a patient, knowledgeable friend talks: plain, warm, exact.

## 1. Know the reader

| Level | Who | What changes |
|---|---|---|
| `no-code` | Has never written code: a founder, a client, a designer | Everyday words. Explain any technical word in the same sentence, with a comparison from daily life. Say what it means for them before how it works. |
| `junior` | Learning to code | Explain each new term once. Show one small example. |
| `developer` | Writes code daily | Technical words are fine. Stay plain and specific. |

Example, one fact at three levels:
- no-code: "Your site now tells Google which page is the original, like putting your name on your work, so copies don't compete with it."
- junior: "We added a canonical link: a tag in the page's `<head>` that tells search engines which URL is the original."
- developer: "Added `<link rel="canonical">` to every page; duplicates now point at the clean URL."

## 2. Say it plainly

- Start with the answer or the result. Put the reasons after it.
- One idea per sentence. Keep most sentences under 20 words, and mix in some short ones.
- Use specific facts: numbers, names, files, dates, what changed and what didn't.
- Cut words that add nothing: `in order to` becomes `to`, `due to the fact that` becomes `because`.
- Never trade accuracy for simplicity. If something is uncertain, say it once, plainly.

## 3. Sound like a person

| Instead of | Write |
|---|---|
| `Great question! Certainly, I'd be happy to help.` | (start with the answer) |
| `It's worth noting that the cache plays a crucial role.` | `The cache saves a second request.` |
| `This seamless, robust solution unlocks new possibilities.` | `Pages now load in 1.2 s instead of 3 s.` |
| `Let's delve into the intricate landscape of SEO.` | `Here is what Google needs from your site.` |
| `It's not just fast, but also secure.` | `It's fast. It also blocks private addresses.` |
| `I hope this helps! Let me know if you have any other questions.` | (stop when you're done) |

Machine habits to avoid:
- the same sentence length again and again;
- every list having exactly three items;
- every bullet opening with a **bold label**;
- em dashes in every paragraph (use a comma, a colon or two sentences);
- emoji in headings, and more than one exclamation mark;
- a closing paragraph that repeats what was just said.

## 4. Arabic

- Clear Modern Standard Arabic, the way a person writes it, not a word-for-word translation.
- Short sentences. One idea per sentence.
- Keep code, commands and product names in English, and explain them in Arabic: "الـ API، أي الطريقة التي تتحدث بها البرامج مع بعضها".
- Stiff phrases to avoid:

| بدلًا من | اكتب |
|---|---|
| `من الجدير بالذكر أن الإضافة سريعة.` | `الإضافة سريعة.` |
| `تلعب الذاكرة المؤقتة دورًا محوريًا.` | `الذاكرة المؤقتة توفّر طلبًا ثانيًا.` |
| `علاوة على ذلك، فهي مجانية.` | `وهي مجانية كذلك.` |
| `في الختام، نأمل أن يكون هذا مفيدًا.` | (توقف عندما تنتهي) |

## 5. What bayan does on its own

- After Claude writes or edits a `.md` or `.mdx` file, bayan cleans only the part Claude wrote: hidden characters, AI signature lines, filler sentences and wordy phrases go, and em dashes between words become commas. Code, front matter, HTML, links and comments are never changed. `.txt` and `.rst` files are only checked.
- Then it lists the lines that still need rewriting, so Claude can fix them.
- It refuses commits, tags, pull requests and releases that carry an AI signature line. Human co-authors are fine.
- Put `bayan: off` anywhere in a file (for example in an HTML comment) to leave that file alone.

## 6. Honest limits

The plainness score measures the habits listed here. It is not an AI detector, and nobody can promise what GPTZero, Copyleaks or any other detector will say: they change often and also flag text written by people. bayan aims for writing that real readers find clear and natural.
