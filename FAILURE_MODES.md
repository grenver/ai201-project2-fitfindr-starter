# FitFindr — Triggered Failure Modes (Milestone 5)

Each tool has one deliberate failure mode. None raises an exception; each
returns a specific, actionable response. Commands below are verified.

> **PowerShell tips:** run from the project root (`python` = the venv). Keep
> each `python -c "..."` on one line — a pasted multi-line block stalls at a
> `>>` prompt. Escape `$` as `` `$ `` (a bare `$5` expands to nothing). Run
> `$env:PYTHONIOENCODING='utf-8'` once for correct em-dash rendering.

---

## Failure 1 — `search_listings` finds no matches

```powershell
python -c "from agent import run_agent; from utils.data_loader import get_example_wardrobe; s = run_agent(query='designer ballgown size XXS under `$5', wardrobe=get_example_wardrobe()); print(s['error']); print(s['fit_card'])"
```
```
No listings found for 'designer ballgown' under $5 in size XXS. Try widening
your budget, dropping the size filter, or using broader keywords.
None
```
✅ Returns `[]` (no exception); the loop sets a filter-aware error and exits
early, so `fit_card` stays `None` — `suggest_outfit`/`create_fit_card` never run.

**In the app:** query `designer ballgown size XXS under $5` (any wardrobe) →
error shows in the **🛍️ listing** panel, other two panels empty.

---

## Failure 2 — `suggest_outfit` with an empty wardrobe

```powershell
python -c "from app import handle_query; print(handle_query('vintage graphic tee under `$30', 'Empty wardrobe (new user)')[1])"
```
```
I'm so excited you found this adorable Y2K baby tee. To style it, look for
high-waisted bottoms in neutral colors... (general styling advice; wording varies)
```
✅ Takes the empty-wardrobe branch and returns useful general advice — not an
empty string, not an exception.

**In the app:** any matching query + **Empty wardrobe (new user)** → the
**👗 outfit** panel shows general advice; all three panels still populate.

---

## Failure 3 — `create_fit_card` with an empty outfit string

```powershell
python -c "from tools import search_listings, create_fit_card; r = search_listings('vintage graphic tee', size=None, max_price=50); print(create_fit_card('', r[0]))"
```
```
I couldn't write a fit card because no outfit suggestion was available — try
searching again so I can style a specific piece.
```
✅ The guard returns this string *before* any LLM call — no exception, no wasted
API request.

**In the app:** not reachable via the UI. The loop only calls `create_fit_card`
after `suggest_outfit`, which always returns a non-empty string, so an empty
outfit never reaches it. This is a defensive guard — trigger it via the direct
call above or the pytest test below.

---

## Automated coverage

The same three modes are locked in by `tests/test_tools.py`
(`test_search_empty_results`, `test_suggest_outfit_empty_wardrobe`,
`test_create_fit_card_empty_outfit`). Run: `pytest tests/`
