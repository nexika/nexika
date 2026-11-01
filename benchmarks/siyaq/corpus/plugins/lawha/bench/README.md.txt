# lawha bench

## speed.mjs: parallel browser contexts (#106)

`lawha check` renders every variant (width × theme × direction, plus one reduced-motion pass) in
its own browser context. It used to render them one after another; now several run at once
(`--concurrency <n>`, default one per CPU, up to 8). Results are merged in matrix order, so the
report is the same at any concurrency.

```
cd plugins/lawha/engine && npm ci && npm run build
node plugins/lawha/bench/speed.mjs [--pages good.html,bad.html] [--concurrency 1,2,4,8] [--repeat 3]
```

It runs the full matrix: 6 widths × light/dark × LTR/RTL + the reduced-motion pass = 25 variants,
and prints the median of `--repeat` runs per concurrency. `--concurrency 1` is the old behaviour.

Measured on 8 Oct 2026 (12 CPUs, Node 22.23, median of 3):

| page | 1 at a time (before) | 2 | 4 | 8 (after) |
|---|---|---|---|---|
| good.html (clean) | 71.6 s | 36.8 s (1.9×) | 21.4 s (3.3×) | 14.3 s (5.0×) |
| bad.html (planted faults, CLS reloads) | 93.7 s | 49.6 s (1.9×) | 27.6 s (3.4×) | 19.2 s (4.9×) |

A 3-round fix loop on the full matrix goes from about 4–5 minutes of checking to about one.
