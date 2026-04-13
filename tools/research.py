#!/usr/bin/env python3
"""Research pending capture items using Claude with web search."""

import json
import os
import sys
import time

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


def call_api(client: anthropic.Anthropic, model: str, messages: list) -> anthropic.types.Message:
    """Call the API with retry logic for overloaded errors."""
    max_retries = 4
    for attempt in range(max_retries):
        try:
            return client.messages.create(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
                messages=messages,
            )
        except anthropic.APIStatusError as e:
            if e.status_code in (429, 529) and attempt < max_retries - 1:
                wait = 10 * (attempt + 1)
                print(f"    Retrying in {wait}s (status {e.status_code})...")
                time.sleep(wait)
            else:
                raise


def research_item(client: anthropic.Anthropic, raw_input: str) -> dict:
    """Use Claude with web search to research a single item."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": f"Research this: {raw_input}"}]

    # Agentic loop — keep going until we get a final text response
    for _turn in range(10):
        response = call_api(client, model, messages)

        if response.stop_reason == "end_turn":
            break

        # Model wants to continue (e.g. after web search) — append and loop
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": [
            {"type": "text", "text": "Continue."}
        ]})

    # Extract the text response from the final message
    text_content = ""
    for block in response.content:
        if block.type == "text":
            text_content += block.text

    if not text_content.strip():
        raise ValueError(f"No text response from Claude. Stop reason: {response.stop_reason}. "
                         f"Content types: {[b.type for b in response.content]}")

    # Parse JSON from the response — strip markdown fencing if present
    text = text_content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    # Try to find JSON object in the response if direct parse fails
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
        raise ValueError(f"Could not parse JSON from response: {text[:200]}")


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
