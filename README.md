# kflow

One command for the Kaggle side of a simulation competition: check scores,
read the leaderboard, download replays, check an agent before upload, compare
agents locally, tune an agent's settings by self-play, and submit with a record
of exactly what was uploaded.

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

## Learning agent settings automatically

`kflow tune` is a policy search, a simple form of reinforcement learning. It
treats top-level constants in your agent (`TARGET_HERD = 15`) as knobs, plays
local games with many sampled settings, keeps the best quarter, re-centres on
them, and repeats (the cross-entropy method). Every candidate is scored by its
reward minus the unchanged agent's reward on the same seeds and seats.

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

The winner is re-played on `val_seeds` and only counts as better if it gains on
games it never trained on. In a first Kaggriculture run with 4 training seeds,
the best settings gained 7,099 in training and lost 15,769 held-out, which is
why the default is now 12 training seeds. Each run writes every candidate,
`log.jsonl`, `best.py` (a standalone, submittable file) and `summary.json` to
`.kflow/tune/<time>/`. Only literal top-level assignments can be tuned.

## Automatic cycle

```bash
kflow auto                          # record scores and rank, write a report
kflow auto --tune tune.toml         # ...plus tune and validate
kflow auto --tune tune.toml --submit
```

`auto` records every submission's score, finds our rank, optionally tunes, and
writes a report to `.kflow/auto/<time>.md`. With `--submit` it uploads the
tuned agent, through the same preflight and ledger as `kflow submit`, but only
if it passed held-out validation. Without `--submit` it never uploads.

## Scheduled tracking

[`examples/track.yml`](examples/track.yml) is a GitHub Actions workflow for the
competition repo. It records scores daily and commits `ratings.csv`, so the
rating history builds up without anyone remembering to run it. It needs two
repository secrets: `KAGGLE_API_TOKEN`, and `KFLOW_REPO_TOKEN`, a read-only
token for this private repo so the workflow can install kflow.

## Tests

```bash
python3 -m unittest -v
```

The tests run offline against `connectx` and take a few seconds.
