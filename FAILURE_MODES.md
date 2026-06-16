# FitFindr — Triggered Failure Modes (Milestone 5)

Each of the three tools has a deliberate failure mode. Below are the exact
commands used to trigger each one and the actual output — none raises an
exception; each returns a specific, actionable response.

---

## Failure 1 — `search_listings` returns zero results

**Trigger (tool in isolation):**
```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
```
**Output:**
```
[]
```
✅ Returns an empty list, no exception.

**Trigger (full agent on the same impossible query):**
```bash
python -c "from agent import run_agent; from utils.data_loader import get_example_wardrobe; \
s = run_agent(query='designer ballgown size XXS under \$5', wardrobe=get_example_wardrobe()); \
print(s['error']); print(s['fit_card'])"
```
**Output:**
```
No listings found for 'designer ballgown' under $5 in size XXS. Try widening
your budget, dropping the size filter, or using broader keywords.
None
```
✅ The agent names *what* failed (the description + the active price/size
filters) and *what to try next* — and `fit_card` stays `None`, proving the
loop short-circuited before calling `suggest_outfit` / `create_fit_card`.

---

## Failure 2 — `suggest_outfit` with an empty wardrobe

**Trigger:**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```
**Output (representative — LLM wording varies):**
```
I'm so excited you found this adorable Y2K baby tee. To style it, pair it with
high-waisted jeans or a flowy skirt in neutral colors like blue, black, or
beige to balance out the playful vibe. ... Overall, this tee suits a fun,
laid-back look that's perfect for casual days out.
```
✅ Returns useful general styling advice (not an empty string, not an
exception) by taking the empty-wardrobe branch.

---

## Failure 3 — `create_fit_card` with an empty outfit string

**Trigger:**
```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
```
**Output:**
```
I couldn't write a fit card because no outfit suggestion was available — try
searching again so I can style a specific piece.
```
✅ Returns a descriptive error-message string. The guard runs *before* any LLM
call, so no exception and no wasted API request.

---

## Automated coverage

These same failure modes are also covered by the pytest suite
(`tests/test_tools.py`): `test_search_empty_results`,
`test_suggest_outfit_empty_wardrobe`, and `test_create_fit_card_empty_outfit`.
Run all 11 tests with:
```bash
pytest tests/
```
