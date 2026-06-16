# FitFindr 🛍️

FitFindr is a small tool-using agent that helps you shop secondhand. You
describe what you're after in plain language ("vintage graphic tee under $30,
size M"); the agent finds the best-matching listing, suggests outfits built
from pieces you already own, and writes a shareable "fit card" caption for the
find. It runs as a Gradio web app.

The interesting part isn't the three tools — it's the **planning loop** that
decides, based on what each tool returns, whether to keep going or stop and
explain what went wrong. See [planning.md](planning.md) for the full design
spec and agent diagram.

**🎥 Demo video:** https://www.loom.com/share/6a09c8666b834d0fa03c26996c52c501

---

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (free key at
[console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

## Run

```bash
python app.py
```

Open the URL printed in your terminal — usually `http://localhost:7860`, but
**check the output**, the port can differ. Type a query, pick a wardrobe
(Example or Empty), and hit **Find it**.

CLI smoke test (no browser):

```bash
python agent.py        # runs a happy-path query and a no-results query
pytest tests/          # 11 tool tests, including every failure mode
```

---

## Tool Inventory

The agent uses three tools, defined in [tools.py](tools.py). Tool 1 is pure
Python (no LLM); Tools 2 and 3 call Groq's `llama-3.3-70b-versatile`.

### 1. `search_listings(description, size, max_price) -> list[dict]`

**Purpose:** Find the secondhand listings that best match the user's request.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `description` | `str` | Keywords describing the item (e.g. `"vintage graphic tee"`). Scored by keyword overlap against each listing's title, description, and style tags. |
| `size` | `str \| None` | Size to filter by. Matched case-insensitively as a substring, so `"M"` matches `"S/M"`. `None` skips size filtering. |
| `max_price` | `float \| None` | Inclusive price ceiling in dollars. `None` skips price filtering. |

**Returns:** A `list[dict]` sorted by relevance (best match first). Each dict is
a full listing: `id`, `title`, `description`, `category`, `style_tags` (list),
`size`, `condition`, `price` (float), `colors` (list), `brand` (str or `None`),
`platform`. Returns `[]` when nothing matches — never raises.

### 2. `suggest_outfit(new_item, wardrobe) -> str`

**Purpose:** Suggest 1–2 complete outfits pairing the found item with the
user's existing clothes.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `new_item` | `dict` | The selected listing dict (the item being styled). |
| `wardrobe` | `dict` | A wardrobe with an `"items"` list; each item has `id`, `name`, `category`, `colors`, `style_tags`, `notes`. May be empty. |

**Returns:** A non-empty `str`. With a stocked wardrobe it names specific pieces
("pair it with your baggy straight-leg jeans…"). With an empty wardrobe it
returns general styling advice instead.

### 3. `create_fit_card(outfit, new_item) -> str`

**Purpose:** Turn an outfit suggestion into a casual, shareable social caption.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `outfit` | `str` | The outfit suggestion string from `suggest_outfit()`. |
| `new_item` | `dict` | The same listing dict, supplying the title, price, and platform the caption mentions. |

**Returns:** A `str` of 2–4 sentences usable as an OOTD caption. Uses a high LLM
temperature (1.0) so repeated calls on the same input produce varied phrasing.

---

## How the Planning Loop Works

The loop lives in `run_agent()` in [agent.py](agent.py). It is a **fixed
pipeline with one decision point** — it does *not* call all three tools
unconditionally. Every step reads from and writes to a single `session` dict.

1. **Initialize** a fresh session (`_new_session`).
2. **Parse** the query with regex (`parse_query`) into `description`, `size`,
   and `max_price`, stored in `session["parsed"]`. Price comes from a number
   after `$`/`under`/`below`; size from `size <token>` or a standalone size
   token; the leftover words become the description.
3. **Search.** Call `search_listings` with the parsed parameters. **This is the
   decision point:**
   - **If the result list is empty** → write a filter-aware message to
     `session["error"]` and **return immediately**. The two LLM tools are never
     called, so the agent never burns an API request styling a nonexistent item.
   - **If the list is non-empty** → set `session["selected_item"] =
     search_results[0]` (the top-ranked match) and continue.
4. **Suggest an outfit** from the selected item + wardrobe → `outfit_suggestion`.
5. **Create a fit card** from the outfit + item → `fit_card`.
6. **Return** the session.

So the agent makes one real decision — *did the search find anything?* — and
that decision changes the entire rest of the run. A matching query produces
three populated panels; a hopeless query produces one helpful error and two
empty panels.

## State Management

There is no hidden state and no re-prompting between steps. A single `session`
dict (created by `_new_session()` in [agent.py](agent.py)) is the single source
of truth for one interaction. Each step writes its output back into the
session, and the next step reads from it:

| Field | Written by | Read by |
|-------|-----------|---------|
| `query` | init | parse step |
| `parsed` | parse step | `search_listings` |
| `search_results` | `search_listings` | empty-check + selection |
| `selected_item` | selection (`= search_results[0]`) | `suggest_outfit`, `create_fit_card`, UI |
| `wardrobe` | init (from caller) | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card`, UI |
| `fit_card` | `create_fit_card` | UI |
| `error` | any early-exit step | caller (checked first) |

Because state flows by passing the same dict object, the item that goes into
`suggest_outfit` is literally `search_results[0]` — verified at runtime:
`session["selected_item"] is session["search_results"][0]` evaluates to `True`.
The UI layer (`handle_query` in [app.py](app.py)) checks `session["error"]`
first: if set, it shows the message and leaves the other two panels blank;
otherwise it formats `selected_item` and shows the outfit and fit card.

---

## Error Handling

Each tool owns one failure mode and handles it without raising. The planning
loop and UI react accordingly. (All three are reproduced with commands and real
output in [FAILURE_MODES.md](FAILURE_MODES.md).)

| Tool | Failure mode | What the agent does |
|------|-------------|---------------------|
| `search_listings` | No listing matches the query | Returns `[]`. The loop sets a filter-aware error and exits early — the LLM tools never run, `fit_card` stays `None`. |
| `suggest_outfit` | Wardrobe is empty | Not an error. Branches to a general-advice prompt and still returns a useful string. (Also falls back to a safe string if the LLM call itself throws.) |
| `create_fit_card` | `outfit` is empty / whitespace | Returns a descriptive error string **before** calling the LLM — no exception, no wasted API request. |

**Concrete example from testing — the no-results path:**

```
$ python agent.py
...
=== No-results path ===
Error message: No listings found for 'designer ballgown' under $5 in size XXS.
Try widening your budget, dropping the size filter, or using broader keywords.
```

The query `"designer ballgown size XXS under $5"` returns zero listings. Rather
than crash or hand an empty list to `suggest_outfit`, the agent names *what*
failed (the description plus the active price and size filters) and offers
*three things to try*. Inspecting the session confirms `search_results == []`,
`selected_item`, `outfit_suggestion`, and `fit_card` are all `None`, and
`error` holds the message — proof the loop short-circuited correctly.

---

## AI Usage

I used Claude (via Claude Code) as the implementation assistant, driving it from
the specs in [planning.md](planning.md). Two specific instances:

**1. Implementing `search_listings`.** I gave Claude the Tool 1 block from
planning.md (all three parameters, the full list of fields a returned listing
contains, and the empty-results failure contract) plus the `load_listings()`
docstring from `utils/data_loader.py`. It produced a function that filtered by
price and size and scored by keyword overlap. **What I changed:** its first cut
scored against the title only, which missed relevant items described in their
`style_tags` (e.g. a tee tagged `graphic tee` but titled "Y2K Baby Tee"). I had
it score against title + description + style_tags combined, and added a
stopword filter so words like "looking"/"under"/"the" don't inflate scores. I
also confirmed it returned `[]` rather than raising, matching my spec, then
tested it against three queries before trusting it.

**2. Implementing the planning loop.** I gave Claude the Planning Loop, State
Management, and Architecture (the ASCII agent diagram) sections together, plus
the `run_agent()` skeleton. It produced a loop that called all three tools in
sequence. **What I overrode:** the generated version called `suggest_outfit`
even when `search_results` was empty (guarded only with a try/except), which
violates the diagram's early-exit branch. I rewrote it to `return session`
immediately after setting `error` on the empty-results case, so the LLM tools
are never reached on a failed search. I verified the branch by running
`python agent.py` and confirming the no-results case leaves `fit_card` as
`None`.

---

## Spec Reflection

**One way the spec helped:** drawing the agent diagram in planning.md *before*
coding — specifically the early-exit branch on `results=[]` and the deliberate
choice to treat an empty wardrobe as a normal branch rather than an error — gave
me a concrete shape to check generated code against. When the AI's first
planning-loop draft called all three tools unconditionally, I could see at a
glance that it didn't match the diagram's branch, and I knew exactly what to fix
(return early after setting `error`). The spec turned a vague "does this look
right?" into a precise diff against a picture.

**One way the implementation diverged, and why:** planning.md's walkthrough
assumed the parse step would yield a clean keyword `description` (e.g. just
`"vintage graphic tee"`). In practice my regex parser only strips the price and
size phrases, so the description still carries filler words (`"I'm looking for a
vintage graphic tee . I mostly wear baggy jeans..."`). I chose to accept this
divergence rather than build the LLM-backed `parse_query` tool I had floated as a
stretch idea: `search_listings` tokenizes the description and drops
stopwords/punctuation before scoring, so the leftover filler has no effect on
match quality, and avoiding an extra LLM call keeps each query faster and
cheaper. The cost (a slightly messy intermediate string) wasn't worth a more
complex parser for the core build.

---

## Project Layout

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example/empty wardrobes
├── utils/
│   └── data_loader.py         # load_listings(), get_example/empty_wardrobe()
├── tools.py                   # The three tools
├── agent.py                   # parse_query() + run_agent() planning loop
├── app.py                     # Gradio UI + handle_query()
├── tests/test_tools.py        # 11 pytest tests (incl. every failure mode)
├── planning.md                # Design spec + agent diagram
├── FAILURE_MODES.md           # Reproducible failure-mode triggers + output
└── requirements.txt
```
