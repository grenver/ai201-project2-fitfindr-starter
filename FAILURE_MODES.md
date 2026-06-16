# FitFindr — Triggered Failure Modes (Milestone 5)

Each of the three tools has a deliberate failure mode. Below are commands to
trigger each one and the actual output. None raises an exception; each returns
a specific, actionable response.

> **PowerShell note:** the commands below are written as **single lines** so they
> paste and run cleanly. A multi-line `python -c "..."` block pasted line-by-line
> stalls PowerShell at a `>>` continuation prompt — that is a paste issue, not a
> bug in the tools. If you prefer the multi-line form, select and paste the whole
> block at once.
>
> Run from the project root. `python` should resolve to the project venv
> (`.venv\Scripts\python.exe`). To make the em-dash render correctly in the
> console, run `$env:PYTHONIOENCODING='utf-8'` first.
>
> **`$` gotcha:** inside a double-quoted PowerShell string, `$5` is read as a
> variable and expanded to nothing before Python sees it. Escape it with a
> backtick — `` `$5 `` — so the literal price reaches the query.

---

## Failure 1 — `search_listings` returns zero results

**Trigger (tool in isolation):**
```powershell
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
```
**Output:**
```
[]
```
✅ Returns an empty list, no exception.

**Trigger (full agent on the same impossible query):**
```powershell
python -c "from agent import run_agent; from utils.data_loader import get_example_wardrobe; s = run_agent(query='designer ballgown size XXS under `$5', wardrobe=get_example_wardrobe()); print(s['error']); print(s['fit_card'])"
```
**Output:**
```
No listings found for 'designer ballgown' under $5 in size XXS. Try widening
your budget, dropping the size filter, or using broader keywords.
None
```
✅ The agent names *what* failed (the description + the active price/size
filters) and *what to try next*. `fit_card` stays `None`, proving the loop
short-circuited before calling `suggest_outfit` / `create_fit_card`.

---

## Failure 2 — `suggest_outfit` with an empty wardrobe

**Trigger:**
```powershell
python -c "from tools import search_listings, suggest_outfit; from utils.data_loader import get_empty_wardrobe; r = search_listings('vintage graphic tee', size=None, max_price=50); print(suggest_outfit(r[0], get_empty_wardrobe()))"
```
**Output (representative — LLM wording varies):**
```
I'm so excited you found this adorable Y2K baby tee. To style it, look for
high-waisted bottoms like jeans, skirts, or shorts in neutral colors like blue,
black, or beige to balance out the playful top. ... Overall, this tee suits a
fun, laid-back style with a touch of nostalgia and femininity.
```
✅ Returns useful general styling advice (not an empty string, not an
exception) by taking the empty-wardrobe branch.

---

## Failure 3 — `create_fit_card` with an empty outfit string

**Trigger:**
```powershell
python -c "from tools import search_listings, create_fit_card; r = search_listings('vintage graphic tee', size=None, max_price=50); print(create_fit_card('', r[0]))"
```
**Output:**
```
I couldn't write a fit card because no outfit suggestion was available — try
searching again so I can style a specific piece.
```
✅ Returns a descriptive error-message string. The guard runs *before* any LLM
call, so there is no exception and no wasted API request.

---

## Automated coverage

These same failure modes are also locked in by the pytest suite
(`tests/test_tools.py`): `test_search_empty_results`,
`test_suggest_outfit_empty_wardrobe`, and `test_create_fit_card_empty_outfit`.
Run all tests with:
```powershell
pytest tests/
```
