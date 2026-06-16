"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Model used for the two LLM-backed tools (suggest_outfit, create_fit_card).
_MODEL = "llama-3.3-70b-versatile"

# Words that carry no filtering signal — dropped before keyword scoring so
# "a vintage graphic tee" scores on {vintage, graphic, tee}, not on "a".
_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "with", "in", "on", "of", "to",
    "i", "im", "looking", "want", "need", "some", "something", "that", "this",
    "under", "below", "over", "size", "around", "about", "my", "me", "is", "are",
}


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _llm(prompt: str, temperature: float = 0.7) -> str:
    """
    Send a single user prompt to the chat model and return its text.

    Raises on transport/API errors — callers are responsible for catching and
    falling back, since each tool has its own failure-mode contract.
    """
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return (response.choices[0].message.content or "").strip()


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-letters/digits, and drop stopwords."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in _STOPWORDS]


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    query_tokens = set(_tokenize(description))

    scored: list[tuple[int, dict]] = []
    for item in listings:
        # 1. Price filter (inclusive ceiling).
        if max_price is not None and item.get("price", 0) > max_price:
            continue

        # 2. Size filter — case-insensitive substring so "M" matches "S/M".
        if size is not None:
            item_size = (item.get("size") or "").lower()
            if size.strip().lower() not in item_size:
                continue

        # 3. Score by keyword overlap against title + description + style_tags.
        haystack = " ".join([
            item.get("title", ""),
            item.get("description", ""),
            " ".join(item.get("style_tags", [])),
        ])
        item_tokens = set(_tokenize(haystack))
        score = len(query_tokens & item_tokens)

        # 4. Drop listings with no relevant overlap.
        if score > 0:
            scored.append((score, item))

    # 5. Sort by score, highest first. Returns [] when nothing matched.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_desc = (
        f"{new_item.get('title', 'an item')} "
        f"(category: {new_item.get('category', 'unknown')}, "
        f"colors: {', '.join(new_item.get('colors', [])) or 'n/a'}, "
        f"style: {', '.join(new_item.get('style_tags', [])) or 'n/a'}). "
        f"{new_item.get('description', '')}"
    )

    items = wardrobe.get("items", []) if wardrobe else []

    if not items:
        # Empty wardrobe → general styling advice (not an error).
        prompt = (
            "You are a personal stylist. The user just found this secondhand item:\n"
            f"{item_desc}\n\n"
            "Their wardrobe is empty, so give general styling advice: what kinds of "
            "pieces (categories, colors, vibes) pair well with it, and what overall "
            "look it suits. Keep it to 3-5 sentences, friendly and concrete."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {w.get('name', 'item')} "
            f"({w.get('category', '?')}; {', '.join(w.get('colors', []))}; "
            f"{', '.join(w.get('style_tags', []))})"
            for w in items
        )
        prompt = (
            "You are a personal stylist. The user just found this secondhand item:\n"
            f"{item_desc}\n\n"
            "Here is the user's existing wardrobe:\n"
            f"{wardrobe_lines}\n\n"
            "Suggest 1-2 complete, wearable outfits that pair the new item with "
            "SPECIFIC pieces named from their wardrobe above. Reference each piece by "
            "name. Keep it concise (3-6 sentences total) and practical."
        )

    try:
        result = _llm(prompt, temperature=0.7)
    except Exception:
        result = ""

    if not result.strip():
        # Safe fallback so the planning loop can still proceed.
        return (
            f"Couldn't generate outfit ideas right now, but "
            f"{new_item.get('title', 'this piece')} works well as a layering base "
            "with neutral basics and your go-to denim."
        )
    return result


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against missing / empty outfit input.
    if not outfit or not outfit.strip():
        return (
            "I couldn't write a fit card because no outfit suggestion was "
            "available — try searching again so I can style a specific piece."
        )

    title = new_item.get("title", "this thrifted find")
    price = new_item.get("price")
    platform = new_item.get("platform", "a resale app")
    price_str = f"${price:.0f}" if isinstance(price, (int, float)) else "a steal"

    prompt = (
        "Write a short, casual social-media caption (an OOTD / fit-card post) for a "
        "thrifted outfit. 2-4 sentences. Sound like a real person posting their fit, "
        "NOT a product description.\n\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"Outfit: {outfit}\n\n"
        "Mention the item name, the price, and the platform naturally — once each. "
        "Capture the vibe in specific terms. Casual and authentic."
    )

    # 2. Higher temperature so repeated calls vary.
    try:
        result = _llm(prompt, temperature=1.0)
    except Exception:
        result = ""

    if not result.strip():
        # Minimal fallback caption built from the item fields.
        return f"Thrifted: {title} — just {price_str} on {platform}. 🛍️"
    return result
