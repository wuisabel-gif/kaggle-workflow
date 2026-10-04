"""Map GitHub Action inputs (env) to a kflow CLI invocation. Never submits."""
from __future__ import annotations

import os
import sys

ALLOWED = {"status", "leaderboard", "auto", "preflight", "gate"}


def build_argv(env: dict) -> list[str]:
    command = (env.get("KFLOW_COMMAND") or "auto").strip()
    if command not in ALLOWED:
        sys.exit(
            f"unsupported command {command!r}; "
            f"use one of {', '.join(sorted(ALLOWED))}"
        )
    argv = [command]
    if command == "status" and (env.get("KFLOW_RECORD") or "true").lower() == "true":
        argv.append("--record")
    if command == "leaderboard":
        argv.extend(["--top", env.get("KFLOW_TOP") or "20"])
    if command in {"preflight", "gate"}:
        path = (env.get("KFLOW_FILE") or "").strip()
        if not path:
            sys.exit(f"{command} requires input 'file'")
        argv.append(path)
    if command == "gate":
        opponents = (env.get("KFLOW_OPPONENTS") or "").strip()
        if not opponents:
            sys.exit("gate requires input 'opponents'")
        argv.extend(["--opponents", opponents])
        seeds = (env.get("KFLOW_SEEDS") or "").strip()
        if seeds:
            argv.extend(["--seeds", seeds])
        baseline = (env.get("KFLOW_BASELINE") or "").strip()
        if baseline:
            argv.extend(["--baseline", baseline])
    if command in {"preflight", "gate"}:
        steps = (env.get("KFLOW_STEPS") or "").strip()
        if steps:
            argv.extend(["--steps", steps])
    if command == "auto":
        tune = (env.get("KFLOW_TUNE") or "").strip()
        if tune:
            argv.extend(["--tune", tune])
    return argv


def main() -> None:
    argv = build_argv(os.environ)
    os.execvp("kflow", ["kflow", *argv])


if __name__ == "__main__":
    main()
