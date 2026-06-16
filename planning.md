# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock secondhand-listings dataset (loaded via `load_listings()`) and returns the items that best match what the user described, after filtering out anything over the price ceiling or in the wrong size. It is a deterministic, non-LLM tool — pure filtering and keyword scoring.

**Input parameters:**
- `description` (str): Free-text keywords describing the wanted item, e.g. `"vintage graphic tee"`. Used for keyword-overlap scoring against each listing's `title`, `description`, and `style_tags`. Required.
- `size` (str | None): Size string to filter by, e.g. `"M"`. Matched case-insensitively as a substring against the listing's `size` field so `"M"` matches `"S/M"` and `"XL (oversized)"`. `None` skips size filtering.
- `max_price` (float | None): Inclusive price ceiling in dollars. Listings with `price > max_price` are dropped. `None` skips price filtering.

**What it returns:**
A `list[dict]`, sorted by descending relevance score (best match first). Each dict is a full listing record from `listings.json` with these fields: `id` (str), `title` (str), `description` (str), `category` (str: tops/bottoms/outerwear/shoes/accessories), `style_tags` (list[str]), `size` (str), `condition` (str: excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str: depop/thredUp/poshmark). Listings whose keyword-overlap score is 0 are excluded entirely. Returns `[]` when nothing matches — it never raises.

**What happens if it fails or returns nothing:**
The tool returns an empty list rather than raising. The planning loop detects the empty list, sets `session["error"]` to a helpful message that names the parsed filters (e.g. `"No listings found for 'vintage graphic tee' under $30. Try removing the size or price filter, or using broader keywords."`), and returns the session early **without** calling `suggest_outfit` or `create_fit_card`.

---

### Tool 2: suggest_outfit

**What it does:**
Takes one listing (the item the user is considering) plus the user's wardrobe and asks the LLM (Groq) to propose 1–2 complete, wearable outfits that pair the new item with specific pieces the user already owns. If the wardrobe is empty, it instead returns general styling advice for the item on its own.

**Input parameters:**
- `new_item` (dict): A single listing dict (the top search result). Its `title`, `category`, `colors`, `style_tags`, and `description` are formatted into the prompt so the model knows what it is styling.
- `wardrobe` (dict): A wardrobe dict in the schema format — a dict with an `"items"` key holding a `list[dict]`. Each wardrobe item has: `id`, `name`, `category`, `colors` (list), `style_tags` (list), `notes` (str | None). May contain zero items.

**What it returns:**
A non-empty `str` of natural-language outfit suggestions. On the happy path it describes 1–2 outfits that name specific wardrobe pieces by their `name` (e.g. *"Pair it with your Baggy straight-leg dark-wash jeans and chunky white sneakers…"*). When the wardrobe is empty it returns general styling guidance (what categories/colors/vibes pair well) instead. The string is meant to be shown directly in the UI and is also passed verbatim into `create_fit_card`.

**What happens if it fails or returns nothing:**
- Empty wardrobe (`wardrobe["items"]` is empty) is **not** an error — the tool branches to a general-advice prompt and still returns a useful string.
- If the LLM call raises or returns an empty/whitespace string, the tool returns a safe fallback string such as `"Couldn't generate outfit ideas right now — but this piece works well as a layering base with neutral basics."` so the loop can still proceed. The planning loop treats any non-empty return as success.

---

### Tool 3: create_fit_card

**What it does:**
Turns an outfit suggestion plus the item details into a short, casual, shareable social-media caption (an "OOTD" / fit card) using the LLM at a higher temperature so repeated calls produce varied phrasing.

**Input parameters:**
- `outfit` (str): The outfit-suggestion string returned by `suggest_outfit()`. This is the creative source material for the caption.
- `new_item` (dict): The same listing dict used in Tool 2. Supplies the `title`, `price`, and `platform` that the caption must mention once each.

**What it returns:**
A `str` of 2–4 sentences usable as an Instagram/TikTok caption: casual and authentic, naming the item, its price, and the platform once each, capturing the outfit vibe. Higher LLM temperature keeps captions varied across runs.

**What happens if it fails or returns nothing:**
- Guards first: if `outfit` is `None`, empty, or whitespace-only, it returns a descriptive error string (e.g. `"Can't build a fit card without an outfit suggestion."`) rather than calling the LLM or raising.
- If the LLM call fails or returns empty, it returns a minimal fallback caption built from the item fields (e.g. `"Thrifted find: {title} — ${price} on {platform}. 🛍️"`) so the user always sees something.

---

### Additional Tools (if any)

None for the core build. (Stretch idea, not yet implemented: a `parse_query` LLM tool to extract `description`/`size`/`max_price` from the raw query; for the core build this parsing happens inline in the planning loop via regex — see State Management.)

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is a fixed, deterministic pipeline (no model-driven tool selection) with one early-exit branch. Each step reads from and writes to the session dict.

1. **Initialize** — `session = _new_session(query, wardrobe)`.
2. **Parse the query** — extract three values from `query` and store them in `session["parsed"]`:
   - `max_price`: regex for a number after `$`, `under`, or `below` (e.g. `under $30` → `30.0`); else `None`.
   - `size`: regex for `size <token>` or a standalone size token (`XS/S/M/L/XL` or a shoe number); else `None`.
   - `description`: the query with the price and size phrases stripped out, used as keywords.
3. **Branch A — call `search_listings(description, size, max_price)`.** Store the list in `session["search_results"]`.
   - **If `search_results` is empty:** set `session["error"]` to a message naming the parsed filters, and `return session` immediately. Do **not** call `suggest_outfit` or `create_fit_card`. ← this is the error branch.
   - **If `search_results` is non-empty:** set `session["selected_item"] = search_results[0]` (top-ranked match) and continue.
4. **Call `suggest_outfit(selected_item, wardrobe)`.** Store the string in `session["outfit_suggestion"]`. This always succeeds (empty wardrobe → general advice; LLM failure → fallback string), so there is no early exit here.
5. **Call `create_fit_card(outfit_suggestion, selected_item)`.** Store the string in `session["fit_card"]`.
6. **Done.** `return session` with `error` still `None`.

The loop "knows it's done" because the pipeline is finite: once `fit_card` is set (or `error` is set at step 3), there is nothing left to call. The only condition that changes behavior is whether `search_listings` returned results.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict created by `_new_session()` and threaded through every step — it is the single source of truth for one interaction. Nothing is passed via globals or return-value chaining between tools directly; each step writes its output back into the session, and the next step reads from it.

Tracked fields and who writes them:

| Field | Type | Written by | Read by |
|-------|------|-----------|---------|
| `query` | str | `_new_session` | parse step |
| `parsed` | dict (`description`, `size`, `max_price`) | parse step | `search_listings` call |
| `search_results` | list[dict] | `search_listings` | empty-check + selection |
| `selected_item` | dict \| None | selection step (`= search_results[0]`) | `suggest_outfit`, `create_fit_card`, UI |
| `wardrobe` | dict | `_new_session` (from caller) | `suggest_outfit` |
| `outfit_suggestion` | str \| None | `suggest_outfit` | `create_fit_card`, UI |
| `fit_card` | str \| None | `create_fit_card` | UI |
| `error` | str \| None | any step that exits early | caller / UI (checked first) |

The caller (`app.py` → `handle_query`) checks `session["error"]` first: if non-`None`, it shows the error and leaves the outfit/fit-card panels empty; otherwise it formats `selected_item` and shows `outfit_suggestion` and `fit_card`.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Loop sets `session["error"]` to a filter-aware message and returns early — e.g. *"No listings matched 'vintage graphic tee' under $30 in size M. Try widening your budget, dropping the size filter, or using more general keywords like 'graphic tee'."* No outfit or fit card is generated; the UI shows this message in the listing panel and leaves the other two panels blank. |
| suggest_outfit | Wardrobe is empty | Not treated as an error. The tool branches to a general-styling prompt and returns advice like *"Your wardrobe is empty, so here are general ways to style this piece: it leans casual/streetwear — pair it with dark denim or relaxed trousers and chunky sneakers, and layer an oversized jacket for colder days. Add one of these basics and I can suggest specific fits."* The loop continues normally to `create_fit_card`. |
| create_fit_card | Outfit input is missing or incomplete | The tool guards before calling the LLM: if `outfit` is `None`/empty/whitespace it returns *"I couldn't write a fit card because no outfit suggestion was available — try searching again so I can style a specific piece."* If the LLM itself fails, it returns a minimal caption built from the item fields (`"Thrifted: {title} — just ${price} on {platform}. 🛍️"`) so the user always sees a usable result. |

---

## Architecture

```
                          ┌─────────────────────────────────────┐
   User query  ──────────►│            PLANNING LOOP            │
   + wardrobe choice      │            (run_agent)              │
                          └─────────────────────────────────────┘
                                          │
                          ┌───────────────┴───────────────────────────────┐
                          ▼                                                │
                 parse query (regex)                                       │
                 Session: parsed = {description, size, max_price}          │
                          │                                                │
                          ▼                                                │
        search_listings(description, size, max_price)                      │
                          │                                                │
              results = []│                          results = [item, …]   │
                          ├───────────────────────┐         │              │
                          ▼                        │         ▼              │
            [ERROR] Session: error =               │   Session:            │
            "No listings found for '<desc>'        │   selected_item =     │
            under $<price> in size <size>…"        │   results[0]          │
                          │                        │         │              │
                          └──► return session ◄────┼─────────┼──────────────┤  ← error path
                                  (early exit)     │         │              │     terminates here
                                                   │         ▼              │
                                                   │  suggest_outfit(       │
                                                   │    selected_item,      │
                                                   │    wardrobe)           │
                                                   │   items==[] → general  │
                                                   │   advice (not an error)│
                                                   │         │              │
                                                   │  Session:              │
                                                   │  outfit_suggestion="…" │
                                                   │         │              │
                                                   │         ▼              │
                                                   │  create_fit_card(      │
                                                   │    outfit_suggestion,  │
                                                   │    selected_item)      │
                                                   │   empty outfit → guard │
                                                   │   message              │
                                                   │         │              │
                                                   │  Session: fit_card="…" │
                                                   │         │              │
                                                   └─────────┘              │
                                                             │              │
                                                             ▼              │
                                                   return session ◄─────────┘
                                                             │
                                                             ▼
                                              app.py handle_query:
                                              error? → show in listing panel
                                              else  → listing | outfit | fit_card
```

**Data flow summary:** every box reads from and writes to the shared `session` dict (see State Management). Solid arrows are the happy path; the `results = []` branch is the single early-exit error path, which writes `session["error"]` and returns before any LLM tool runs.

---

## AI Tool Plan

I'll use **Claude (Claude Code)** as the primary implementation assistant, giving it this `planning.md` as the spec and verifying each generated function against the spec before trusting it.

**Milestone 3 — Individual tool implementations:**

- **search_listings:** Give Claude the *Tool 1* block (all three params, the field list of a returned listing, and the empty-results failure mode) plus the `load_listings()` docstring from `utils/data_loader.py`. Ask it to implement filtering by `max_price` and `size` (case-insensitive substring) and keyword-overlap scoring of `description` against each listing's `title` + `description` + `style_tags`, dropping score-0 items and sorting descending. **Verify before use:** read the code to confirm it (a) filters by all three params, (b) drops zero-score items, (c) returns `[]` instead of raising on no match. Then run it against 3 queries — `"vintage graphic tee"` (expect the Y2K baby tee), `"size XXS ballgown under $5"` (expect `[]`), and `"jeans under $40"` (expect the Levi's 501s).
- **suggest_outfit:** Give Claude the *Tool 2* block plus the wardrobe item schema (id/name/category/colors/style_tags/notes). Ask for the empty-vs-non-empty branch and a Groq chat call. **Verify:** confirm the empty-wardrobe branch exists and returns advice (not `""`), and that the non-empty prompt actually injects wardrobe item `name`s. Test with `get_example_wardrobe()` (expect named pieces) and `get_empty_wardrobe()` (expect general advice).
- **create_fit_card:** Give Claude the *Tool 3* block (style guidelines, the empty-`outfit` guard, higher temperature). **Verify:** confirm the whitespace/`None` guard returns the error string without calling the LLM, and that title/price/platform each appear. Test by calling it twice with the same input to confirm the captions differ (temperature working).

**Milestone 4 — Planning loop and state management:**

Give Claude the *Planning Loop*, *State Management*, and *Architecture* (diagram) sections together, plus the `_new_session()` and `run_agent()` skeletons from `agent.py`. Ask it to implement the parse step (regex for price/size, remainder as description) and wire the five pipeline steps, writing each result into the session and taking the early-exit error branch when `search_results` is empty. **Verify before use:** trace the generated code against the diagram step by step — confirm (a) the empty-results branch sets `error` and returns *before* any LLM call, (b) `selected_item = search_results[0]`, and (c) every output field is written to the session. Then run `python agent.py` and check both the happy path (graphic-tee query fills all three fields, `error is None`) and the no-results path (`designer ballgown size XXS under $5` sets `error` and leaves `outfit_suggestion`/`fit_card` as `None`).

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"
*(Wardrobe choice: "Example wardrobe")*

**Step 1 — Initialize + parse.**
`run_agent` builds a fresh session and parses the query. The regex finds `under $30` → `max_price = 30.0`; no explicit `size <token>` is present → `size = None`; the cleaned keyword string becomes `description = "vintage graphic tee"`. Session now holds `parsed = {"description": "vintage graphic tee", "size": None, "max_price": 30.0}`.

**Step 2 — search_listings.**
Calls `search_listings("vintage graphic tee", None, 30.0)`. It drops anything over $30, scores the rest by keyword overlap, and returns a non-empty list. The top hit is the **Y2K Baby Tee — Butterfly Print** (`lst_002`, $18.00, depop, style_tags include `y2k`, `vintage`, `graphic tee`). Session: `search_results = [that tee, …]`, then `selected_item = search_results[0]`.

**Step 3 — suggest_outfit.**
Calls `suggest_outfit(selected_item, example_wardrobe)`. The wardrobe is non-empty, so the LLM gets the tee's details plus the wardrobe items and returns specific outfits naming real pieces, e.g. *"Tuck the butterfly baby tee into your baggy dark-wash straight-leg jeans, finish with chunky sneakers, and throw the oversized grey crewneck over your shoulders for a layered Y2K look."* Session: `outfit_suggestion = "…"`.

**Step 4 — create_fit_card.**
Calls `create_fit_card(outfit_suggestion, selected_item)` at higher temperature. Returns a 2–4 sentence caption mentioning the item, $18, and depop once each, e.g. *"Found my new fave: this Y2K Butterfly Baby Tee for just $18 on depop. Styled it with baggy jeans + chunky sneakers for that early-2000s-but-make-it-now vibe. Thrift wins only. ✨"* Session: `fit_card = "…"`, `error = None`.

**Final output to user:**
`handle_query` sees `error is None` and fills the three UI panels:
- **🛍️ Top listing found:** formatted `selected_item` — "Y2K Baby Tee — Butterfly Print · $18.00 · size S/M · excellent · depop" plus its description.
- **👗 Outfit idea:** the `outfit_suggestion` string.
- **✨ Your fit card:** the `fit_card` caption.
