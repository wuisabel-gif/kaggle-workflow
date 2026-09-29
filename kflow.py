"""kflow: submit, track and study agents in Kaggle simulation competitions.

Run from a project directory that contains kflow.toml:

    competition = "kaggriculture"   # Kaggle competition slug
    env = "kaggriculture"           # kaggle_environments name (default: competition)
    team = "agentic warriors"       # our leaderboard team name
    data_dir = ".kflow"             # ledger, ratings history, replay cache

Commands: status, leaderboard, pull, preflight, gate, submit.
See README.md for examples.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import subprocess
import sys
import time
import tomllib
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

BAD_STATUSES = {"ERROR", "INVALID", "TIMEOUT"}


# Configuration and storage


def load_config(start: Path | None = None) -> dict:
    """Read the nearest kflow.toml at or above `start` and resolve data_dir."""
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        path = folder / "kflow.toml"
        if path.exists():
            config = tomllib.loads(path.read_text())
            if "competition" not in config:
                sys.exit(f"{path}: 'competition' is required")
            config.setdefault("env", config["competition"])
            config.setdefault("team", "")
            config["root"] = folder
            config["data_dir"] = folder / config.get("data_dir", ".kflow")
            return config
    sys.exit("no kflow.toml found here or in any parent directory")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def append_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if new:
            writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_state(path: Path) -> dict:
    """Commit and dirty flag for the file's repository; empty outside git."""
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=path.parent, capture_output=True, text=True
        )

    head = git("rev-parse", "HEAD")
    if head.returncode:
        return {}
    dirty = git("status", "--porcelain", "--", path.name).stdout.strip()
    return {"git_commit": head.stdout.strip(), "git_dirty": bool(dirty)}


# Kaggle API


def kaggle_api():
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    return api


def as_dict(value):
    return value.to_dict() if hasattr(value, "to_dict") else dict(value)


def all_submissions(api, competition: str) -> list[dict]:
    # The API defaults to 20 rows; reading only the first page hides history.
    return [as_dict(s) for s in api.competition_submissions(competition, page_size=200)]


def score(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def completed_episodes(api, submission_id: int) -> list[dict]:
    episodes = [as_dict(e) for e in api.competition_list_episodes(submission_id)]
    episodes = [e for e in episodes if "COMPLETED" in str(e.get("state"))]
    episodes.sort(key=lambda e: str(e.get("createTime")), reverse=True)
    return episodes


# Commands


def cmd_status(args, config):
    api = kaggle_api()
    subs = all_submissions(api, config["competition"])
    print(f"{'ref':>9}  {'submitted':16}  {'status':9} {'score':>7}  file / description")
    for s in subs:
        print(
            f"{s['ref']:>9}  {str(s['date'])[:16]:16}  {str(s['status'])[:9]:9} "
            f"{str(s.get('publicScore') or ''):>7}  {s['fileName']}: "
            f"{str(s.get('description') or '')[:70]}"
        )
    scored = [s for s in subs if score(s.get("publicScore")) is not None]
    if scored:
        best = max(scored, key=lambda s: score(s["publicScore"]))
        print(f"\n{len(subs)} submissions; best {best['ref']} at {best['publicScore']}")
    if args.record:
        stamp = now_utc()
        rows = [
            {"snapshot_utc": stamp, "ref": s["ref"], "status": s["status"],
             "score": s.get("publicScore") or ""}
            for s in subs
        ]
        path = config["data_dir"] / "ratings.csv"
        append_csv(path, rows, ["snapshot_utc", "ref", "status", "score"])
        print(f"recorded {len(rows)} rows to {path}")


def read_leaderboard(api, config) -> list[dict]:
    folder = config["data_dir"] / "leaderboard"
    folder.mkdir(parents=True, exist_ok=True)
    api.competition_leaderboard_download(config["competition"], path=str(folder))
    archive = max(folder.glob("*.zip"), key=lambda p: p.stat().st_mtime)
    with zipfile.ZipFile(archive) as bundle:
        name = next(n for n in bundle.namelist() if n.endswith(".csv"))
        text = bundle.read(name).decode("utf-8-sig")  # file starts with a BOM
    return list(csv.DictReader(text.splitlines()))


def cmd_leaderboard(args, config):
    rows = read_leaderboard(kaggle_api(), config)
    team = config["team"].lower()
    print(f"{len(rows)} teams")
    for row in rows[: args.top]:
        print(f"{row.get('Rank', ''):>5}  {row.get('Score', ''):>8}  {row.get('TeamName', '')}")
    ours = [r for r in rows if team and r.get("TeamName", "").lower() == team]
    for row in ours:
        rank = int(row.get("Rank") or 0)
        print(f"\nus: rank {rank} of {len(rows)} (top {100 * rank / len(rows):.0f}%), "
              f"score {row.get('Score')}")
    if team and not ours:
        print(f"\nteam {config['team']!r} not found on the leaderboard")


def download(api, replay_dir: Path, episode_id: int) -> bool:
    """Fetch one replay unless cached; True if it was downloaded."""
    if (replay_dir / f"episode-{episode_id}-replay.json").exists():
        return False
    api.competition_episode_replay(episode_id, path=str(replay_dir), quiet=True)
    time.sleep(0.3)  # stay polite to the API
    return True


def cmd_pull(args, config):
    api = kaggle_api()
    replay_dir = config["data_dir"] / "replays"
    replay_dir.mkdir(parents=True, exist_ok=True)
    jobs = []  # (label, submission_id, limit)
    if args.submission:
        jobs += [("ours", sid, args.limit) for sid in args.submission]
    if args.top:
        board = [as_dict(r) for r in api.competition_leaderboard_view(
            config["competition"], page_size=args.top)]
        for row in board[: args.top]:
            subs = [as_dict(s) for s in api.competition_team_submissions(int(row["teamId"]))]
            live = [s for s in subs if score(s.get("publicScore")) is not None]
            # The team's rated submission is the one whose score matches the board.
            live.sort(key=lambda s: abs(score(s["publicScore"]) - float(row["score"])))
            if live:
                jobs.append((row["teamName"], int(live[0]["id"]), args.per_team))
    fetched = cached = 0
    for label, sid, limit in jobs:
        for episode in completed_episodes(api, sid)[:limit]:
            got = download(api, replay_dir, int(episode["id"]))
            fetched += got
            cached += not got
            append_jsonl(replay_dir / "index.jsonl", {
                "episode": int(episode["id"]), "submission": sid, "label": label,
                "created": str(episode.get("createTime")),
                "agents": [
                    {k: as_dict(a).get(k) for k in ("teamName", "reward", "submissionId")}
                    for a in episode.get("agents") or []
                ],
            }) if got else None
        print(f"{label}: submission {sid}")
    print(f"{fetched} downloaded, {cached} already cached, in {replay_dir}")


def preflight(file: Path, env_name: str, steps: int) -> list[str]:
    """Load the agent the way Kaggle does and play a short self-play game."""
    from kaggle_environments import make
    from kaggle_environments.agent import get_last_callable

    problems = []
    source = file.read_text()
    try:
        compile(source, str(file), "exec")
        chosen = get_last_callable(source, path=str(file))
        print(f"loader picks: {getattr(chosen, '__name__', chosen)!r}")
    except Exception as error:  # report any load failure, not just syntax
        return [f"load failed: {error!r}"]
    env = make(env_name, configuration={"episodeSteps": steps}, debug=True)
    start = time.perf_counter()
    env.run([str(file), str(file)])
    elapsed = time.perf_counter() - start
    statuses = [s.status for s in env.steps[-1]]
    per_step = elapsed / max(1, len(env.steps) - 1)
    print(f"self-play {len(env.steps) - 1} steps: statuses {statuses}, "
          f"{per_step * 1000:.1f} ms per step")
    if BAD_STATUSES & set(statuses):
        problems.append(f"bad final status {statuses}")
    timeout = float(env.configuration.get("actTimeout", 0) or 0)
    if timeout and per_step / 2 > timeout:
        problems.append(f"{per_step / 2:.2f}s per action exceeds actTimeout {timeout}s")
    return problems


def cmd_preflight(args, config):
    problems = preflight(Path(args.file), config["env"], args.steps)
    for problem in problems:
        print(f"FAIL {problem}")
    print("PREFLIGHT " + ("FAILED" if problems else "PASSED"))
    sys.exit(1 if problems else 0)


def resolve_agent(value: str, root: Path) -> str:
    """Built-in agent names stay as-is; anything else is a path from root."""
    path = (root / value) if not Path(value).is_absolute() else Path(value)
    return str(path.resolve()) if path.exists() else value


def play(job):
    env_name, agent, opponent, seed, seat, steps = job
    from kaggle_environments import make

    configuration = {"seed": seed}
    if steps:
        configuration["episodeSteps"] = steps
    env = make(env_name, configuration=configuration)
    env.run([agent, opponent] if seat == 0 else [opponent, agent])
    final = env.steps[-1]
    return {
        "opponent": Path(opponent).stem, "seed": seed, "seat": seat,
        "reward": final[seat].reward, "opp_reward": final[1 - seat].reward,
        "status": final[seat].status,
    }


def run_games(env_name, agent, opponents, seeds, steps):
    jobs = [(env_name, agent, o, s, seat, steps)
            for o in opponents for s in seeds for seat in (0, 1)]
    with ProcessPoolExecutor() as pool:
        return list(pool.map(play, jobs))


def parse_seeds(text: str) -> list[int]:
    if "-" in text and "," not in text:
        low, high = text.split("-")
        return list(range(int(low), int(high) + 1))
    return [int(s) for s in text.split(",")]


def cmd_gate(args, config):
    root = config["root"]
    agent = resolve_agent(args.file, root)
    opponents = [resolve_agent(o, root) for o in args.opponents.split(",")]
    seeds = parse_seeds(args.seeds)
    games = run_games(config["env"], agent, opponents, seeds, args.steps)
    base = run_games(config["env"], resolve_agent(args.baseline, root), opponents,
                     seeds, args.steps) if args.baseline else None
    for index, game in enumerate(games):
        line = (f"{game['opponent']:>16} seed {game['seed']:>3} seat {game['seat']}  "
                f"{game['reward']!s:>9} vs {game['opp_reward']!s:>9}  {game['status']}")
        if base:
            line += f"   baseline {base[index]['reward']!s:>9}"
        print(line)
    rewards = [g["reward"] or 0 for g in games]
    wins = sum((g["reward"] or 0) > (g["opp_reward"] or 0) for g in games)
    print(f"\n{len(games)} games  W-L {wins}-{len(games) - wins}  "
          f"mean reward {sum(rewards) / len(rewards):.1f}")
    if base:
        # Same seeds and seats, so the per-game difference removes town/seed luck.
        deltas = [(g["reward"] or 0) - (b["reward"] or 0) for g, b in zip(games, base)]
        better = sum(d > 0 for d in deltas)
        worse = sum(d < 0 for d in deltas)
        print(f"vs baseline: mean delta {sum(deltas) / len(deltas):+.1f}, "
              f"better {better}, worse {worse}, same {len(deltas) - better - worse}")
    if any(g["status"] in BAD_STATUSES for g in games):
        sys.exit("an agent ended with a bad status")


def cmd_submit(args, config):
    file = Path(args.file).resolve()
    record = {"file": str(file.relative_to(config["root"])) if file.is_relative_to(config["root"]) else str(file),
              "sha256": sha256(file), "message": args.message, **git_state(file)}
    print(json.dumps(record, indent=1))
    if record.get("git_dirty"):
        print("warning: file has uncommitted changes")
    if not args.yes:
        sys.exit("dry run: nothing uploaded. Re-run with --yes to submit.")
    problems = preflight(file, config["env"], args.steps)
    if problems:
        sys.exit("preflight failed: " + "; ".join(problems))
    api = kaggle_api()
    before = {s["ref"] for s in all_submissions(api, config["competition"])}
    api.competition_submit(str(file), args.message, config["competition"], quiet=True)
    new = [s for s in all_submissions(api, config["competition"]) if s["ref"] not in before]
    record.update(submitted_utc=now_utc(), ref=new[0]["ref"] if new else None,
                  competition=config["competition"])
    append_jsonl(config["data_dir"] / "ledger.jsonl", record)
    print(f"submitted as {record['ref']}; recorded in {config['data_dir'] / 'ledger.jsonl'}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="kflow", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="list every submission and its score")
    p.add_argument("--record", action="store_true", help="append scores to ratings.csv")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("leaderboard", help="top teams and our rank")
    p.add_argument("--top", type=int, default=20)
    p.set_defaults(func=cmd_leaderboard)

    p = sub.add_parser("pull", help="download completed-episode replays")
    p.add_argument("--submission", type=int, action="append", help="submission id (repeatable)")
    p.add_argument("--limit", type=int, default=20, help="newest episodes per --submission")
    p.add_argument("--top", type=int, default=0, help="also pull the top N teams")
    p.add_argument("--per-team", type=int, default=6, help="newest episodes per top team")
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser("preflight", help="load an agent as Kaggle does and self-play")
    p.add_argument("file")
    p.add_argument("--steps", type=int, default=50)
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("gate", help="local games in both seats, optionally vs a baseline")
    p.add_argument("file")
    p.add_argument("--opponents", required=True, help="comma list of files or built-in agents")
    p.add_argument("--seeds", default="1-8", help="'1-8' or '1,7,42'")
    p.add_argument("--baseline", help="agent to compare on the same seeds and seats")
    p.add_argument("--steps", type=int, help="episodeSteps override")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("submit", help="preflight, upload and record a submission")
    p.add_argument("file")
    p.add_argument("-m", "--message", required=True)
    p.add_argument("--yes", action="store_true", help="actually upload (default is a dry run)")
    p.add_argument("--steps", type=int, default=50, help="preflight episode length")
    p.set_defaults(func=cmd_submit)

    args = parser.parse_args(argv)
    args.func(args, load_config())


if __name__ == "__main__":
    main()
