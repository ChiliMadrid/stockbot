"""Simple source reliability and verification labeling for StockBot reports."""

from __future__ import annotations


PRIMARY_SOURCES = [
    "sec",
    "sec edgar",
    "sec filing",
    "investor relations",
    "press release",
    "company press release",
    "earnings transcript",
]

TOP_TIER_SOURCES = [
    "reuters",
    "bloomberg",
    "associated press",
    " ap ",
    "wall street journal",
    "wsj",
    "financial times",
    "cnbc",
]

REPUTABLE_SOURCES = [
    "marketwatch",
    "yahoo finance",
    "the verge",
    "techcrunch",
    "industry publication",
]

ANALYST_BLOG_SOURCES = [
    "seeking alpha",
    "motley fool",
    "substack",
    "analyst note",
]

RUMOR_SOURCES = [
    "reddit",
    "twitter",
    "x.com",
    "forum",
    "anonymous leak",
    "unsourced screenshot",
]


def score_source(source: str, url: str | None = None) -> int:
    """Return a simple source reliability score from 0 to 10."""
    text = f" {source or ''} {url or ''} ".lower()

    if any(term in text for term in PRIMARY_SOURCES):
        return 10
    if any(term in text for term in TOP_TIER_SOURCES):
        return 8
    if any(term in text for term in REPUTABLE_SOURCES):
        return 6
    if any(term in text for term in ANALYST_BLOG_SOURCES):
        return 4
    if any(term in text for term in RUMOR_SOURCES):
        return 2
    return 0


def label_verification(source_score: int, independent_source_count: int) -> str:
    """Label an item using source quality and approximate independent coverage."""
    if source_score >= 8:
        return "CONFIRMED"
    if independent_source_count >= 2 and source_score >= 6:
        return "CONFIRMED"
    if source_score >= 6:
        return "PARTIALLY_CONFIRMED"
    if independent_source_count >= 2:
        return "PARTIALLY_CONFIRMED"
    return "RUMOR_OR_UNVERIFIED"


def explain_verification(source_score: int, independent_source_count: int) -> str:
    """Explain why a verification label was assigned."""
    label = label_verification(source_score, independent_source_count)
    if label == "CONFIRMED":
        return (
            f"High-confidence source signal: source score {source_score}/10 with "
            f"{independent_source_count} approximate independent source(s)."
        )
    if label == "PARTIALLY_CONFIRMED":
        return (
            f"Some support, but still needs confirmation: source score {source_score}/10 with "
            f"{independent_source_count} approximate independent source(s)."
        )
    return (
        f"Low verification support: source score {source_score}/10 with "
        f"{independent_source_count} approximate independent source(s)."
    )
