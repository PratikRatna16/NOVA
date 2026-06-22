#!/usr/bin/env python3
"""Wikipedia article summaries to JSON CLI tool."""
import argparse
import json
import sys
from typing import Optional
import requests

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"

def search_articles(search_term: str, limit: int, session: requests.Session) -> list[str]:
    """Search Wikipedia for articles and return their titles."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": search_term,
        "srlimit": limit,
        "format": "json",
    }
    try:
        response = session.get(WIKIPEDIA_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        raise RuntimeError(f"API request failed: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid API response: {e}") from e
    
    results = data.get("query", {}).get("search", [])
    if not results:
        return []
    
    return [r["title"] for r in results]

def fetch_summary(title: str, session: requests.Session) -> tuple[str, str]:
    """Fetch article summary for a given title."""
    params = {
        "action": "query",
        "prop": "extracts",
        "exintro": True,
        "explaintext": True,
        "titles": title,
        "format": "json",
    }
    try:
        response = session.get(WIKIPEDIA_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        return (title, f"Error fetching summary: {e}")
    except json.JSONDecodeError as e:
        return (title, f"Error parsing response: {e}")
    
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return (title, "No content found")
    
    page = next(iter(pages.values()))
    extract = page.get("extract", "No summary available")
    return (title, extract.strip() if extract else "No summary available")

def main():
    parser = argparse.ArgumentParser(
        description="Fetch Wikipedia article summaries and save to JSON",
        prog="wiki-scrape"
    )
    parser.add_argument("search_term", help="Search term or article title")
    parser.add_argument("-o", "--output", default="summaries.json", help="Output JSON file")
    parser.add_argument("-l", "--limit", type=int, default=5, help="Number of results")
    args = parser.parse_args()
    
    if args.limit < 1:
        parser.error("Limit must be a positive integer")
    
    session = requests.Session()
    session.headers.update({"User-Agent": "wiki-scrape/1.0 (https://example.com)"})
    
    titles = search_articles(args.search_term, args.limit, session)
    if not titles:
        print(f"No articles found for '{args.search_term}'")
        sys.exit(1)
    
    summaries = [fetch_summary(title, session) for title in titles]
    articles = [{"title": t, "summary": s} for t, s in summaries]
    
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"Error writing file: {e}")
        sys.exit(1)
    
    print(f"Saved {len(articles)} article summaries to {args.output}")

if __name__ == "__main__":
    main()