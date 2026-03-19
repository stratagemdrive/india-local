"""
fetch_india_news.py
Fetches RSS headlines from 5 Indian news sources, translates Hindi content
to English, categorizes stories, and writes docs/India_news.json.
"""

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
from dateutil import parser as dateparser
from deep_translator import GoogleTranslator
from langdetect import detect, LangDetectException

# ── Config ────────────────────────────────────────────────────────────────────

SOURCES = [
    {
        "name": "The Hindu",
        "feeds": [
            "https://www.thehindu.com/news/national/feeder/default.rss",
            "https://www.thehindu.com/business/feeder/default.rss",
            "https://www.thehindu.com/sci-tech/energy-and-environment/feeder/default.rss",
        ],
        "lang": "en",
    },
    {
        "name": "India Today",
        "feeds": [
            "https://www.indiatoday.in/rss/home",
            "https://www.indiatoday.in/rss/1206514",
            "https://www.indiatoday.in/rss/1206577",
        ],
        "lang": "en",
    },
    {
        "name": "Aaj Tak",
        "feeds": [
            "https://feeds.feedburner.com/aajtak/news",
        ],
        "lang": "hi",
    },
    {
        "name": "Hindustan Times",
        "feeds": [
            "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
            "https://www.hindustantimes.com/feeds/rss/business/rssfeed.xml",
            "https://www.hindustantimes.com/feeds/rss/world-news/rssfeed.xml",
        ],
        "lang": "en",
    },
    {
        "name": "NDTV",
        "feeds": [
            "https://feeds.feedburner.com/ndtvnews-india-news",
            "https://feeds.feedburner.com/ndtvnews-top-stories",
            "https://feeds.feedburner.com/ndtvprofit-latest",
        ],
        "lang": "en",
    },
]

CATEGORIES = ["Diplomacy", "Military", "Energy", "Economy", "Local Events"]
MAX_PER_CATEGORY = 20
MAX_AGE_DAYS = 7
OUTPUT_PATH = Path("docs/India_news.json")

CATEGORY_KEYWORDS = {
    "Diplomacy": [
        "diplomacy", "diplomatic", "foreign minister", "ministry of external affairs",
        "bilateral", "treaty", "ambassador", "embassy", "united nations", "UN",
        "summit", "foreign policy", "relations", "sanctions", "trade deal",
        "G20", "BRICS", "SCO", "ASEAN", "WTO", "IMF", "World Bank",
        "pakistan", "china", "USA", "russia", "visa", "consulate",
    ],
    "Military": [
        "military", "army", "navy", "air force", "defence", "defense",
        "soldier", "troops", "missile", "weapon", "war", "conflict",
        "border", "LAC", "LOC", "ceasefire", "airstrike", "operation",
        "DRDO", "IAF", "Indian Army", "Indian Navy", "nuclear",
        "terrorist", "terrorism", "insurgency", "paramilitary", "CRPF", "BSF",
    ],
    "Energy": [
        "energy", "oil", "gas", "petroleum", "coal", "solar", "wind",
        "renewable", "power plant", "electricity", "nuclear energy",
        "crude", "OPEC", "ONGC", "NTPC", "petroleum ministry",
        "fuel", "LPG", "CNG", "EV", "electric vehicle", "battery",
        "climate", "emission", "carbon", "green energy", "hydro",
    ],
    "Economy": [
        "economy", "economic", "GDP", "inflation", "RBI", "Reserve Bank",
        "budget", "fiscal", "trade", "export", "import", "rupee",
        "market", "stock", "NSE", "BSE", "sensex", "nifty",
        "bank", "finance", "tax", "GST", "revenue", "investment",
        "startup", "industry", "manufacturing", "agriculture", "farm",
        "unemployment", "growth", "recession", "interest rate",
    ],
    "Local Events": [
        "india", "state", "city", "district", "village", "flood",
        "earthquake", "cyclone", "disaster", "accident", "fire",
        "election", "vote", "rally", "protest", "court", "police",
        "crime", "arrest", "murder", "health", "hospital", "school",
        "festival", "weather", "rain", "drought", "road",
    ],
}

INDIA_KEYWORDS = [
    "india", "indian", "delhi", "mumbai", "bangalore", "bengaluru",
    "chennai", "kolkata", "hyderabad", "modi", "parliament", "lok sabha",
    "rajya sabha", "supreme court", "rupee", "BJP", "congress",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_india_related(text: str) -> bool:
    t = text.lower()
    return any(kw.lower() in t for kw in INDIA_KEYWORDS)


def categorize(text: str) -> str:
    t = text.lower()
    scores = {cat: 0 for cat in CATEGORIES}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in t:
                scores[cat] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Local Events"


def translate_to_english(text: str) -> str:
    if not text:
        return text
    try:
        lang = detect(text)
    except LangDetectException:
        lang = "en"
    if lang == "en":
        return text
    try:
        translator = GoogleTranslator(source="auto", target="en")
        return translator.translate(text)
    except Exception:
        return text


def parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            return datetime(*val[:6], tzinfo=timezone.utc)
    for attr in ("published", "updated"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return dateparser.parse(val).astimezone(timezone.utc)
            except Exception:
                pass
    return None


def fetch_feed(url: str, source_name: str) -> list[dict]:
    stories = []
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        print(f"  [WARN] Could not parse {url}: {e}")
        return stories

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    for entry in feed.entries:
        pub_date = parse_date(entry)
        if pub_date and pub_date < cutoff:
            continue

        title_raw = getattr(entry, "title", "") or ""
        link = getattr(entry, "link", "") or ""

        title = translate_to_english(title_raw.strip())

        combined = (title + " " + title_raw).lower()
        if not is_india_related(combined):
            continue

        category = categorize(combined)

        stories.append({
            "title": title,
            "source": source_name,
            "url": link,
            "published_date": pub_date.strftime("%Y-%m-%dT%H:%M:%SZ") if pub_date else None,
            "category": category,
        })

        time.sleep(0.05)

    return stories


def load_existing(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {cat: [] for cat in CATEGORIES}


def merge_stories(existing: dict, new_stories: list[dict]) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    result = {cat: [] for cat in CATEGORIES}

    for cat in CATEGORIES:
        for story in existing.get(cat, []):
            try:
                pub = datetime.fromisoformat(
                    story["published_date"].replace("Z", "+00:00")
                )
                if pub >= cutoff:
                    result[cat].append(story)
            except Exception:
                pass

    existing_urls = {s["url"] for cat in CATEGORIES for s in result[cat]}

    for story in new_stories:
        if story["url"] in existing_urls:
            continue
        cat = story["category"]
        result[cat].append(story)
        existing_urls.add(story["url"])

    for cat in CATEGORIES:
        result[cat].sort(
            key=lambda s: s.get("published_date") or "",
            reverse=True,
        )
        result[cat] = result[cat][:MAX_PER_CATEGORY]

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== India News Fetcher ===")
    all_new: list[dict] = []

    for source in SOURCES:
        print(f"\nFetching: {source['name']}")
        for feed_url in source["feeds"]:
            print(f"  → {feed_url}")
            stories = fetch_feed(feed_url, source["name"])
            print(f"     {len(stories)} relevant stories found")
            all_new.extend(stories)

    print(f"\nTotal new stories fetched: {len(all_new)}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = load_existing(OUTPUT_PATH)
    merged = merge_stories(existing, all_new)

    for cat in CATEGORIES:
        print(f"  {cat}: {len(merged[cat])} stories")
    print(f"  Total stored: {sum(len(v) for v in merged.values())}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
