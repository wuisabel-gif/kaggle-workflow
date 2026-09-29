"""Offline checks; run: python3 -m unittest -v"""
import json
import tempfile
import unittest
from pathlib import Path

import kflow

AGENT = """
def helper(obs):
    return 0

def agent(obs, config):
    return next(c for c in range(config.columns) if obs.board[c] == 0)
"""


class ConfigTests(unittest.TestCase):
    def test_nearest_config_and_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "kflow.toml").write_text('competition = "connectx"\n')
            (root / "sub").mkdir()
            config = kflow.load_config(root / "sub")
            self.assertEqual(config["env"], "connectx")
            self.assertEqual(config["data_dir"], root / ".kflow")

    def test_missing_competition_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "kflow.toml").write_text('env = "connectx"\n')
            with self.assertRaises(SystemExit):
                kflow.load_config(Path(tmp))


class HelperTests(unittest.TestCase):
    def test_parse_seeds(self):
        self.assertEqual(kflow.parse_seeds("1-3"), [1, 2, 3])
        self.assertEqual(kflow.parse_seeds("1,7,42"), [1, 7, 42])

    def test_ledger_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d" / "ledger.jsonl"
            kflow.append_jsonl(path, {"ref": 1})
            kflow.append_jsonl(path, {"ref": 2})
            self.assertEqual([json.loads(l)["ref"] for l in path.read_text().splitlines()], [1, 2])


class GameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / "main.py"
        self.file.write_text(AGENT)

    def tearDown(self):
        self.tmp.cleanup()

    def test_preflight_passes_valid_agent(self):
        self.assertEqual(kflow.preflight(self.file, "connectx", 20), [])

    def test_preflight_reports_load_failure(self):
        self.file.write_text("def agent(:\n")
        self.assertTrue(kflow.preflight(self.file, "connectx", 20)[0].startswith("load failed"))

    def test_games_cover_both_seats(self):
        games = kflow.run_games("connectx", str(self.file), ["random"], [1], None)
        self.assertEqual(sorted(g["seat"] for g in games), [0, 1])


if __name__ == "__main__":
    unittest.main()
