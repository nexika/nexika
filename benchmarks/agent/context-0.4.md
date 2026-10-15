# Session-start tokens: 0.3.0, 0.4.0 and no plugins (#392)

How many tokens each Nexika plugin adds to the first request of a session, before any work. Measured
on 15 Oct 2026 with `bench.py context`, once on each release tag.

## Result

Nexika 0.4.0 adds **7,381** tokens to the first request. 0.3.0 adds **9,840**, so the session start is
**2,459 tokens smaller**. Without plugins, the first request is 17,170 tokens in both.

| Plugin | 0.3.0 | 0.4.0 | Change | Hook output 0.3.0 (chars) | Hook output 0.4.0 (chars) |
|---|---|---|---|---|---|
| itqan | +1,683 | +1,526 | -157 | 901 | 600 |
| bayan | +1,148 | +1,058 | -90 | 2,129 | 2,065 |
| lawha | +1,840 | +805 | -1,035 | 182 | 0 |
| prof | +1,331 | +644 | -687 | 1,004 | 0 |
| hafiz | +712 | +642 | -70 | 368 | 191 |
| mizan | +557 | +520 | -37 | 387 | 295 |
| amin | +517 | +489 | -28 | 172 | 121 |
| siyaq | +506 | +476 | -30 | 259 | 186 |
| haris | +429 | +390 | -39 | 550 | 386 |
| tabib | +435 | +381 | -54 | 356 | 207 |
| manar | +579 | +277 | -302 | 167 | 0 |
| barq | +262 | +206 | -56 | 686 | 537 |
| **One at a time, summed** | +9,999 | +7,414 | -2,585 | | |
| **All twelve together** | +9,840 | +7,381 | -2,459 | | |

Each row is a session with only that plugin, minus the session with none. Every plugin got smaller.
lawha, prof and manar account for 2,024 of the 2,585: in 0.4.0 they print nothing at the start of a
session, so what is left is their skill and agent descriptions.

All twelve together add 43% to a session's first request in 0.4.0, down from 57%.

## What this does not show

- **A task does not get cheaper.** This measures only the first request. In the #336/#345 guardrail run,
  the median first request fell by 2,266 tokens, but Claude took 0.7 more turns, and tokens per task
  rose by 12.8k (within noise). The README says so.
- **One session per arm.** The first request is nearly deterministic, so one session is enough, but
  not always. The first 0.3.0 amin session came out 62 tokens *below* no plugins, with a different
  cached prefix (10,869 tokens read from the cache against 13,714 in the other arms). Run again, it
  gave +517, the same as pilot 1 on 9 Oct. The table uses the second run; both are kept.

## Setup

| | |
|---|---|
| Date | 15 Oct 2026 |
| Command | `bench.py context --model sonnet --ref nexika-v<version> --task django__django-11848 --budget 1` |
| Model | `sonnet` (the sessions report `claude-sonnet-5-5`), one turn per session (`--max-turns 1`) |
| Claude Code | 2.1.300, in the benchmark's Docker container |
| Nexika | `nexika-v0.3.0` (c71079a) and `nexika-v0.4.0` (1c56d2f) |
| Arms | none, each of the 12 plugins alone, all 12; Claude Code's own built-in plugins load in every arm |
| Machine | Fedora 44, Linux 7.2.10, 12 cores, 14 GB RAM |
| Cost | $0.61 for 30 sessions (28, plus a rerun of 0.3.0's amin and no-plugin arms) |
| Raw data | `~/nexika-bench/context-0.3.0/` and `~/nexika-bench/context-0.4.0/` (`context/<arm>/meta.json`) |

To repeat it for the next release, run the command above with each tag and a fresh
`AGENTBENCH_HOME`. It makes one short paid session per arm, 14 per version.
