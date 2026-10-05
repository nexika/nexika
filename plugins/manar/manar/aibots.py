"""AI crawlers and what a robots.txt allows each of them to do.

Two kinds matter differently:
- search / user agents fetch pages to ANSWER questions and cite them (ChatGPT search, Perplexity,
  Claude search, Google and Bing). Blocking them makes you invisible in AI answers.
- training agents collect data to train models. Allowing them is a policy choice; it does not
  directly decide whether today's AI answers cite you.
"""
from __future__ import annotations

import urllib.robotparser
from dataclasses import dataclass


@dataclass(frozen=True)
class Bot:
    name: str
    owner: str
    kind: str      # search | user | training | search+ai (classic search that also feeds AI answers)
    note: str


BOTS = [
    Bot("Googlebot", "Google", "search+ai", "Google Search and AI Overviews / AI Mode"),
    Bot("Bingbot", "Microsoft", "search+ai", "Bing and Copilot; also used by other AI search products"),
    Bot("OAI-SearchBot", "OpenAI", "search", "ChatGPT search results"),
    Bot("ChatGPT-User", "OpenAI", "user", "fetches a page when a ChatGPT user asks about it"),
    Bot("PerplexityBot", "Perplexity", "search", "Perplexity answers"),
    Bot("Perplexity-User", "Perplexity", "user", "fetches pages for a user's question"),
    Bot("Claude-SearchBot", "Anthropic", "search", "Claude web search"),
    Bot("Claude-User", "Anthropic", "user", "fetches a page for a Claude user"),
    Bot("DuckAssistBot", "DuckDuckGo", "search", "DuckDuckGo AI answers"),
    Bot("Applebot", "Apple", "search", "Siri and Spotlight"),
    Bot("GPTBot", "OpenAI", "training", "model training"),
    Bot("ClaudeBot", "Anthropic", "training", "model training"),
    Bot("Google-Extended", "Google", "training", "control token for Gemini training (not a crawler)"),
    Bot("Applebot-Extended", "Apple", "training", "control token for Apple AI training"),
    Bot("CCBot", "Common Crawl", "training", "open dataset used by many models"),
    Bot("Meta-ExternalAgent", "Meta", "training", "Meta AI training"),
    Bot("Bytespider", "ByteDance", "training", "model training"),
    Bot("Amazonbot", "Amazon", "training", "Alexa and Amazon AI"),
]
VISIBILITY_KINDS = {"search", "user", "search+ai"}


def access(robots_txt: str | None, path: str = "/") -> dict[str, bool]:
    """Whether each bot may fetch path. No robots.txt means everything is allowed."""
    if not robots_txt:
        return {b.name: True for b in BOTS}
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return {b.name: parser.can_fetch(b.name, path) for b in BOTS}


def blocked_for_visibility(allowed: dict[str, bool]) -> list[Bot]:
    return [b for b in BOTS if b.kind in VISIBILITY_KINDS and not allowed.get(b.name, True)]


def blocked_for_training(allowed: dict[str, bool]) -> list[Bot]:
    return [b for b in BOTS if b.kind == "training" and not allowed.get(b.name, True)]
