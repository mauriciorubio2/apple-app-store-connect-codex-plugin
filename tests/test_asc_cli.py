import importlib.util
import json
import contextlib
import io
import os
import plistlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


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


class RecordingClient:
    def __init__(self):
        self.patch_calls = []
        self.post_calls = []

    def patch(self, path, body):
        self.patch_calls.append((path, body))
        return {"data": {"id": body.get("data", {}).get("id", "patched-id")}}

    def post(self, path, body):
        self.post_calls.append((path, body))
        return {"data": {"id": "posted-id"}}


class SubscriptionStatusClient:
    def __init__(self, subscription_state="APPROVED", localization_state="APPROVED"):
        self.subscription_state = subscription_state
        self.localization_state = localization_state

    def get(self, path, query=None):
        if path == "/v1/subscriptions/sub-weekly":
            return {
                "data": {
                    "id": "sub-weekly",
                    "type": "subscriptions",
                    "attributes": {
                        "productId": "com.example.product.pro.weekly",
                        "name": "Example Pro Weekly",
                        "state": self.subscription_state,
                        "subscriptionPeriod": "ONE_WEEK",
                    },
                }
            }
        if path == "/v1/subscriptions/sub-weekly/subscriptionLocalizations":
            return {
                "data": [
                    {
                        "id": "loc-en-us",
                        "type": "subscriptionLocalizations",
                        "attributes": {
                            "locale": "en-US",
                            "name": "Example Pro Weekly",
                            "description": "Premium features for Example.",
                            "state": self.localization_state,
                        },
                    }
                ]
            }
        raise AssertionError(f"Unexpected path: {path}")


class SelectedBuildClient:
    def __init__(self, *, selected_build="42", processing_state="VALID", uses_non_exempt_encryption=False):
        self.selected_build = selected_build
        self.processing_state = processing_state
        self.uses_non_exempt_encryption = uses_non_exempt_encryption

    def get(self, path, query=None):
        if path == "/v1/apps/1234567890/appStoreVersions":
            return {
                "data": [
                    {
                        "id": "version-1",
                        "type": "appStoreVersions",
                        "attributes": {"versionString": "1.0.0", "platform": "IOS"},
                        "relationships": {"build": {"data": {"id": "build-1", "type": "builds"}}},
                    }
                ],
                "included": [
                    {
                        "id": "build-1",
                        "type": "builds",
                        "attributes": {
                            "version": self.selected_build,
                            "processingState": self.processing_state,
                            "uploadedDate": "2026-06-06T00:00:00-07:00",
                            "usesNonExemptEncryption": self.uses_non_exempt_encryption,
                        },
                    }
                ],
            }
        if path == "/v1/builds/build-1":
            return {
                "data": {
                    "id": "build-1",
                    "type": "builds",
                    "attributes": {
                        "version": self.selected_build,
                        "processingState": self.processing_state,
                        "uploadedDate": "2026-06-06T00:00:00-07:00",
                        "usesNonExemptEncryption": self.uses_non_exempt_encryption,
                    },
                }
            }
        raise AssertionError(f"Unexpected path: {path}")


class BuildComplianceClient:
    def __init__(self, uses_non_exempt_encryption=None):
        self.uses_non_exempt_encryption = uses_non_exempt_encryption
        self.patch_calls = []

    def get(self, path, query=None):
        if path == "/v1/builds/build-1":
            attrs = {
                "version": "42",
                "processingState": "VALID",
                "uploadedDate": "2026-06-06T00:00:00-07:00",
            }
            if self.uses_non_exempt_encryption is not None:
                attrs["usesNonExemptEncryption"] = self.uses_non_exempt_encryption
            return {"data": {"id": "build-1", "type": "builds", "attributes": attrs}}
        raise AssertionError(f"Unexpected path: {path}")

    def patch(self, path, body):
        self.patch_calls.append((path, body))
        self.uses_non_exempt_encryption = body["data"]["attributes"]["usesNonExemptEncryption"]
        return self.get(path)


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

    def test_missing_whats_new_warns_for_version_history(self):
        cli = load_cli()
        config = {
            "app": {"platform": "IOS"},
            "appInfoLocalizations": [
                {
                    "locale": "en-US",
                    "name": "Example Product",
                    "privacyPolicyUrl": "https://example.com/privacy",
                }
            ],
            "versionLocalizations": [
                {
                    "locale": "en-US",
                    "description": "A useful app with clear user value.",
                    "keywords": "planner,focus",
                    "supportUrl": "https://example.com/support",
                }
            ],
        }
        result = cli.validate_submission_config(config)
        self.assertTrue(result["ok"])
        self.assertTrue(
            any(
                issue["field"] == "versionLocalizations[en-US].whatsNew"
                and issue["severity"] == "warning"
                for issue in result["issues"]
            )
        )

    def test_missing_whats_new_allowed_for_initial_platform_release(self):
        cli = load_cli()
        config = {
            "app": {"platform": "MAC_OS"},
            "version": {"versionString": "1.0.0", "initialPlatformRelease": True},
            "appInfoLocalizations": [
                {
                    "locale": "en-US",
                    "name": "Example Product",
                    "privacyPolicyUrl": "https://example.com/privacy",
                }
            ],
            "versionLocalizations": [
                {
                    "locale": "en-US",
                    "description": "A useful desktop app with clear user value.",
                    "keywords": "planner,focus",
                    "supportUrl": "https://example.com/support",
                }
            ],
        }
        result = cli.validate_submission_config(config)
        self.assertTrue(result["ok"])
        self.assertFalse(
            any(
                issue["field"] == "versionLocalizations[en-US].whatsNew"
                and issue["severity"] == "warning"
                for issue in result["issues"]
            )
        )

    def test_whats_new_formatter_splits_flat_version_history_into_bullets(self):
        cli = load_cli()
        flat = (
            "Confirmed 2026 squads are now loaded with 26-player team rosters, DOBs, clubs, positions, "
            "and refreshed original generated player portrait-card artwork. "
            "Added a Past tab for finished matches with scores, stats, replay links when available, "
            "and an Entertaining to Watch rating. "
            "App Store screenshots and metadata were refreshed for clearer conversion-focused messaging "
            "while keeping independent, generic soccer artwork."
        )
        expected = (
            "-Confirmed 2026 squads are now loaded with 26-player team rosters, DOBs, clubs, positions, "
            "and refreshed original generated player portrait-card artwork.\n"
            "-Added a Past tab for finished matches with scores, stats, replay links when available, "
            "and an Entertaining to Watch rating.\n"
            "-App Store screenshots and metadata were refreshed for clearer conversion-focused messaging "
            "while keeping independent, generic soccer artwork."
        )
        self.assertEqual(cli.format_whats_new_bullets(flat), expected)

    def test_whats_new_formatter_normalizes_existing_bullet_markers(self):
        cli = load_cli()
        source = "- Confirmed squads.\n• Added match history.\n* Refreshed screenshots."
        self.assertTrue(cli.whats_new_uses_bullet_lines(source))
        self.assertEqual(
            cli.format_whats_new_bullets(source),
            "-Confirmed squads.\n-Added match history.\n-Refreshed screenshots.",
        )

    def test_flat_whats_new_warns_for_bullet_version_history_format(self):
        cli = load_cli()
        config = {
            "app": {"platform": "IOS"},
            "appInfoLocalizations": [
                {
                    "locale": "en-US",
                    "name": "Example Product",
                    "privacyPolicyUrl": "https://example.com/privacy",
                }
            ],
            "versionLocalizations": [
                {
                    "locale": "en-US",
                    "description": "A useful app with clear user value.",
                    "keywords": "planner,focus",
                    "supportUrl": "https://example.com/support",
                    "whatsNew": "Added smarter planning. Refreshed screenshots.",
                }
            ],
        }
        result = cli.validate_submission_config(config)
        self.assertTrue(result["ok"])
        self.assertTrue(
            any(
                issue["field"] == "versionLocalizations[en-US].whatsNew"
                and issue["severity"] == "warning"
                and "hyphen-prefixed bullet lines" in issue["message"]
                for issue in result["issues"]
            )
        )

    def test_apply_submission_sends_bulleted_whats_new(self):
        cli = load_cli()
        client = RecordingClient()
        config = {
            "versionLocalizations": [
                {
                    "id": "loc-1",
                    "locale": "en-US",
                    "supportUrl": "https://example.com/support",
                    "whatsNew": "Added smarter planning. Refreshed screenshots.",
                }
            ]
        }
        result = cli.apply_submission(config, client, yes=True)
        self.assertFalse(result["dryRun"])
        self.assertEqual(len(client.patch_calls), 1)
        _, body = client.patch_calls[0]
        self.assertEqual(
            body["data"]["attributes"]["whatsNew"],
            "-Added smarter planning.\n-Refreshed screenshots.",
        )

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

    def test_subscription_description_requires_labeled_terms_url(self):
        cli = load_cli()
        config = {
            "app": {"platform": "IOS"},
            "appInfoLocalizations": [
                {"locale": "en-US", "name": "Example Product", "privacyPolicyUrl": "https://example.com/privacy"}
            ],
            "versionLocalizations": [
                {
                    "locale": "en-US",
                    "description": "SUBSCRIPTION INFORMATION:\nPro renews automatically. You can cancel 24 hours before renewal. Terms apply.\nPrivacy Policy: https://example.com/privacy",
                    "keywords": "planner,focus",
                    "supportUrl": "https://example.com/support",
                }
            ],
            "subscriptions": [{"reviewScreenshot": "paywall.png"}],
        }
        result = cli.validate_submission_config(config)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("Terms of Use or EULA URL" in issue["message"] for issue in result["issues"] if issue["severity"] == "error")
        )

    def test_first_time_ready_to_submit_subscriptions_require_ui_selection(self):
        cli = load_cli()
        config = {
            "version": {"versionString": "1.0.0", "buildId": "build-5"},
            "subscriptions": {
                "products": [
                    {
                        "productId": "com.example.product.pro.weekly",
                        "status": "READY_TO_SUBMIT",
                    }
                ],
                "firstTimeSubmission": {
                    "status": "ui_selection_required",
                },
            },
        }
        result = cli.validate_submission_config(config)
        fields = {issue["field"] for issue in result["issues"]}
        self.assertFalse(result["ok"])
        self.assertIn("firstTimeSubscriptionSubmission", fields)

    def test_first_time_ready_to_submit_subscriptions_require_selected_build(self):
        cli = load_cli()
        config = {
            "version": {"versionString": "1.0.0"},
            "subscriptions": [
                {
                    "productId": "com.example.product.pro.weekly",
                    "status": "READY_TO_SUBMIT",
                    "reviewScreenshot": "screenshots/review/pro-paywall.png",
                    "paidFeatureScreenshot": True,
                }
            ],
        }
        result = cli.validate_submission_config(config)
        fields = {issue["field"] for issue in result["issues"]}
        self.assertFalse(result["ok"])
        self.assertIn("version.buildId", fields)
        self.assertIn("firstTimeSubscriptionSubmission", fields)

    def test_first_time_subscription_ui_confirmation_allows_ready_state(self):
        cli = load_cli()
        config = {
            "version": {"versionString": "1.0.0", "buildId": "build-5"},
            "subscriptions": {
                "products": [
                    {
                        "productId": "com.example.product.pro.weekly",
                        "status": "READY_TO_SUBMIT",
                    }
                ],
                "firstTimeSubmission": {
                    "status": "selected_with_app_version",
                    "selectedInAppStoreConnect": True,
                },
            },
        }
        result = cli.validate_submission_config(config)
        self.assertTrue(result["ok"])
        self.assertFalse(any(issue["field"] == "firstTimeSubscriptionSubmission" for issue in result["issues"]))

    def test_subscription_review_screenshots_must_be_plan_specific(self):
        cli = load_cli()
        config = {
            "subscriptions": {
                "reviewScreenshot": {
                    "allowSharedReviewScreenshot": False,
                    "products": [
                        {
                            "productId": "com.example.product.pro.weekly",
                            "subscriptionId": "sub-weekly",
                            "expectedSelectedPlan": "weekly",
                            "sourceFileChecksum": "same-checksum",
                        },
                        {
                            "productId": "com.example.product.pro.monthly",
                            "subscriptionId": "sub-monthly",
                            "expectedSelectedPlan": "monthly",
                            "sourceFileChecksum": "same-checksum",
                        },
                    ],
                }
            }
        }
        result = cli.validate_submission_config(config)
        fields = {issue["field"] for issue in result["issues"]}
        self.assertFalse(result["ok"])
        self.assertIn("subscriptions.reviewScreenshot.products", fields)

    def test_subscription_review_screenshots_can_be_shared_when_intentional(self):
        cli = load_cli()
        entries = [
            {"expectedSelectedPlan": "weekly", "sourceFileChecksum": "same-checksum"},
            {"expectedSelectedPlan": "monthly", "sourceFileChecksum": "same-checksum"},
        ]
        self.assertEqual(cli.subscription_review_screenshot_duplicate_issues(entries, allow_shared=True), [])

    def test_subscription_review_screenshot_black_pixel_check(self):
        cli = load_cli()
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "black.png"
            Image.new("RGB", (640, 920), "black").save(path)
            issues = []
            cli.add_subscription_review_screenshot_pixel_issues(
                issues,
                "subscriptions.reviewScreenshot.products[0].source",
                cli.local_screenshot_pixel_summary(path),
            )
        self.assertTrue(any(issue["severity"] == "error" for issue in issues))

    def test_macos_subscription_review_screenshot_rejects_phone_dimensions(self):
        cli = load_cli()
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "phone.png"
            image = Image.frombytes("RGB", (640, 920), os.urandom(640 * 920 * 3))
            image.save(path)
            config = {
                "app": {"platform": "MAC_OS"},
                "subscriptionAvailability": {"allAppStoreTerritories": True},
                "subscriptions": [
                    {
                        "id": "sub-weekly",
                        "productId": "com.example.pro.weekly",
                        "period": "ONE_WEEK",
                        "reviewScreenshot": {
                            "source": str(path),
                            "expectedSelectedPlan": "weekly",
                        },
                    }
                ],
            }
            result = cli.validate_submission_config(config)
        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["field"].endswith(".dimensions") for issue in result["issues"]))

    def test_macos_subscription_review_screenshot_accepts_desktop_dimensions(self):
        cli = load_cli()
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "desktop.png"
            image = Image.frombytes("RGB", (1200, 800), os.urandom(1200 * 800 * 3))
            image.save(path)
            config = {
                "app": {"platform": "MAC_OS"},
                "subscriptionAvailability": {"allAppStoreTerritories": True},
                "subscriptions": [
                    {
                        "id": "sub-weekly",
                        "productId": "com.example.pro.weekly",
                        "period": "ONE_WEEK",
                        "reviewScreenshot": {
                            "source": str(path),
                            "expectedSelectedPlan": "weekly",
                        },
                    }
                ],
            }
            result = cli.validate_submission_config(config)
        self.assertTrue(result["ok"])
        self.assertFalse(any(issue["field"].endswith(".dimensions") for issue in result["issues"]))

    def test_verify_subscription_status_blocks_rejected_localization(self):
        cli = load_cli()
        config = {
            "subscriptions": [
                {
                    "id": "sub-weekly",
                    "productId": "com.example.product.pro.weekly",
                    "period": "ONE_WEEK",
                }
            ]
        }
        result = cli.verify_subscription_status(
            config,
            SubscriptionStatusClient(
                subscription_state="DEVELOPER_ACTION_NEEDED",
                localization_state="REJECTED",
            ),
        )
        fields = {issue["field"] for issue in result["issues"]}
        self.assertFalse(result["ok"])
        self.assertIn("subscriptions[0].state", fields)
        self.assertIn("subscriptions[0].subscriptionLocalizations[0].state", fields)

    def test_verify_subscription_status_warns_ready_to_submit(self):
        cli = load_cli()
        config = {
            "subscriptions": [
                {
                    "id": "sub-weekly",
                    "productId": "com.example.product.pro.weekly",
                    "period": "ONE_WEEK",
                }
            ]
        }
        result = cli.verify_subscription_status(
            config,
            SubscriptionStatusClient(
                subscription_state="READY_TO_SUBMIT",
                localization_state="READY_TO_SUBMIT",
            ),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["warningCount"], 2)

    def test_verify_build_assets_accepts_ios_archive_with_assets_car(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Example.xcarchive" / "Products" / "Applications" / "Example.app"
            app.mkdir(parents=True)
            with (app / "Info.plist").open("wb") as file:
                plistlib.dump(
                    {
                        "CFBundleIdentifier": "com.example.product",
                        "CFBundleShortVersionString": "1.0.0",
                        "CFBundleVersion": "42",
                        "CFBundleSupportedPlatforms": ["iPhoneOS"],
                    },
                    file,
                )
            (app / "Assets.car").write_bytes(b"compiled assets")
            result = cli.verify_build_assets(
                root / "Example.xcarchive",
                expect_bundle_id="com.example.product",
                expect_platform="iPhoneOS",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["appCount"], 1)
        self.assertTrue(result["apps"][0]["assetsCarPresent"])

    def test_verify_build_assets_accepts_macos_archive_bundle_layout(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Example.xcarchive" / "Products" / "Applications" / "Example.app"
            resources = app / "Contents" / "Resources"
            resources.mkdir(parents=True)
            with (app / "Contents" / "Info.plist").open("wb") as file:
                plistlib.dump(
                    {
                        "CFBundleIdentifier": "com.example.product",
                        "CFBundleShortVersionString": "1.0.0",
                        "CFBundleVersion": "42",
                        "CFBundleSupportedPlatforms": ["MacOSX"],
                        "LSMinimumSystemVersion": "14.0",
                        "NSHealthUpdateUsageDescription": "Save activity.",
                    },
                    file,
                )
            (resources / "Assets.car").write_bytes(b"compiled assets")
            result = cli.verify_build_assets(
                root / "Example.xcarchive",
                expect_bundle_id="com.example.product",
                expect_platform="MacOSX",
                required_purpose_strings=["NSHealthUpdateUsageDescription"],
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["apps"][0]["bundleShortVersion"], "1.0.0")
        self.assertEqual(result["apps"][0]["purposeStrings"]["NSHealthUpdateUsageDescription"], "Save activity.")
        self.assertEqual(result["apps"][0]["minimumOSVersion"], "14.0")
        self.assertTrue(result["apps"][0]["infoPlistPath"].endswith("Contents/Info.plist"))
        self.assertTrue(result["apps"][0]["assetsCarPath"].endswith("Contents/Resources/Assets.car"))

    def test_verify_build_assets_accepts_macos_pkg_with_assets_car(self):
        cli = load_cli()

        def fake_expand(command, capture_output=False, text=False):
            expanded = Path(command[-1])
            app = expanded / "Payload" / "Example.app"
            resources = app / "Contents" / "Resources"
            resources.mkdir(parents=True)
            with (app / "Contents" / "Info.plist").open("wb") as file:
                plistlib.dump(
                    {
                        "CFBundleIdentifier": "com.example.product",
                        "CFBundleShortVersionString": "1.0.0",
                        "CFBundleVersion": "42",
                        "CFBundleSupportedPlatforms": ["MacOSX"],
                        "LSMinimumSystemVersion": "14.0",
                        "NSHealthUpdateUsageDescription": "Save activity.",
                    },
                    file,
                )
            (resources / "Assets.car").write_bytes(b"compiled assets")
            return cli.subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "Example.pkg"
            pkg.write_bytes(b"flat package")
            with mock.patch.object(cli.shutil, "which", return_value="/usr/sbin/pkgutil"):
                with mock.patch.object(cli.subprocess, "run", side_effect=fake_expand):
                    result = cli.verify_build_assets(
                        pkg,
                        expect_bundle_id="com.example.product",
                        expect_platform="MAC_OS",
                        required_purpose_strings=["NSHealthUpdateUsageDescription"],
                    )
        self.assertTrue(result["ok"])
        self.assertEqual(result["expectPlatform"], "MacOSX")
        self.assertTrue(result["apps"][0]["assetsCarPresent"])
        self.assertEqual(result["apps"][0]["purposeStrings"]["NSHealthUpdateUsageDescription"], "Save activity.")

    def test_verify_build_assets_rejects_macos_pkg_missing_assets_car(self):
        cli = load_cli()

        def fake_expand(command, capture_output=False, text=False):
            expanded = Path(command[-1])
            app = expanded / "Payload" / "Example.app"
            (app / "Contents" / "Resources").mkdir(parents=True)
            with (app / "Contents" / "Info.plist").open("wb") as file:
                plistlib.dump(
                    {
                        "CFBundleIdentifier": "com.example.product",
                        "CFBundleShortVersionString": "1.0.0",
                        "CFBundleVersion": "42",
                        "CFBundleSupportedPlatforms": ["MacOSX"],
                    },
                    file,
                )
            return cli.subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "Example.pkg"
            pkg.write_bytes(b"flat package")
            with mock.patch.object(cli.shutil, "which", return_value="/usr/sbin/pkgutil"):
                with mock.patch.object(cli.subprocess, "run", side_effect=fake_expand):
                    result = cli.verify_build_assets(
                        pkg,
                        expect_bundle_id="com.example.product",
                        expect_platform="MacOS",
                    )
        self.assertFalse(result["ok"])
        self.assertEqual(result["expectPlatform"], "MacOSX")
        self.assertIn("Assets.car", result["issues"][0]["field"])
    def test_verify_build_assets_rejects_ios_ipa_missing_assets_car(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ipa = root / "Example.ipa"
            with zipfile.ZipFile(ipa, "w") as archive:
                archive.writestr(
                    "Payload/Example.app/Info.plist",
                    plistlib.dumps(
                        {
                            "CFBundleIdentifier": "com.example.product",
                            "CFBundleShortVersionString": "1.0.0",
                            "CFBundleVersion": "42",
                            "CFBundleSupportedPlatforms": ["iPhoneOS"],
                        }
                    ),
                )
            result = cli.verify_build_assets(
                ipa,
                expect_bundle_id="com.example.product",
                expect_platform="iPhoneOS",
            )
        self.assertFalse(result["ok"])
        self.assertIn("Assets.car", result["issues"][0]["field"])

    def test_verify_build_assets_rejects_health_share_without_update_purpose_string(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Example.xcarchive" / "Products" / "Applications" / "Example.app"
            app.mkdir(parents=True)
            with (app / "Info.plist").open("wb") as file:
                plistlib.dump(
                    {
                        "CFBundleIdentifier": "com.example.product",
                        "CFBundleShortVersionString": "1.0.0",
                        "CFBundleVersion": "42",
                        "CFBundleSupportedPlatforms": ["iPhoneOS"],
                        "NSHealthShareUsageDescription": "Read steps.",
                    },
                    file,
                )
            (app / "Assets.car").write_bytes(b"compiled assets")
            result = cli.verify_build_assets(root / "Example.xcarchive")
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("NSHealthUpdateUsageDescription" in issue["field"] for issue in result["issues"])
        )

    def test_verify_build_assets_accepts_required_health_update_purpose_string(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Example.xcarchive" / "Products" / "Applications" / "Example.app"
            app.mkdir(parents=True)
            with (app / "Info.plist").open("wb") as file:
                plistlib.dump(
                    {
                        "CFBundleIdentifier": "com.example.product",
                        "CFBundleShortVersionString": "1.0.0",
                        "CFBundleVersion": "42",
                        "CFBundleSupportedPlatforms": ["iPhoneOS"],
                        "NSHealthShareUsageDescription": "Read steps.",
                        "NSHealthUpdateUsageDescription": "Save activity.",
                    },
                    file,
                )
            (app / "Assets.car").write_bytes(b"compiled assets")
            result = cli.verify_build_assets(
                root / "Example.xcarchive",
                required_purpose_strings=["NSHealthUpdateUsageDescription"],
            )
        self.assertTrue(result["ok"])
        self.assertEqual(
            result["apps"][0]["purposeStrings"]["NSHealthUpdateUsageDescription"],
            "Save activity.",
        )

    def test_verify_selected_build_accepts_valid_selected_artifact_build(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Example.xcarchive" / "Products" / "Applications" / "Example.app"
            app.mkdir(parents=True)
            with (app / "Info.plist").open("wb") as file:
                plistlib.dump(
                    {
                        "CFBundleIdentifier": "com.example.product",
                        "CFBundleShortVersionString": "1.0.0",
                        "CFBundleVersion": "42",
                        "CFBundleSupportedPlatforms": ["iPhoneOS"],
                    },
                    file,
                )
            (app / "Assets.car").write_bytes(b"compiled assets")
            args = type(
                "Args",
                (),
                {
                    "app_id": "1234567890",
                    "platform": "IOS",
                    "version_string": None,
                    "build_number": None,
                    "artifact": str(root / "Example.xcarchive"),
                    "expect_bundle_id": "com.example.product",
                    "expect_platform": "iPhoneOS",
                },
            )()
            result = cli.verify_selected_build(args, SelectedBuildClient())
        self.assertTrue(result["ok"])
        self.assertEqual(result["versionString"], "1.0.0")
        self.assertEqual(result["selectedBuildNumber"], "42")
        self.assertTrue(result["encryptionCompliance"]["ok"])

    def test_verify_selected_build_rejects_stale_selected_build(self):
        cli = load_cli()
        args = type(
            "Args",
            (),
            {
                "app_id": "1234567890",
                "platform": "IOS",
                "version_string": "1.0.0",
                "build_number": "43",
                "artifact": None,
                "expect_bundle_id": None,
                "expect_platform": None,
            },
        )()
        result = cli.verify_selected_build(args, SelectedBuildClient(selected_build="42"))
        self.assertFalse(result["ok"])
        self.assertIn("build.version", {issue["field"] for issue in result["issues"]})

    def test_cross_platform_version_consistency_rejects_mismatch(self):
        cli = load_cli()
        config = {
            "app": {"platform": "IOS"},
            "version": {"versionString": "1.0.1"},
            "build": {"buildNumber": "12"},
            "crossPlatformRelease": {
                "versionConsistency": {
                    "requireSameVersionString": True,
                    "requireSameBuildNumber": True,
                    "platforms": [
                        {"platform": "IOS", "versionString": "1.0.1", "buildNumber": "12"},
                        {"platform": "MAC_OS", "versionString": "1.0.2", "buildNumber": "13"},
                    ],
                }
            },
        }
        result = cli.validate_submission_config(config)
        fields = {issue["field"] for issue in result["issues"] if issue["severity"] == "error"}
        self.assertFalse(result["ok"])
        self.assertIn("crossPlatformRelease.versionConsistency.platforms.versionString", fields)
        self.assertIn("crossPlatformRelease.versionConsistency.platforms.buildNumber", fields)

    def test_cross_platform_version_consistency_accepts_matching_platforms(self):
        cli = load_cli()
        config = {
            "app": {"platform": "IOS"},
            "version": {"versionString": "1.0.1"},
            "build": {"buildNumber": "12"},
            "crossPlatformRelease": {
                "versionConsistency": {
                    "requireSameVersionString": True,
                    "requireSameBuildNumber": True,
                    "platforms": [
                        {"platform": "IOS", "versionString": "1.0.1", "buildNumber": "12"},
                        {"platform": "MAC_OS", "versionString": "1.0.1", "buildNumber": "12"},
                    ],
                }
            },
        }
        result = cli.validate_submission_config(config)
        self.assertTrue(result["ok"])
        plan = cli.plan_submission(config)
        self.assertTrue(
            any(action["resource"] == "iOS/macOS App Store version consistency" for action in plan["actions"])
        )

    def test_cross_platform_description_consistency_rejects_mismatch(self):
        cli = load_cli()
        config = {
            "app": {"platform": "IOS", "primaryLocale": "en-US"},
            "crossPlatformRelease": {
                "applePlatforms": ["IOS", "MAC_OS"],
                "descriptionConsistency": {
                    "requireSameDescription": True,
                    "platforms": [
                        {"platform": "IOS", "locale": "en-US", "description": "Plan calm days."},
                        {"platform": "MAC_OS", "locale": "en-US", "description": "Track focused work."},
                    ],
                },
            },
        }
        result = cli.validate_submission_config(config)
        fields = {issue["field"] for issue in result["issues"] if issue["severity"] == "error"}
        self.assertFalse(result["ok"])
        self.assertIn("crossPlatformRelease.descriptionConsistency.platforms.description", fields)
        plan = cli.plan_submission(config)
        self.assertTrue(
            any(action["resource"] == "iOS/macOS App Store description consistency" for action in plan["actions"])
        )

    def test_cross_platform_screenshot_sync_blocks_stale_ui_screenshots(self):
        cli = load_cli()
        config = {
            "app": {"platform": "IOS"},
            "crossPlatformRelease": {
                "applePlatforms": ["IOS", "MAC_OS"],
                "screenshotSync": {
                    "uiChangedSinceLastSubmission": True,
                    "preserveScreenshotRules": True,
                    "platforms": [
                        {
                            "platform": "IOS",
                            "displayTypes": ["APP_IPHONE_67"],
                            "updatedFromLatestUi": True,
                            "uploadedToAppStoreConnect": True,
                        }
                    ],
                },
            },
            "screenshots": [
                {
                    "displayType": "APP_IPHONE_67",
                    "files": ["generated-screenshots/en-US/APP_IPHONE_67/01-plan.png"],
                }
            ],
        }
        result = cli.validate_submission_config(config)
        fields = {issue["field"] for issue in result["issues"] if issue["severity"] == "error"}
        self.assertFalse(result["ok"])
        self.assertIn("crossPlatformRelease.screenshotSync.platforms", fields)
        plan = cli.plan_submission(config)
        screenshot_action = next(
            action for action in plan["actions"] if action["resource"] == "iOS/macOS App Store screenshot freshness"
        )
        self.assertEqual(screenshot_action["action"], "UPLOAD_REQUIRED")

    def test_cross_platform_screenshot_sync_accepts_fresh_ios_and_macos(self):
        cli = load_cli()
        config = {
            "app": {"platform": "IOS", "primaryLocale": "en-US"},
            "crossPlatformRelease": {
                "applePlatforms": ["IOS", "MAC_OS"],
                "descriptionConsistency": {
                    "requireSameDescription": True,
                    "platforms": [
                        {"platform": "IOS", "locale": "en-US", "description": "Plan calm days."},
                        {"platform": "MAC_OS", "locale": "en-US", "description": "Plan calm days."},
                    ],
                },
                "screenshotSync": {
                    "uiChangedSinceLastSubmission": True,
                    "preserveScreenshotRules": True,
                    "platforms": [
                        {
                            "platform": "IOS",
                            "displayTypes": ["APP_IPHONE_67"],
                            "updatedFromLatestUi": True,
                            "uploadedToAppStoreConnect": True,
                        },
                        {
                            "platform": "MAC_OS",
                            "displayTypes": ["APP_DESKTOP"],
                            "updatedFromLatestUi": True,
                            "uploadedToAppStoreConnect": True,
                        },
                    ],
                },
            },
            "screenshots": [
                {
                    "displayType": "APP_IPHONE_67",
                    "files": ["generated-screenshots/en-US/APP_IPHONE_67/01-plan.png"],
                },
                {
                    "displayType": "APP_DESKTOP",
                    "files": ["generated-screenshots/en-US/APP_DESKTOP/01-plan.png"],
                },
            ],
        }
        result = cli.validate_submission_config(config)
        self.assertTrue(result["ok"])
        self.assertFalse(any(issue["severity"] == "error" for issue in result["issues"]))

    def test_verify_selected_build_rejects_missing_encryption_compliance(self):
        cli = load_cli()
        args = type(
            "Args",
            (),
            {
                "app_id": "1234567890",
                "platform": "IOS",
                "version_string": "1.0.0",
                "build_number": "42",
                "artifact": None,
                "expect_bundle_id": None,
                "expect_platform": None,
            },
        )()
        result = cli.verify_selected_build(args, SelectedBuildClient(uses_non_exempt_encryption=True))
        self.assertFalse(result["ok"])
        self.assertIn("build.usesNonExemptEncryption", {issue["field"] for issue in result["issues"]})

    def test_configure_build_compliance_sets_none_of_the_algorithms(self):
        cli = load_cli()
        client = BuildComplianceClient(uses_non_exempt_encryption=True)
        result = cli.configure_build_compliance("build-1", client, yes=True)
        self.assertEqual(result["action"], "PATCH")
        self.assertEqual(result["after"]["usesNonExemptEncryption"], False)
        self.assertEqual(client.patch_calls[0][0], "/v1/builds/build-1")
        self.assertFalse(client.patch_calls[0][1]["data"]["attributes"]["usesNonExemptEncryption"])

    def test_revenuecat_paywall_mapping_warns_when_products_missing(self):
        cli = load_cli()
        config = {
            "subscriptions": [
                {
                    "id": "sub-weekly",
                    "productId": "com.example.product.pro.weekly",
                    "reviewScreenshot": "screenshots/review/pro-paywall.png",
                    "paidFeatureScreenshot": True,
                }
            ],
            "revenueCatIntegration": {
                "enabled": True,
                "requiresAuthenticatedMcp": True,
                "projectId": "proj-example",
                "entitlementIdentifier": "pro",
                "offeringIdentifier": "default",
            },
        }
        result = cli.validate_submission_config(config)
        fields = {issue["field"] for issue in result["issues"]}
        self.assertIn("revenueCatIntegration.products", fields)
        self.assertIn("revenueCatIntegration.apps", fields)

    def test_ip_review_warns_when_independent_app_disclaimers_are_missing(self):
        cli = load_cli()
        config = {
            "app": {"platform": "IOS"},
            "appInfoLocalizations": [
                {"locale": "en-US", "name": "Example Product", "privacyPolicyUrl": "https://example.com/privacy"}
            ],
            "versionLocalizations": [
                {
                    "locale": "en-US",
                    "description": "A companion guide for a popular event.",
                    "keywords": "guide,event",
                    "supportUrl": "https://example.com/support",
                }
            ],
            "reviewDetails": {
                "contactFirstName": "Alex",
                "contactLastName": "Example",
                "contactPhone": "+15550100",
                "contactEmail": "review@example.com",
                "notes": "No account required.",
            },
            "ipReview": {
                "usesThirdPartyIP": True,
                "hasWrittenAuthorization": False,
                "isIndependentReferenceOrFanApp": True,
                "noAffiliationDisclaimerInDescription": False,
                "noAffiliationDisclaimerInReviewNotes": False,
                "checkedBinaryAndMetadataForOfficialMarks": False,
                "newBuildUploadedForBinaryAssetChanges": False,
            },
        }
        result = cli.validate_submission_config(config)
        fields = {issue["field"] for issue in result["issues"]}
        self.assertTrue(result["ok"])
        self.assertIn("ipReview.hasWrittenAuthorization", fields)
        self.assertIn("ipReview.noAffiliationDisclaimerInDescription", fields)
        self.assertIn("ipReview.noAffiliationDisclaimerInReviewNotes", fields)
        self.assertIn("ipReview.checkedBinaryAndMetadataForOfficialMarks", fields)
        self.assertIn("ipReview.newBuildUploadedForBinaryAssetChanges", fields)

    def test_plan_does_not_require_credentials(self):
        cli = load_cli()
        config = {
            "appInfoLocalizations": [{"locale": "en-US", "name": "Example Product"}],
            "version": {"versionString": "1.0.0"},
        }
        plan = cli.plan_submission(config)
        self.assertEqual(len(plan["actions"]), 2)

    def test_macos_upload_rejects_ipa_for_mac_platform(self):
        cli = load_cli()
        with tempfile.NamedTemporaryFile(suffix=".ipa") as file:
            args = type(
                "Args",
                (),
                {
                    "file": file.name,
                    "version_string": "1.0.0",
                    "build_number": "42",
                    "auto_version": False,
                    "project_dir": ".",
                    "release_level": "auto",
                    "iteration_count": None,
                    "current_version": None,
                    "current_build": None,
                    "no_git": True,
                    "yes": True,
                    "platform": "MAC_OS",
                    "app_id": "1234567890",
                    "wait": 0,
                },
            )()
            with self.assertRaisesRegex(cli.AppStoreConnectError, "MAC_OS uploads should use .pkg"):
                cli.upload_build_api(args, client=object())

    def test_macos_upload_dry_run_checks_pkg_assets(self):
        cli = load_cli()
        with tempfile.NamedTemporaryFile(suffix=".pkg") as file:
            args = type(
                "Args",
                (),
                {
                    "file": file.name,
                    "version_string": "1.0.0",
                    "build_number": "42",
                    "auto_version": False,
                    "project_dir": ".",
                    "release_level": "auto",
                    "iteration_count": None,
                    "current_version": None,
                    "current_build": None,
                    "no_git": True,
                    "yes": False,
                    "platform": "MAC_OS",
                    "app_id": "1234567890",
                    "wait": 0,
                    "expect_bundle_id": "com.example.product",
                    "expect_platform": None,
                    "skip_binary_asset_check": False,
                },
            )()
            check = {"ok": True, "appCount": 1, "issues": [], "apps": []}
            with mock.patch.object(cli, "verify_build_assets", return_value=check) as verify:
                result = cli.upload_build_api(args, client=None)
        self.assertEqual(result["binaryAssetCheck"], check)
        verify.assert_called_once()
        self.assertEqual(verify.call_args.kwargs["expect_platform"], "MacOSX")

    def test_cross_platform_subscription_plan_preserves_existing_prices_and_trials(self):
        cli = load_cli()
        products = [
            ("sub-weekly", "com.example.product.pro.weekly", "ONE_WEEK", "$rc_weekly"),
            ("sub-monthly", "com.example.product.pro.monthly", "ONE_MONTH", "$rc_monthly"),
            ("sub-yearly", "com.example.product.pro.yearly", "ONE_YEAR", "$rc_annual"),
        ]
        config = {
            "app": {"platform": "MAC_OS"},
            "build": {"packagePath": "build/App.pkg"},
            "crossPlatformRelease": {
                "enabled": True,
                "applePlatforms": ["IOS", "MAC_OS"],
                "distributionModel": "appleUniversalPurchase",
                "sharedAppleAppRecord": True,
                "sameBundleIdForUniversalPurchase": True,
                "sameSubscriptionGroupAndProductIds": True,
            },
            "revenueCatIntegration": {
                "enabled": True,
                "projectId": "proj-example",
                "entitlementIdentifier": "pro",
                "offeringIdentifier": "default",
                "apps": [
                    {
                        "platform": "IOS",
                        "store": "app_store",
                        "bundleId": "com.example.product",
                        "appId": "app-example",
                        "publicApiKey": "appl_public",
                    }
                ],
                "packages": [package for _, _, _, package in products],
                "requiresAuthenticatedMcp": True,
                "productsMirrorAppStoreConnectSubscriptions": True,
                "crossPlatform": {
                    "enabled": True,
                    "sameProject": True,
                    "sharedEntitlement": True,
                    "sharedOffering": True,
                    "packagesRepresentEquivalentProducts": True,
                    "universalPurchaseMacUsesApplePublicKey": True,
                },
            },
            "subscriptionPricing": {
                "appDownloadModel": "freeWithSubscription",
                "baseTerritory": "USA",
                "useSingleSubscriptionGroup": True,
                "creatorCanOverrideCadences": True,
                "products": [
                    {
                        "subscriptionId": subscription_id,
                        "productId": product_id,
                        "period": period,
                        "territory": "USA",
                        "pricePointId": "price-point",
                        "preserveCurrentPrice": True,
                    }
                    for subscription_id, product_id, period, _ in products
                ],
                "introductoryOffers": [
                    {
                        "subscriptionId": subscription_id,
                        "productId": product_id,
                        "territory": "USA",
                        "offerMode": "FREE_TRIAL",
                        "duration": "TWO_WEEKS",
                        "numberOfPeriods": 1,
                        "preserveCurrentIntroductoryOffer": True,
                    }
                    for subscription_id, product_id, _, _ in products
                ],
            },
            "onboarding": {
                "collectsPreferences": True,
                "paywallTiming": "afterFirstPersonalizedValue",
                "restorePurchasesVisible": True,
                "termsAndPrivacyVisibleOnPaywall": True,
            },
            "reviewPromptPolicy": {
                "usesStoreKitRequestReview": True,
                "minimumSessions": 3,
                "minimumDaysSinceInstall": 3,
                "localCooldownDays": 90,
                "positiveMomentTriggers": [{"event": "used_app", "afterSuccessfulUserOutcome": True}],
                "blockedContexts": ["launch", "paywall", "purchase"],
            },
        }
        growth_plan = cli.plan_growth_strategy(config)
        self.assertTrue(growth_plan["ok"])
        self.assertTrue(all(action["action"] == "NO_OP" for action in growth_plan["plannedPricingActions"]))
        self.assertTrue(all(action["action"] == "NO_OP" for action in growth_plan["plannedIntroOfferActions"]))
        release_plan = cli.plan_submission(config)
        subscription_action = next(
            action for action in release_plan["actions"] if action["resource"] == "subscriptionPrices/subscriptionIntroductoryOffers"
        )
        self.assertEqual(subscription_action["action"], "NO_OP")
        self.assertEqual(subscription_action["priceActionCount"], 0)
        self.assertEqual(subscription_action["introOfferActionCount"], 0)
        self.assertEqual(subscription_action["preservedPriceCount"], 3)
        self.assertEqual(subscription_action["preservedIntroOfferCount"], 3)

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

    def test_subscription_price_and_intro_offer_bodies_use_json_api_relationships(self):
        cli = load_cli()
        price_body = cli.build_subscription_price_body(
            "sub-123",
            "point-123",
            territory="USA",
            start_date="2026-07-01",
            preserve_current_price=True,
        )
        offer_body = cli.build_subscription_intro_offer_body(
            "sub-123",
            {
                "territory": "USA",
                "offerMode": "FREE_TRIAL",
                "duration": "ONE_WEEK",
                "numberOfPeriods": 1,
            },
        )
        self.assertEqual(price_body["data"]["type"], "subscriptionPrices")
        self.assertEqual(
            price_body["data"]["relationships"]["subscriptionPricePoint"]["data"]["id"],
            "point-123",
        )
        self.assertEqual(price_body["data"]["relationships"]["territory"]["data"]["id"], "USA")
        self.assertTrue(price_body["data"]["attributes"]["preserveCurrentPrice"])
        self.assertEqual(offer_body["data"]["type"], "subscriptionIntroductoryOffers")
        self.assertEqual(offer_body["data"]["attributes"]["offerMode"], "FREE_TRIAL")

    def test_subscription_availability_body_uses_available_territories_relationship(self):
        cli = load_cli()
        body = cli.build_subscription_availability_body("sub-123", ["USA", "AUS"], True)
        self.assertEqual(body["data"]["type"], "subscriptionAvailabilities")
        self.assertTrue(body["data"]["attributes"]["availableInNewTerritories"])
        self.assertEqual(body["data"]["relationships"]["subscription"]["data"]["id"], "sub-123")
        self.assertEqual(
            body["data"]["relationships"]["availableTerritories"]["data"],
            [{"type": "territories", "id": "USA"}, {"type": "territories", "id": "AUS"}],
        )

    def test_pricing_research_warns_when_stale(self):
        cli = load_cli()
        config = {
            "subscriptions": [{"id": "sub-123", "productId": "com.example.pro.monthly"}],
            "pricingResearch": {
                "lastReviewedOn": "2025-01-01",
                "reviewIntervalMonths": 6,
                "sources": [
                    "https://www.revenuecat.com/state-of-subscription-apps-2025/",
                    "https://developer.apple.com/app-store/subscriptions/",
                ],
            },
            "subscriptionPricing": {
                "useSingleSubscriptionGroup": True,
                "products": [
                    {
                        "subscriptionId": "sub-123",
                        "period": "ONE_MONTH",
                        "role": "primary",
                        "benchmarkCustomerPrice": "9.99",
                        "pricePointId": "point-123",
                    },
                    {
                        "subscriptionId": "sub-year",
                        "period": "ONE_YEAR",
                        "role": "bestValue",
                        "benchmarkCustomerPrice": "29.99",
                        "pricePointId": "point-year",
                    },
                ],
            },
        }
        issues = []
        cli.validate_subscription_pricing_strategy(config, issues)
        fields = {issue["field"] for issue in issues}
        self.assertIn("pricingResearch.lastReviewedOn", fields)

    def test_weekly_primary_plan_needs_cadence_reason(self):
        cli = load_cli()
        config = {
            "subscriptions": [{"id": "weekly-subscription-id", "productId": "com.example.pro.weekly"}],
            "pricingResearch": {
                "lastReviewedOn": "2026-06-01",
                "reviewIntervalMonths": 6,
                "sources": [
                    "https://www.revenuecat.com/state-of-subscription-apps-2025/",
                    "https://developer.apple.com/app-store/subscriptions/",
                ],
            },
            "subscriptionPricing": {
                "useSingleSubscriptionGroup": True,
                "products": [
                    {
                        "subscriptionId": "weekly-subscription-id",
                        "period": "ONE_WEEK",
                        "role": "primary",
                        "benchmarkCustomerPrice": "4.99",
                        "pricePointId": "point-week",
                    }
                ],
            },
        }
        issues = []
        cli.validate_subscription_pricing_strategy(config, issues)
        fields = {issue["field"] for issue in issues}
        self.assertIn("subscriptionPricing.products[0].role", fields)

    def test_missing_default_weekly_cadence_warns_without_override_reason(self):
        cli = load_cli()
        config = {
            "subscriptions": [{"id": "sub-month", "productId": "com.example.pro.monthly"}],
            "pricingResearch": {
                "lastReviewedOn": "2026-06-01",
                "reviewIntervalMonths": 6,
                "sources": [
                    "https://www.revenuecat.com/state-of-subscription-apps-2025/",
                    "https://developer.apple.com/app-store/subscriptions/",
                ],
            },
            "subscriptionPricing": {
                "useSingleSubscriptionGroup": True,
                "defaultCadences": ["ONE_WEEK", "ONE_MONTH", "ONE_YEAR"],
                "products": [
                    {
                        "subscriptionId": "sub-month",
                        "period": "ONE_MONTH",
                        "role": "primary",
                        "benchmarkCustomerPrice": "9.99",
                        "pricePointId": "point-month",
                    },
                    {
                        "subscriptionId": "sub-year",
                        "period": "ONE_YEAR",
                        "role": "bestValue",
                        "benchmarkCustomerPrice": "29.99",
                        "pricePointId": "point-year",
                    },
                ],
            },
        }
        issues = []
        cli.validate_subscription_pricing_strategy(config, issues)
        self.assertTrue(any("ONE_WEEK" in issue["message"] for issue in issues))

    def test_custom_cadence_reason_allows_omitting_weekly_default(self):
        cli = load_cli()
        config = {
            "subscriptions": [{"id": "sub-month", "productId": "com.example.pro.monthly"}],
            "pricingResearch": {
                "lastReviewedOn": "2026-06-01",
                "reviewIntervalMonths": 6,
                "sources": [
                    "https://www.revenuecat.com/state-of-subscription-apps-2025/",
                    "https://developer.apple.com/app-store/subscriptions/",
                ],
            },
            "subscriptionPricing": {
                "useSingleSubscriptionGroup": True,
                "defaultCadences": ["ONE_WEEK", "ONE_MONTH", "ONE_YEAR"],
                "customCadenceReason": "This professional app has no short-term use case, so weekly is intentionally omitted.",
                "products": [
                    {
                        "subscriptionId": "sub-month",
                        "period": "ONE_MONTH",
                        "role": "primary",
                        "benchmarkCustomerPrice": "9.99",
                        "pricePointId": "point-month",
                    },
                    {
                        "subscriptionId": "sub-year",
                        "period": "ONE_YEAR",
                        "role": "bestValue",
                        "benchmarkCustomerPrice": "29.99",
                        "pricePointId": "point-year",
                    },
                ],
            },
        }
        issues = []
        cli.validate_subscription_pricing_strategy(config, issues)
        self.assertFalse(any("ONE_WEEK" in issue["message"] for issue in issues))

    def test_annual_discount_below_threshold_warns(self):
        cli = load_cli()
        config = {
            "subscriptions": [{"id": "sub-123", "productId": "com.example.pro.monthly"}],
            "pricingResearch": {
                "lastReviewedOn": "2026-06-01",
                "reviewIntervalMonths": 6,
                "sources": [
                    "https://www.revenuecat.com/state-of-subscription-apps-2025/",
                    "https://developer.apple.com/app-store/subscriptions/",
                ],
            },
            "subscriptionPricing": {
                "useSingleSubscriptionGroup": True,
                "products": [
                    {
                        "subscriptionId": "sub-month",
                        "period": "ONE_MONTH",
                        "role": "primary",
                        "benchmarkCustomerPrice": "9.99",
                        "pricePointId": "point-month",
                    },
                    {
                        "subscriptionId": "sub-year",
                        "period": "ONE_YEAR",
                        "role": "bestValue",
                        "benchmarkCustomerPrice": "99.99",
                        "pricePointId": "point-year",
                    },
                ],
            },
        }
        issues = []
        cli.validate_subscription_pricing_strategy(config, issues)
        self.assertTrue(any("annual plan discount" in issue["message"] for issue in issues))

    def test_revenuecat_access_probe_flags_revoked_token(self):
        cli = load_cli()
        result = cli.revenuecat_access_probe(
            "Error calling list-projects: authorization_error access token has been revoked"
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "revoked_or_unauthorized")
        self.assertIn("reconnect", result["reauthentication"].lower())

    def test_revenuecat_access_probe_accepts_project_list(self):
        cli = load_cli()
        result = cli.revenuecat_access_probe([{"id": "proj123", "name": "Example"}])
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["visibleProjects"], 1)

    def test_revenuecat_access_probe_accepts_v2_items_list(self):
        cli = load_cli()
        result = cli.revenuecat_access_probe(
            {
                "object": "list",
                "items": [
                    {"object": "project", "id": "proj123", "name": "Example"},
                    {"object": "project", "id": "proj456", "name": "Another"},
                ],
                "next_page": None,
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["visibleProjects"], 2)

    def test_revenuecat_access_probe_accepts_codex_text_project_list(self):
        cli = load_cli()
        result = cli.revenuecat_access_probe(
            'object: list\nitems[2]{object,id,name}:\n  project,proj123,Example\n  project,proj456,Another\nnext_page: null'
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["visibleProjects"], 2)

    def test_preflight_access_prompts_for_reauthorization_when_blocked(self):
        cli = load_cli()
        result = cli.preflight_access(
            verify_apple=False,
            revenuecat_probe_payload="HTTP status: 403 authorization_error access token has been revoked",
        )
        services = {item["service"] for item in result["reauthorizationPrompts"]}
        self.assertFalse(result["ok"])
        self.assertIn("App Store Connect", services)
        self.assertIn("RevenueCat", services)

    def test_main_preflight_access_parses_revenuecat_probe_json(self):
        cli = load_cli()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli.main(
                [
                    "preflight-access",
                    "--skip-apple",
                    "--revenuecat-probe-json",
                    '[{"id":"proj123","name":"Example"}]',
                ]
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["revenueCat"]["ok"])
        self.assertFalse(payload["ok"])

    def test_growth_strategy_flags_bad_review_trigger(self):
        cli = load_cli()
        config = {
            "subscriptions": [{"id": "sub-123", "productId": "com.example.pro.monthly"}],
            "pricingAvailability": {"downloadPrice": "0.00"},
            "subscriptionPricing": {
                "useSingleSubscriptionGroup": True,
                "products": [
                    {
                        "subscriptionId": "sub-123",
                        "period": "ONE_MONTH",
                        "territory": "USA",
                        "pricePointId": "point-123",
                    }
                ],
            },
            "onboarding": {
                "collectsPreferences": True,
                "paywallTiming": "afterFirstPersonalizedValue",
                "restorePurchasesVisible": True,
                "termsAndPrivacyVisibleOnPaywall": True,
            },
            "reviewPromptPolicy": {
                "usesStoreKitRequestReview": True,
                "minimumDaysSinceInstall": 0,
                "minimumSessions": 1,
                "localCooldownDays": 30,
                "positiveMomentTriggers": [
                    {"event": "launch", "afterSuccessfulUserOutcome": False}
                ],
                "blockedContexts": ["launch"],
            },
        }
        result = cli.plan_growth_strategy(config)
        fields = {issue["field"] for issue in result["issues"]}
        self.assertFalse(result["ok"])
        self.assertIn("reviewPromptPolicy.positiveMomentTriggers[0]", fields)
        self.assertIn("reviewPromptPolicy.minimumSessions", fields)

    def test_growth_strategy_accepts_default_free_pro_access_model(self):
        cli = load_cli()
        config = json.loads(
            (ROOT / "plugins/apple-app-store-connect/assets/subscription-onboarding-review-template.json").read_text()
        )
        config["subscriptions"] = [
            {"id": "weekly-subscription-id", "productId": "com.example.app.pro.weekly"},
            {"id": "monthly-subscription-id", "productId": "com.example.app.pro.monthly"},
            {"id": "yearly-subscription-id", "productId": "com.example.app.pro.yearly"},
        ]
        config["pricingAvailability"] = {"downloadPrice": "0.00"}
        result = cli.plan_growth_strategy(config)
        fields = {issue["field"] for issue in result["issues"]}
        self.assertTrue(result["ok"])
        self.assertEqual(result["freeProAccessModel"]["targetFreeAccessPercent"], 75)
        self.assertEqual(result["freeProAccessModel"]["targetProAccessPercent"], 25)
        self.assertNotIn("freeProAccessModel.targetFreeAccessPercent", fields)

    def test_growth_strategy_warns_when_free_access_split_is_too_low(self):
        cli = load_cli()
        config = {
            "subscriptions": [{"id": "sub-123", "productId": "com.example.pro.monthly"}],
            "subscriptionPricing": {"useSingleSubscriptionGroup": True},
            "freeProAccessModel": {
                "targetFreeAccessPercent": 50,
                "freeTier": {"features": ["View dashboard", "Search content", "Save one item"]},
                "proTier": {"features": ["Everything else"], "lockedFeatureTypes": ["advanced alerts"]},
                "paywall": {"timing": "afterFirstPersonalizedValue", "triggers": ["user taps Pro feature"]},
            },
            "onboarding": {
                "collectsPreferences": True,
                "paywallTiming": "afterFirstPersonalizedValue",
                "restorePurchasesVisible": True,
                "termsAndPrivacyVisibleOnPaywall": True,
            },
            "reviewPromptPolicy": {
                "usesStoreKitRequestReview": True,
                "minimumDaysSinceInstall": 3,
                "minimumSessions": 3,
                "localCooldownDays": 120,
                "positiveMomentTriggers": [{"event": "completed_goal", "afterSuccessfulUserOutcome": True}],
                "blockedContexts": ["launch", "onboarding", "paywall", "error"],
            },
        }
        result = cli.plan_growth_strategy(config)
        fields = {issue["field"] for issue in result["issues"]}
        self.assertIn("freeProAccessModel.targetFreeAccessPercent", fields)

    def test_growth_strategy_allows_custom_free_pro_access_split_with_reason(self):
        cli = load_cli()
        config = {
            "subscriptions": [{"id": "sub-123", "productId": "com.example.pro.monthly"}],
            "subscriptionPricing": {"useSingleSubscriptionGroup": True},
            "freeProAccessModel": {
                "targetFreeAccessPercent": 55,
                "targetProAccessPercent": 45,
                "customAccessSplitReason": "The app is a professional dataset tool with licensed Pro-only datasets.",
                "freeTier": {"features": ["Browse sample data", "Search examples", "Save one project"]},
                "proTier": {"features": ["Licensed datasets", "Exports", "Team workflows"]},
                "paywall": {"timing": "afterFirstPersonalizedValue", "triggers": ["user taps licensed dataset"]},
            },
            "onboarding": {
                "collectsPreferences": True,
                "paywallTiming": "afterFirstPersonalizedValue",
                "restorePurchasesVisible": True,
                "termsAndPrivacyVisibleOnPaywall": True,
            },
            "reviewPromptPolicy": {
                "usesStoreKitRequestReview": True,
                "minimumDaysSinceInstall": 3,
                "minimumSessions": 3,
                "localCooldownDays": 120,
                "positiveMomentTriggers": [{"event": "completed_goal", "afterSuccessfulUserOutcome": True}],
                "blockedContexts": ["launch", "onboarding", "paywall", "error"],
            },
        }
        result = cli.plan_growth_strategy(config)
        fields = {issue["field"] for issue in result["issues"]}
        self.assertNotIn("freeProAccessModel.targetFreeAccessPercent", fields)
        self.assertTrue(result["freeProAccessModel"]["customAccessSplitReason"])

    def test_growth_strategy_warns_when_pro_locks_core_loop(self):
        cli = load_cli()
        config = {
            "subscriptions": [{"id": "sub-123", "productId": "com.example.pro.monthly"}],
            "subscriptionPricing": {"useSingleSubscriptionGroup": True},
            "freeProAccessModel": {
                "targetFreeAccessPercent": 75,
                "freeTier": {"features": ["Open the app", "See preview", "Create account"]},
                "proTier": {
                    "features": ["Browse the app"],
                    "lockedFeatureTypes": ["core loop"],
                    "locksCoreLoop": True,
                },
                "paywall": {"timing": "afterFirstPersonalizedValue", "triggers": ["user taps Pro feature"]},
            },
            "onboarding": {
                "collectsPreferences": True,
                "paywallTiming": "afterFirstPersonalizedValue",
                "restorePurchasesVisible": True,
                "termsAndPrivacyVisibleOnPaywall": True,
            },
            "reviewPromptPolicy": {
                "usesStoreKitRequestReview": True,
                "minimumDaysSinceInstall": 3,
                "minimumSessions": 3,
                "localCooldownDays": 120,
                "positiveMomentTriggers": [{"event": "completed_goal", "afterSuccessfulUserOutcome": True}],
                "blockedContexts": ["launch", "onboarding", "paywall", "error"],
            },
        }
        result = cli.plan_growth_strategy(config)
        fields = {issue["field"] for issue in result["issues"]}
        self.assertIn("freeProAccessModel.proTier.locksCoreLoop", fields)

    def test_growth_strategy_warns_without_preview_first_paywall_principle(self):
        cli = load_cli()
        config = {
            "subscriptions": [{"id": "sub-123", "productId": "com.example.pro.monthly"}],
            "subscriptionPricing": {"useSingleSubscriptionGroup": True},
            "freeProAccessModel": {
                "targetFreeAccessPercent": 75,
                "targetProAccessPercent": 25,
                "freeTier": {"features": ["Browse results", "Open summaries", "Save one item"]},
                "proTier": {
                    "features": ["Unlimited saved items", "Advanced readers", "External provider actions"],
                    "lockedFeatureTypes": ["unlimited usage", "advanced readers", "provider actions"],
                },
                "paywall": {
                    "timing": "afterFirstPersonalizedValue",
                    "triggers": ["user taps a clearly labeled Pro action"],
                    "principles": ["explain Pro value clearly", "keep terms and restore visible"],
                },
            },
            "onboarding": {
                "collectsPreferences": True,
                "paywallTiming": "afterFirstPersonalizedValue",
                "restorePurchasesVisible": True,
                "termsAndPrivacyVisibleOnPaywall": True,
            },
            "reviewPromptPolicy": {
                "usesStoreKitRequestReview": True,
                "minimumDaysSinceInstall": 3,
                "minimumSessions": 3,
                "localCooldownDays": 120,
                "positiveMomentTriggers": [{"event": "completed_goal", "afterSuccessfulUserOutcome": True}],
                "blockedContexts": ["launch", "onboarding", "paywall", "error"],
            },
        }
        result = cli.plan_growth_strategy(config)
        fields = {issue["field"] for issue in result["issues"]}
        self.assertIn("freeProAccessModel.paywall.principles", fields)

    def test_growth_strategy_template_is_valid(self):
        cli = load_cli()
        config = json.loads(
            (ROOT / "plugins/apple-app-store-connect/assets/subscription-onboarding-review-template.json").read_text()
        )
        config["subscriptions"] = [
            {"id": "weekly-subscription-id", "productId": "com.example.app.pro.weekly"},
            {"id": "monthly-subscription-id", "productId": "com.example.app.pro.monthly"},
            {"id": "yearly-subscription-id", "productId": "com.example.app.pro.yearly"},
        ]
        config["pricingAvailability"] = {"downloadPrice": "0.00"}
        result = cli.plan_growth_strategy(config)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["plannedPricingActions"]), 3)
        self.assertEqual(len(result["plannedIntroOfferActions"]), 3)
        self.assertEqual(
            {offer["duration"] for offer in result["plannedIntroOfferActions"]},
            {"TWO_WEEKS"},
        )


if __name__ == "__main__":
    unittest.main()
