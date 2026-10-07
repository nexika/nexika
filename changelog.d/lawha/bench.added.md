A public benchmark (benchmarks/): the same tasks, starter app and scoring script for lawha and the leading tools. Brief to page: lawha and Anthropic's frontend-design both did the whole brief with no must-fix problems; blind judges picked lawha's page 6 times out of 6. Figma to code (lawha, Figma MCP, Builder.io) is set up for the account-based runs. lawha check now scrolls through the page before measuring, so sections that appear on scroll are checked and photographed, and lawha ab shows both pages in full instead of cutting them at 4000px.

Found by the benchmark's Figma run and fixed:
- **Photos:** layers that share a name ("Rectangle 6") no longer overwrite each other's photos.
- **Colour styles:** they keep their opacity in theme.css.
- **Mixed text sizes:** the spec now lists the base size when a longer run sets the main style.
- **Icons:** icons that only exist in the phone or tablet frame are exported too.
- **Text over images:** contrast is measured against the real background behind the letters, by hiding the text for one screenshot, instead of guessing from pixels that include the letters' soft edges.
