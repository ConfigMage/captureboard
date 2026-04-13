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

SYSTEM_PROMPT = """You are a research assistant that outputs ONLY JSON. No prose, no explanation, no markdown.

The user gives you something to check out. Use web search to research it, then respond with exactly one JSON object:

{"title":"proper title","category":"movie|tv|book|podcast|article|music|misc","summary":"2-3 sentence pitch for why it's worth checking out","source_url":"URL or null","details":{}}

Details fields by category:
- movie/tv: year, director, cast[], genre, where_to_watch[], rating
- book: author, genre, page_count, goodreads_rating
- podcast: show_name, episode_title, duration, topics[]
- article: author, publication, date_published, key_takeaways[]
- music: artist, album, genre, similar_to[]

YOUR ENTIRE RESPONSE MUST BE A SINGLE JSON OBJECT. No other text before or after."""


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
    model = "claude-haiku-4-5-20251001"
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

    result = extract_json(response)
    if result:
        return result

    # If no JSON in the response, ask the model to reformat
    print("    No JSON found, asking model to reformat...")
    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": (
        "Please respond with ONLY a JSON object, no other text. "
        "Format: {\"title\":\"...\",\"category\":\"...\",\"summary\":\"...\","
        "\"source_url\":\"...\",\"details\":{...}}"
    )})
    response = call_api(client, model, messages)
    result = extract_json(response)
    if result:
        return result

    raise ValueError("Could not get JSON response from Claude")


def extract_json(response) -> dict | None:
    """Extract a JSON object from the API response."""
    text_content = ""
    for block in response.content:
        if block.type == "text":
            text_content += block.text

    text = text_content.strip()
    if not text:
        return None

    # Strip markdown fencing
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Look for JSON object within the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return None


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
