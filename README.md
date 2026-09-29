# kflow

One command for the Kaggle side of a simulation competition: check scores,
read the leaderboard, download replays, check an agent before upload, compare
agents locally, and submit with a record of exactly what was uploaded.

Game strategy stays in your competition repo. kflow only handles the Kaggle
workflow around it, and works for any `kaggle_environments` competition.

## Install

```bash
pip install -e ~/kaggle-workflow
```

If the `kflow` script lands outside your PATH (as the `kaggle` CLI did on
macOS), run it as `python3 -m kflow` instead. Kaggle credentials are read the
usual way (`~/.kaggle/access_token` or `KAGGLE_API_TOKEN`).

## Configure

Put a `kflow.toml` at the root of the competition repo:

```toml
competition = "kaggriculture"    # Kaggle competition slug
env = "kaggriculture"            # kaggle_environments name (defaults to competition)
team = "agentic warriors"        # leaderboard team name, used to find our rank
data_dir = ".kflow"              # defaults to .kflow
```

kflow finds the nearest `kflow.toml` above the current directory. Everything it
writes goes under `data_dir`:

| Path | Contents | Commit it? |
|---|---|---|
| `ledger.jsonl` | One row per upload: ref, file, SHA-256, git commit, dirty flag, message | Yes |
| `ratings.csv` | Score of every submission at each `status --record` snapshot | Yes |
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

`gate` plays every opponent and seed in both seats. With `--baseline` it plays
the same games with the baseline and reports the per-game reward difference,
which removes most seed and town luck. Local results can still disagree with
the live ladder; treat them as a check for regressions, not a forecast of rank.

`submit` never uploads without `--yes`, refuses if preflight fails, and warns
when the file has uncommitted changes.

## Scheduled tracking

[`examples/track.yml`](examples/track.yml) is a GitHub Actions workflow for the
competition repo. It records scores daily and commits `ratings.csv`, so the
rating history builds up without anyone remembering to run it. It needs a
`KAGGLE_API_TOKEN` repository secret.

## Tests

```bash
python3 -m unittest -v
```

The tests run offline against `connectx` and take a few seconds.
