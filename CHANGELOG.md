# Changelog

## 0.2.1 — 2026-10-04

- First GitHub Marketplace listing of the `kaggle-kflow` Action.
- README: removed release instructions.

## 0.2.0 — 2026-10-03

- GitHub Action `kaggle-kflow` at the repository root for Marketplace listing.
- Commands write `.kflow/last.json` and, on GitHub Actions, job outputs plus a step summary.
- `pip install kflow` tracks scores with the Kaggle API; `pip install kflow[sim]` adds local games.
- MIT license, release workflow, and example workflows that `uses:` this action.
- The Action never uploads to Kaggle (`submit` stays a local CLI flag).

## 0.1.0

- CLI for status, leaderboard, pull, preflight, gate, submit, tune, and auto.
