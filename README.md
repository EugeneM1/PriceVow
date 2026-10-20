# PriceVow

**AI-powered binding quotes for home repair.** Snap photos or a short guided video of a repair job and get a guaranteed maximum price backed by a local contractor — no site visit needed to learn what a job costs.

Every existing tool in this space produces an *estimate* that gets re-quoted after a contractor visit. PriceVow binds the number: contractors pre-commit pricing rules, and the system only issues a guarantee when its calibrated confidence clears a threshold. A vow is a binding promise — that's the product.

## How it works

Three layers, each doing what it's best at:

1. **Perception — Claude vision.** Extracts a structured job scope (dimensions, materials, damage severity, visibility gaps) from photos or sampled video frames.
2. **Judgment — Jev (TypeSafe AI System One model).** Sub-second structured decisions: is this scope complete enough to bind? What's the risk tier? During guided video capture, it directs the camera in real time ("pan left", "show the corner") at ~2 decisions per second.
3. **Pricing — deterministic Python.** Scope × versioned contractor rate cards = a guaranteed ceiling. Money logic never goes through a model, so every quote is explainable and reproducible.

A calibration loop records predicted vs. invoiced cost on every completed job, continuously re-tuning the bind thresholds and risk spreads per zip code and job type.

## Status

Design phase. Phase 0 (manual concierge validation) targets fence repair in Los Angeles: prove ≤15% median quote error against real contractor prices before writing production code.

## Roadmap

| Phase | Scope | Gate to next |
| --- | --- | --- |
| 0 — Concierge | Manual quotes via neighborhood groups; golden set of reference prices | ≤15% median error + 5 real bookings |
| 1 — Photo MVP | FastAPI + Claude vision scope + Python pricing; first automated binds | 85% of bound quotes within ±15% |
| 2 — Guided video | Jev judgment layer; real-time capture direction | Overrun payouts under 5% |
| 3 — Multi-trade | Interior paint next; wider LA coverage | — |
