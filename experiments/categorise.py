"""Keyword classifier for market topics.

gamma returns a null `category` and an empty `tags` array on these records,
so topic has to come from the question text. Crude, but it only needs to be
good enough to separate "a story that breaks on X" from "a scheduled event
that resolves on a timetable" -- which is the distinction the strategy turns
on.
"""

from __future__ import annotations

import re

RULES: list[tuple[str, tuple[str, ...]]] = [
    ("geopolitics", (
        "war", "ceasefire", "strike", "invade", "invasion", "troops", "military",
        "nuclear", "missile", "iran", "russia", "ukraine", "israel", "gaza",
        "hamas", "nato", "sanction", "peace deal", "hostage", "taiwan",
        "north korea", "venezuela", "coup", "khamenei", "putin", "zelensky",
    )),
    ("politics", (
        "election", "president", "prime minister", "chancellor", "nominee",
        "nomination", "resign", "impeach", "cabinet", "secretary", "senate",
        "congress", "parliament", "vote", "poll", "candidate", "primary",
        "trump", "biden", "harris", "mamdani", "starmer", "macron",
    )),
    ("corporate", (
        "ceo", "ipo", "acquire", "acquisition", "merger", "earnings", "bankrupt",
        "lawsuit", "sec ", "antitrust", "layoff", "openai", "tesla", "apple",
        "nvidia", "microsoft", "google", "amazon", "meta ", "spacex", "boeing",
        "microstrategy", "product", "launch", "release",
    )),
    ("macro", (
        "fed ", "interest rate", "cpi", "inflation", "gdp", "recession",
        "unemployment", "fomc", "rate cut", "rate hike", "tariff", "jobs report",
    )),
    ("crypto", (
        "bitcoin", "ethereum", "solana", "xrp", "dogecoin", "etf", "crypto",
        "btc", "eth ", "stablecoin", "binance", "coinbase",
    )),
    ("celebrity", (
        "grammy", "oscar", "album", "movie", "netflix", "engaged", "divorce",
        "baby", "arrest", "dies", "death", "retire", "swift", "kanye", "musk",
        "drake", "kardashian", "epstein", "gta",
    )),
    ("science", ("nobel", "spacex launch", "starship", "vaccine", "fda", "clinical")),
]


def categorise(question: str, slug: str = "") -> str:
    t = f" {question.lower()} {slug.lower().replace('-', ' ')} "
    for name, keys in RULES:
        for k in keys:
            if k in t:
                return name
    return "other"


def is_scheduled(question: str) -> bool:
    """Resolves on a timetable rather than by surprise.

    A market that settles at a known moment -- a monthly print, a scheduled
    vote, a price at a fixed timestamp -- is not something that breaks on X,
    however newsworthy the topic. Being able to exclude these is most of the
    value of the classifier.
    """
    t = question.lower()
    if re.search(r"\b(by|before|on)\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", t):
        return False       # deadline markets can still be broken by surprise
    return bool(re.search(r"\b(up or down|close (above|below)|price at)\b", t))
