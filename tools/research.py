#!/usr/bin/env python3
"""Research pending capture items using Claude with web search."""

import json
import os
import re
import sys
import time
import urllib.request

import anthropic
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

SYSTEM_PROMPT = """You are a research assistant that outputs ONLY JSON. No prose, no explanation, no markdown.

The user gives you something to check out. Use web search to research it thoroughly, then respond with exactly one JSON object:

{"title":"proper title","category":"movie|tv|book|podcast|article|music|misc","summary":"...","source_url":"primary URL or null","sources":["url1","url2"],"details":{}}

Field guidelines:
- summary: 4-6 sentences. Start with what it is and why it's interesting. Include key context (who made it, when, critical reception). End with who would enjoy it and why. Be specific and compelling, not generic.
- source_url: the single best link (official site, Wikipedia, etc.)
- sources: array of 2-5 URLs you found useful during research. Include a mix — official sites, reviews, articles. These help the user dig deeper.
- details: category-specific metadata (see below). Be thorough — fill in every field you can find.

Details fields by category:
- movie/tv: year, director, cast[], genre, where_to_watch[], rating, seasons (tv only), status (tv: "ongoing"/"ended")
- book: author, genre, page_count, goodreads_rating, year_published
- podcast: show_name, episode_title, duration, topics[], host
- article: author, publication, date_published, key_takeaways[]
- music: artist, album, genre, similar_to[], year
- misc: include whatever fields are relevant to the item

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
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
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
    messages = [{"role": "user", "content": f"Research this thoroughly: {raw_input}"}]

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
        "\"source_url\":\"...\",\"sources\":[],\"details\":{...}}"
    )})
    response = call_api(client, model, messages)
    result = extract_json(response)
    if result:
        return result

    raise ValueError("Could not get JSON response from Claude")


def clean_data(obj):
    """Recursively strip citation markup from all string values."""
    if isinstance(obj, str):
        return strip_citations(obj)
    if isinstance(obj, dict):
        return {k: clean_data(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_data(v) for v in obj]
    return obj


def strip_citations(text: str) -> str:
    """Remove <cite> tags and other markup from web search responses."""
    text = re.sub(r'<cite[^>]*>.*?</cite>', '', text, flags=re.DOTALL)
    text = re.sub(r'</?[a-zA-Z][^>]*>', '', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


def extract_json(response) -> dict | None:
    """Extract a JSON object from the API response."""
    text_content = ""
    for block in response.content:
        if block.type == "text":
            text_content += block.text

    text = strip_citations(text_content.strip())
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


def post_to_slack(data: dict):
    """Post researched item summary to Slack."""
    if not SLACK_WEBHOOK_URL:
        return

    category = data.get("category", "misc")
    title = data.get("title", "Unknown")
    summary = data.get("summary", "")
    source_url = data.get("source_url")
    sources = data.get("sources", [])
    details = data.get("details", {})

    # Build detail lines
    detail_parts = []
    for key, value in details.items():
        if value is None or value == "" or value == []:
            continue
        label = key.replace("_", " ").title()
        if isinstance(value, list):
            detail_parts.append(f"*{label}:* {', '.join(str(v) for v in value)}")
        else:
            detail_parts.append(f"*{label}:* {value}")

    # Build sources section
    source_lines = ""
    if sources:
        links = [f"<{url}|{i+1}>" for i, url in enumerate(sources) if url]
        if links:
            source_lines = f"\n\n:link: *Read more:* {' | '.join(links)}"

    detail_text = "\n".join(detail_parts)

    text = (
        f":sparkles: *{title}* `{category}`\n\n"
        f"{summary}\n\n"
        f"{detail_text}"
        f"{source_lines}"
    )

    if source_url:
        text += f"\n\n<{source_url}|View source>"

    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"  Slack notification failed: {e}", file=sys.stderr)


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
            data = clean_data(research_item(client, item["raw_input"]))

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

            # Notify Slack
            post_to_slack(data)

        except Exception as e:
            print(f"  ✗ Error researching '{item['raw_input']}': {e}", file=sys.stderr)
            continue

    print("\nDone.")


if __name__ == "__main__":
    main()
