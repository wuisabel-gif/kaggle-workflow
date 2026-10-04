# Security

kflow talks to the Kaggle API with `KAGGLE_API_TOKEN` or `~/.kaggle/access_token`. Treat that token like a password. Store it as a GitHub Actions secret. Do not put it in `kflow.toml`, workflow YAML, or commit history.

The Action never submits an agent. `kflow submit --yes` and `kflow auto --submit` are local CLI flags. Do not add upload to CI.

Report a vulnerability privately via GitHub Security Advisories on this repository. Do not open a public issue for token leaks or API abuse.
