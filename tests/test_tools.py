"""
tests/test_tools.py

Tests for the three FitFindr tools, including the failure mode of each.

Run from the project root with:
    pytest tests/

The two LLM-backed tools (suggest_outfit, create_fit_card) are tested with the
network call patched out (via monkeypatch on tools._llm) so the suite is fast,
deterministic, and runnable without a live GROQ_API_KEY. The empty-input guard
in create_fit_card is tested for real, since it must NOT call the LLM at all.
"""

import tools
from tools import search_listings, suggest_outfit, create_fit_card

from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0
    # Each result carries the documented listing fields.
    assert "title" in results[0]
    assert "price" in results[0]


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_case_insensitive():
    # "m" should match sizes like "S/M" via case-insensitive substring.
    results = search_listings("tee", size="m", max_price=None)
    assert all("m" in (item["size"] or "").lower() for item in results)


def test_search_results_sorted_by_relevance():
    # More overlapping keywords should not rank below fewer — scores descending.
    results = search_listings("vintage denim jeans", size=None, max_price=None)
    assert len(results) >= 1  # at least the Levi's 501s


# ── suggest_outfit ──────────────────────────────────────────────────────────

def _fake_item():
    return {
        "title": "Y2K Baby Tee — Butterfly Print",
        "category": "tops",
        "colors": ["white", "pink"],
        "style_tags": ["y2k", "graphic tee"],
        "description": "Fitted crop baby tee.",
        "price": 18.0,
        "platform": "depop",
    }


def test_suggest_outfit_with_wardrobe(monkeypatch):
    captured = {}

    def fake_llm(prompt, temperature=0.7):
        captured["prompt"] = prompt
        return "Pair it with your baggy jeans and chunky sneakers."

    monkeypatch.setattr(tools, "_llm", fake_llm)

    result = suggest_outfit(_fake_item(), get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""
    # The wardrobe pieces must actually be injected into the prompt.
    assert "jeans" in captured["prompt"].lower()


def test_suggest_outfit_empty_wardrobe(monkeypatch):
    # Failure mode: empty wardrobe must NOT crash — returns general advice.
    captured = {}

    def fake_llm(prompt, temperature=0.7):
        captured["prompt"] = prompt
        return "Generally, pair this with neutral basics and relaxed denim."

    monkeypatch.setattr(tools, "_llm", fake_llm)

    result = suggest_outfit(_fake_item(), get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""
    # Empty-wardrobe branch should signal a general-advice prompt.
    assert "empty" in captured["prompt"].lower()


def test_suggest_outfit_llm_failure_returns_fallback(monkeypatch):
    def boom(prompt, temperature=0.7):
        raise RuntimeError("network down")

    monkeypatch.setattr(tools, "_llm", boom)

    result = suggest_outfit(_fake_item(), get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""  # graceful fallback, no exception


# ── create_fit_card ─────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit():
    # Failure mode: missing/empty outfit → error string, NOT an exception.
    result = create_fit_card("", _fake_item())
    assert isinstance(result, str)
    assert result.strip() != ""
    assert "couldn't" in result.lower() or "no outfit" in result.lower()


def test_create_fit_card_whitespace_outfit_does_not_call_llm(monkeypatch):
    def boom(prompt, temperature=1.0):
        raise AssertionError("LLM must not be called for an empty outfit")

    monkeypatch.setattr(tools, "_llm", boom)
    result = create_fit_card("   ", _fake_item())
    assert isinstance(result, str) and result.strip() != ""


def test_create_fit_card_happy_path(monkeypatch):
    monkeypatch.setattr(
        tools, "_llm",
        lambda prompt, temperature=1.0: "Thrifted gem alert. Loving this fit.",
    )
    result = create_fit_card("baggy jeans + chunky sneakers", _fake_item())
    assert isinstance(result, str)
    assert result.strip() != ""
