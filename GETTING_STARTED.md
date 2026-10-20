# Getting started (beginner edition)

## Run it

From the PriceVow folder:

```
python3 -m venv .venv            # one-time: make a private Python for this project
source .venv/bin/activate        # turn it on (do this every new terminal)
pip install -r requirements.txt  # one-time: install the libraries
uvicorn app.main:app --reload    # start the web app
```

Open http://127.0.0.1:8000, fill in the form, get a quote. Ctrl+C stops it.

## Run the tests

```
pytest
```

All green = the money logic still works. Run this after every change.

## What each file is

| File | What it does | AI involved? |
| --- | --- | --- |
| app/scope.py | Turns form answers (and optionally photos) into a structured Scope | Claude vision, optional |
| app/gate.py | Decides whether we're confident enough to guarantee a price | Rules in v0, Jev in Phase 2 |
| app/pricing.py | Scope x rate card = price. Pure math | Never |
| app/rate_cards.py | Contractor pricing rules. PLACEHOLDER numbers until Phase 0 calls | Never |
| app/main.py | The web page: form in, quote out | No |
| data/golden_set_template.csv | The spreadsheet for your Phase 0 contractor calls | No |
| tests/ | Proof the pricing and gate behave | No |

## Turn on photo analysis (optional)

Get an API key from console.anthropic.com, then before starting the app:

```
export ANTHROPIC_API_KEY=sk-ant-...
```

Without a key the app still works - it just prices off the form answers
and refuses to guarantee (no photos = a visibility gap, by design).

## The one rule

The pricing engine (pricing.py) and rate cards never call a model.
Money logic stays deterministic so every quote is explainable,
testable, and reproducible. AI perceives and judges; code prices.
