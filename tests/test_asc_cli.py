import importlib.util
import json
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins" / "apple-app-store-connect" / "scripts"
ASC_CLI = SCRIPTS / "asc_cli.py"


def load_cli():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("asc_cli", ASC_CLI)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["asc_cli"] = module
    spec.loader.exec_module(module)
    return module


class AscCliValidationTests(unittest.TestCase):
    def test_template_validates_with_expected_warnings_only(self):
        cli = load_cli()
        config = json.loads((ROOT / "plugins/apple-app-store-connect/assets/submission-template.json").read_text())
        result = cli.validate_submission_config(config)
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["warningCount"], 0)

    def test_keyword_length_error(self):
        cli = load_cli()
        config = {
            "app": {"platform": "IOS"},
            "appInfoLocalizations": [{"locale": "en-US", "name": "A", "privacyPolicyUrl": ""}],
            "versionLocalizations": [
                {
                    "locale": "en-US",
                    "keywords": "x" * 101,
                    "supportUrl": "",
                    "description": "A useful app.",
                }
            ],
        }
        result = cli.validate_submission_config(config)
        fields = {issue["field"] for issue in result["issues"]}
        self.assertFalse(result["ok"])
        self.assertIn("versionLocalizations[en-US].supportUrl", fields)
        self.assertIn("appInfoLocalizations[en-US].name", fields)
        self.assertTrue(any(issue["field"] == "keywords" for issue in result["issues"]))

    def test_plan_does_not_require_credentials(self):
        cli = load_cli()
        config = {
            "appInfoLocalizations": [{"locale": "en-US", "name": "Example Product"}],
            "version": {"versionString": "1.0.0"},
        }
        plan = cli.plan_submission(config)
        self.assertEqual(len(plan["actions"]), 2)

    def test_main_plan_reads_config(self):
        cli = load_cli()
        config = {"version": {"versionString": "1.0.0"}}
        with tempfile.NamedTemporaryFile("w", suffix=".json") as file:
            json.dump(config, file)
            file.flush()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["plan", "--config", file.name]), 0)


if __name__ == "__main__":
    unittest.main()
