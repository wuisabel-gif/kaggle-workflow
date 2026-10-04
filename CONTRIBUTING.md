# Contributing

Install for development:

```bash
pip install -e ".[sim]"
python3 -m unittest -v
```

Keep game strategy out of this repo. kflow is the Kaggle workflow around a competition: API, ledger, local checks, tuning.

The GitHub Action is `action.yml` plus `scripts/run_action.py`. It must not grow a `--submit` path. Uploads stay behind `kflow submit --yes` on a machine the owner controls.

Do not add files that are not needed to run the CLI or the Action. Marketplace listings are tied to this repository as one unit.
