"""Fetch SWE-bench Verified and pick the pilot's tasks with a fixed seed."""

import json
import random
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

DATASET = "princeton-nlp/SWE-bench_Verified"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
PAGE = 100

# Only what the agent may see, plus what selection needs. The gold patch, the test patch, the
# test names and the hints are never stored: the agent must not be able to find them.
KEEP = ("instance_id", "repo", "base_commit", "version", "difficulty", "created_at", "problem_statement")

EASY, MEDIUM, HARD, VERY_HARD = "<15 min fix", "15 min - 1 hour", "1-4 hours", ">4 hours"


def strip(row):
    return {k: row.get(k) for k in KEEP}


def fetch_rows(total=500, opener=urllib.request.urlopen):
    rows = []
    for offset in range(0, total, PAGE):
        query = urllib.parse.urlencode({"dataset": DATASET, "config": "default", "split": "test",
                                        "offset": offset, "length": PAGE})
        with opener(f"{ROWS_URL}?{query}", timeout=60) as resp:
            page = json.load(resp)
        batch = [strip(r["row"]) for r in page.get("rows", [])]
        rows.extend(batch)
        if len(batch) < PAGE:
            break
    return rows


def select(rows, quotas, seed, max_per_repo, scarce_first=False):
    """Pick tasks per difficulty quota, the same ones for the same seed, with at most
    max_per_repo from one repository (django is almost half of Verified). scarce_first fills the
    difficulty with the fewest tasks first, so the repository cap cannot use up a rare kind."""
    rng = random.Random(seed)
    ordered = sorted(rows, key=lambda r: r["instance_id"])
    rng.shuffle(ordered)
    per_repo = Counter()
    picked = []
    order = list(quotas)
    if scarce_first:
        available = Counter(r["difficulty"] for r in rows)
        order.sort(key=lambda d: available[d])
    for difficulty in order:
        quota = quotas[difficulty]
        taken = 0
        for row in ordered:
            if taken == quota:
                break
            if row["difficulty"] != difficulty or per_repo[row["repo"]] >= max_per_repo:
                continue
            picked.append(row)
            per_repo[row["repo"]] += 1
            taken += 1
        if taken < quota:
            raise ValueError(f"only {taken} tasks for {difficulty!r}, wanted {quota}")
    return picked


def save_tasks(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")


def load_tasks(path):
    return json.loads(Path(path).read_text())


def load_pilot(path):
    """The committed pilot file: seed, quotas and the chosen instance ids."""
    return json.loads(Path(path).read_text())
