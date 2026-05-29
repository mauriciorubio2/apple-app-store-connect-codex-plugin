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

    def test_subscription_description_requires_terms_link(self):
        cli = load_cli()
        config = {
            "app": {"platform": "IOS"},
            "appInfoLocalizations": [
                {"locale": "en-US", "name": "Example Product", "privacyPolicyUrl": "https://example.com/privacy"}
            ],
            "versionLocalizations": [
                {
                    "locale": "en-US",
                    "description": "Example Product has a Pro subscription.",
                    "keywords": "planner,focus",
                    "supportUrl": "https://example.com/support",
                }
            ],
            "subscriptions": [{"reviewScreenshot": "paywall.png"}],
        }
        result = cli.validate_submission_config(config)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("Terms of Use" in issue["message"] for issue in result["issues"] if issue["severity"] == "error")
        )

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

    def test_credential_setup_imports_key_and_writes_env_file(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "AuthKey_TEST123.p8"
            source.write_text("fake private key", encoding="utf-8")
            key_dir = root / "private_keys"
            env_file = root / "credentials.env"
            args = type(
                "Args",
                (),
                {
                    "key_id": None,
                    "issuer_id": "00000000-0000-0000-0000-000000000000",
                    "key_type": "team",
                    "key_path": None,
                    "key_dir": str(key_dir),
                    "import_key": str(source),
                    "write_env_file": str(env_file),
                    "verify": False,
                },
            )()
            result = cli.credential_setup(args)
            imported = key_dir / "AuthKey_TEST123.p8"
            self.assertTrue(result["ok"])
            self.assertTrue(imported.exists())
            self.assertEqual(imported.stat().st_mode & 0o777, 0o600)
            self.assertIn("source ", result["shell"]["sourceCommand"])
            self.assertIn("ASC_KEY_ID='TEST123'", env_file.read_text())

    def test_doctor_fix_does_not_require_credentials_to_print_guidance(self):
        cli = load_cli()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli.main(["doctor", "--fix", "--key-id", "ABC123", "--key-path", "/tmp/AuthKey_ABC123.p8"])
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertIn("ASC_ISSUER_ID", payload["missing"])
        self.assertTrue(any("ASC_KEY_ID" in line for line in payload["shell"]["exports"]))

    def test_free_download_plan_reads_app_id_from_config(self):
        cli = load_cli()
        config = {"app": {"id": "1234567890"}}
        with tempfile.NamedTemporaryFile("w", suffix=".json") as file:
            json.dump(config, file)
            file.flush()
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = cli.main(["configure-free-download", "--config", file.name])
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["dryRun"])
        self.assertEqual(payload["appId"], "1234567890")
        self.assertEqual(payload["target"]["customerPrice"], "0.00")
        self.assertEqual(payload["target"]["availability"], "all App Store territories")

    def test_free_price_and_availability_bodies_use_json_api_relationships(self):
        cli = load_cli()
        price_body = cli.build_free_app_price_schedule_body("123", "USA", "free-point")
        availability_body = cli.build_all_territory_availability_body("123", ["USA", "AUS"])
        self.assertEqual(
            price_body["data"]["relationships"]["manualPrices"]["data"][0],
            {"type": "appPrices", "id": "${free-price-0}"},
        )
        self.assertEqual(
            price_body["included"][0]["relationships"]["appPricePoint"]["data"]["id"],
            "free-point",
        )
        self.assertTrue(availability_body["data"]["attributes"]["availableInNewTerritories"])
        self.assertEqual(len(availability_body["included"]), 2)
        self.assertTrue(all(item["attributes"]["available"] for item in availability_body["included"]))


if __name__ == "__main__":
    unittest.main()
