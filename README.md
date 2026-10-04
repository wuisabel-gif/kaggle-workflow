# kflow

Track Kaggle simulation agents, gate them locally, and keep a record of every upload.

[![tests](https://github.com/wuisabel-gif/kaggle-workflow/actions/workflows/tests.yml/badge.svg)](https://github.com/wuisabel-gif/kaggle-workflow/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Game strategy stays in your competition repo. kflow handles the Kaggle workflow around it, for any `kaggle_environments` competition.

## GitHub Action

```yaml
name: track
on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:
permissions:
  contents: write
jobs:
  record:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: wuisabel-gif/kaggle-workflow@v1
        with:
          kaggle-api-token: ${{ secrets.KAGGLE_API_TOKEN }}
          commit: true
```

That run records every submission, writes rank into the job summary, and (when `commit: true`) pushes `.kflow/ratings.csv`. The Action never uploads an agent.

Pin a release tag (`@v1` or `@v0.2.0`) once you have published one. Until then, `@main` works on the public repo.

### Inputs

| Input | Default | Notes |
|---|---|---|
| `command` | `auto` | `auto`, `status`, `leaderboard`, `preflight`, `gate` |
| `kaggle-api-token` | empty | Required for `auto`, `status`, `leaderboard` |
| `record` | `true` | `status --record` |
| `commit` | `false` | Commit `ratings.csv` (needs `contents: write`) |
| `file` | empty | Agent path for `preflight` / `gate` |
| `opponents` | empty | Comma list for `gate` |
| `seeds` | `1-8` | Gate seeds |
| `baseline` | empty | Gate baseline on the same seeds and seats |
| `tune` | empty | `tune.toml` for `auto` (still does not submit) |

### Outputs

`rank`, `score`, `teams`, `submission_count`, `best_ref`, `best_score`, `passed`, `mean_reward`, `baseline_delta`

### Gate a pull request

```yaml
- uses: actions/checkout@v4
- uses: wuisabel-gif/kaggle-workflow@v1
  with:
    command: gate
    file: main.py
    opponents: starter
    baseline: main.py
    seeds: 1-8
```

Copy-paste workflows: [`examples/track.yml`](examples/track.yml), [`examples/gate.yml`](examples/gate.yml).

## Install the CLI

```bash
pip install kflow            # status, leaderboard, submit, pull
pip install 'kflow[sim]'     # preflight, gate, tune, auto --tune
```

From this repo: `pip install -e ".[sim]"`. If the `kflow` script is not on your PATH, run `python3 -m kflow`. Credentials are the usual Kaggle ones (`~/.kaggle/access_token` or `KAGGLE_API_TOKEN`).

## Configure

Put a `kflow.toml` at the root of the competition repo:

```toml
competition = "kaggriculture"    # Kaggle competition slug
env = "kaggriculture"            # kaggle_environments name (defaults to competition)
team = "agentic warriors"        # leaderboard team name, used to find our rank
data_dir = ".kflow"              # defaults to .kflow
```

kflow finds the nearest `kflow.toml` above the current directory. Everything it writes goes under `data_dir`:

| Path | Contents | Commit it? |
|---|---|---|
| `ledger.jsonl` | One row per upload: ref, file, SHA-256, git commit, dirty flag, message | Yes |
| `ratings.csv` | Score of every submission at each `status --record` snapshot | Yes |
| `last.json` | Machine-readable result of the last command (Action outputs) | No |
| `replays/` | Downloaded replays plus `index.jsonl` | No |
| `leaderboard/` | Latest full leaderboard download | No |

## Commands

```bash
kflow status                 # every submission, not just the first page of 20
kflow status --record        # ...and append the scores to ratings.csv
kflow leaderboard --top 20   # top teams plus our rank out of all teams
kflow pull --submission 56630481 --limit 20   # newest episodes of a submission
kflow pull --top 12 --per-team 6              # newest episodes of the top 12
kflow preflight main.py      # load as Kaggle does, then a short self-play game
kflow gate cand.py --opponents starter,old/v14.py --seeds 1-8 --baseline main.py
kflow submit main.py -m "why this version"         # dry run: shows what would upload
kflow submit main.py -m "why this version" --yes   # preflight, upload, record in ledger
```

`gate` plays every opponent and seed in both seats. With `--baseline` it plays the same games with the baseline and reports the per-game reward difference, which removes most seed and town luck. Local results can still disagree with the live ladder; treat them as a check for regressions, not a forecast of rank.

`submit` never uploads without `--yes`, refuses if preflight fails, and warns when the file has uncommitted changes.

## Learning agent settings automatically

`kflow tune` is a policy search, a simple form of reinforcement learning. It treats top-level constants in your agent (`TARGET_HERD = 15`) as knobs, plays local games with many sampled settings, keeps the best quarter, re-centres on them, and repeats (the cross-entropy method). Every candidate is scored by its reward minus the unchanged agent's reward on the same seeds and seats.

```toml
# tune.toml
agent = "main_adaptive.py"        # file whose constants are tuned
baseline = "main_adaptive.py"     # compared against (defaults to agent)
opponents = ["main.py", "starter"]
seeds = "1-12"                    # training games
val_seeds = "101-108"             # held-out games, never used for training
iterations = 6
population = 8
min_gain = 0.01                   # held-out gain must beat 1% of baseline reward

[params.TARGET_HERD]
low = 12
high = 20
type = "int"

[params.JOBS_PER_HAND]
low = 5.0
high = 9.0
```

```bash
kflow tune tune.toml
```

The winner is re-played on `val_seeds` and only counts as better if it gains on games it never trained on. In a first Kaggriculture run with 4 training seeds, the best settings gained 7,099 in training and lost 15,769 held-out, which is why the default is now 12 training seeds. Each run writes every candidate, `log.jsonl`, `best.py` (a standalone, submittable file) and `summary.json` to `.kflow/tune/<time>/`. Only literal top-level assignments can be tuned.

## Automatic cycle

```bash
kflow auto                          # record scores and rank, write a report
kflow auto --tune tune.toml         # ...plus tune and validate
kflow auto --tune tune.toml --submit
```

`auto` records every submission's score, finds our rank, optionally tunes, and writes a report to `.kflow/auto/<time>.md`. With `--submit` it uploads the tuned agent, through the same preflight and ledger as `kflow submit`, but only if it passed held-out validation. Without `--submit` it never uploads. The GitHub Action runs `auto` without `--submit`.

## Tests

```bash
python3 -m unittest -v
```

The tests run offline against `connectx` and take a few seconds.

## Release and Marketplace

After this repo is on `main`:

1. Tag `v0.2.0` and create a GitHub Release.
2. On the release form, check **Publish this Action to the GitHub Marketplace**.
3. Accept the GitHub Marketplace Developer Agreement (account 2FA required).
4. Primary category: Continuous integration. Secondary: Utilities.
5. Optional: set repository secret `PYPI_API_TOKEN` so the release workflow can `twine upload`.

Until that release exists, competition repos can still `uses: wuisabel-gif/kaggle-workflow@main`.

## License

MIT. See [CHANGELOG](CHANGELOG.md) for releases.
