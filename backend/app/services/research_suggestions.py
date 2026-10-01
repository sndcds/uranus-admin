"""Deterministic privacy gate and bounded learning weights; no inference services."""

import re
import unicodedata
from math import log1p

MIN_SUCCESSES = 3
MAX_QUERY_LENGTH = 300
PREFIX_WEIGHT = 100.0
FREQUENCY_WEIGHT = 3.0
SELECTION_WEIGHT = 1.0
CONVERSION_WEIGHT = 5.0
RECENCY_WEIGHT = 4.0
CTR_WEIGHT = 2.0
RECENCY_DAYS = 30.0

# Deliberately conservative: false negatives are more costly than omitted suggestions.
SENSITIVE = re.compile(
    r"@|(?:https?|ftp|file|ssh)\s*:|www\.|localhost|127\.0\.|\b\d{1,3}(?:\.\d{1,3}){3}\b"
    r"|\b[\w-]+\.[a-z]{2,63}\b"
    r"|\b[0-9a-f]{8}-[0-9a-f-]{20,}\b|\b[0-9a-f]{24,}\b|\b\w*[0-9]\w{23,}\b"
    r"|\b(?:sk-|ghp_|gho_|AKIA)[a-z0-9_-]{12,}|\b(?:or|and)\s+\d\s*=\s*\d"
    r"|\b(?:\+?\d[\d\s()./-]{6,}\d)\b"
    r"|api[ _-]?key|bearer|token|passwor[dt]|secret|geheim|kennwort|ssh-|private key"
    r"|account|username|benutzer(?:name|konto|kennung)|kundennummer|user[_ -]?id"
    r"|ignore|ignorier|system prompt|systemanweisung|jailbreak|prompt.?injection|bypass|exploit"
    r"|\b(?:select|insert|update|delete|drop|union|truncate)\b.*\b(?:from|into|table|select|set)\b"
    r"|[<>{};`\\]|=>|--|/\*|\b(?:import|def|function|sudo|curl)\b",
    re.IGNORECASE,
)


def display_query(query: str) -> str:
    return " ".join(query.split())


def normalize(query: str) -> str:
    return display_query(query).casefold().rstrip(".!?。！？").rstrip()


def eligible(query: str) -> bool:
    return (
        2 <= len(query) <= MAX_QUERY_LENGTH
        and len(normalize(query)) <= MAX_QUERY_LENGTH
        and any(c.isalpha() for c in query)
        and not any(unicodedata.category(c).startswith("C") for c in query if c not in "\n\r\t")
        and not SENSITIVE.search(query)
        and not any(len(token) > 40 for token in query.split())
    )


def search_prefixes(normalized: str) -> list[str]:
    # At most 300 short entries; GIN supports token-prefix lookup without extensions.
    return sorted({word[:end] for word in normalized.split() for end in range(1, len(word) + 1)})


def score(
    *,
    starts: bool,
    successes: int,
    selections: int,
    conversions: int,
    impressions: int,
    age_days: float,
) -> float:
    return (
        PREFIX_WEIGHT * starts
        + FREQUENCY_WEIGHT * log1p(successes)
        + SELECTION_WEIGHT * log1p(selections)
        + CONVERSION_WEIGHT * log1p(conversions)
        + RECENCY_WEIGHT / (1 + max(0, age_days) / RECENCY_DAYS)
        + CTR_WEIGHT * min(1, (selections + 2) / (impressions + 10))
    )
