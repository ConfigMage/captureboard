#!/usr/bin/env python3
"""Research pending capture items using Claude with web search."""

import json
import os
import sys

import anthropic
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

SYSTEM_PROMPT = """You are a research assistant. The user will give you something they want to check out — it could be a movie, TV show, book, podcast, article, music, or something else.

Your job:
1. Figure out what it is using web search.
2. Categorize it as one of: movie, tv, book, podcast, article, music, misc
3. Research it and gather key details.
4. Write a compelling 2-3 sentence summary — a pitch for why it's worth checking out.

Return a JSON object (no markdown fencing) with these fields:
{
  "title": "The proper title",
  "category": "movie|tv|book|podcast|article|music|misc",
  "summary": "2-3 sentence compelling pitch",
  "source_url": "relevant URL if found, or null",
  "details": { ... category-specific metadata ... }
}

Category-specific details fields:
- movie/tv: year, director, cast (array), genre, where_to_watch (array), rating
- book: author, genre, page_count, goodreads_rating
- podcast: show_name, episode_title, duration, topics (array)
- article: author, publication, date_published, key_takeaways (array)
- music: artist, album, genre, similar_to (array)

Return ONLY valid JSON, no other text."""


def research_item(client: anthropic.Anthropic, raw_input: str) -> dict:
    """Use Claude with web search to research a single item."""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": f"Research this: {raw_input}"}],
    )

    # Extract the text response (may come after tool use blocks)
    text_content = ""
    for block in response.content:
        if block.type == "text":
            text_content += block.text

    if not text_content.strip():
        raise ValueError("No text response from Claude")

    # Parse JSON from the response — strip markdown fencing if present
    text = text_content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)


def main():
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Fetch pending items
    result = supabase.table("items").select("*").eq("status", "pending").execute()
    items = result.data

    if not items:
        print("No pending items to research.")
        return

    print(f"Found {len(items)} pending item(s) to research.")

    for item in items:
        print(f"\nResearching: {item['raw_input']}")
        try:
            data = research_item(client, item["raw_input"])

            supabase.table("items").update(
                {
                    "title": data.get("title"),
                    "category": data.get("category"),
                    "summary": data.get("summary"),
                    "source_url": data.get("source_url"),
                    "details": data.get("details", {}),
                    "status": "new",
                }
            ).eq("id", item["id"]).execute()

            print(f"  ✓ {data.get('title')} [{data.get('category')}]")

        except Exception as e:
            print(f"  ✗ Error researching '{item['raw_input']}': {e}", file=sys.stderr)
            continue

    print("\nDone.")


if __name__ == "__main__":
    main()
