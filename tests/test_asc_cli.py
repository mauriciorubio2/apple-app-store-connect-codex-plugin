import importlib.util
import json
import contextlib
import io
import plistlib
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

    def test_plan_versioning_reads_xcode_settings_and_iterations(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "Example.xcodeproj"
            project.mkdir()
            (project / "project.pbxproj").write_text(
                "MARKETING_VERSION = 1.2.3;\nCURRENT_PROJECT_VERSION = 40;\n",
                encoding="utf-8",
            )
            result = cli.plan_versioning(
                root,
                release_level="patch",
                iteration_count=3,
                use_git=False,
            )
        self.assertEqual(result["recommendation"]["versionString"], "1.2.4")
        self.assertEqual(result["recommendation"]["buildNumber"], "43")

    def test_apply_versioning_updates_project_and_config(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "Example.xcodeproj"
            project.mkdir()
            (project / "project.pbxproj").write_text(
                "MARKETING_VERSION = 1.2.3;\nCURRENT_PROJECT_VERSION = 40;\n",
                encoding="utf-8",
            )
            plist = root / "Info.plist"
            with plist.open("wb") as file:
                plistlib.dump(
                    {"CFBundleShortVersionString": "1.2.3", "CFBundleVersion": "40"},
                    file,
                    fmt=plistlib.FMT_XML,
                )
            config = root / "submission.json"
            config.write_text("{}", encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "project_dir": str(root),
                    "release_level": "minor",
                    "iteration_count": 2,
                    "current_version": None,
                    "current_build": None,
                    "no_git": True,
                    "config": str(config),
                    "force_plist": False,
                    "yes": True,
                },
            )()
            result = cli.apply_versioning(args)
            updated_config = json.loads(config.read_text())
            updated_plist = plistlib.loads(plist.read_bytes())
        self.assertFalse(result["dryRun"])
        self.assertEqual(updated_config["version"]["versionString"], "1.3.0")
        self.assertEqual(updated_config["build"]["buildNumber"], "42")
        self.assertEqual(updated_plist["CFBundleShortVersionString"], "1.3.0")
        self.assertEqual(updated_plist["CFBundleVersion"], "42")

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
