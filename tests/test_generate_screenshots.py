import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins" / "apple-app-store-connect" / "scripts"
GENERATOR = SCRIPTS / "generate_screenshots.py"


def load_generator():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("generate_screenshots", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["generate_screenshots"] = module
    spec.loader.exec_module(module)
    return module


class ScreenshotCopyValidationTests(unittest.TestCase):
    def test_public_screenshot_copy_rejects_price_references(self):
        generator = load_generator()
        config = {
            "screens": [
                {
                    "headline": "Know your day instantly",
                    "subheadline": "A useful dashboard.",
                    "cta": "Free to download",
                },
                {
                    "headline": "Upgrade with confidence",
                    "subheadline": "A better workflow.",
                    "cta": "Start 14-day free trial",
                    "ctaNote": "No payment due now",
                },
            ]
        }
        with self.assertRaisesRegex(ValueError, "price, free, trial"):
            generator.validate_public_screenshot_copy(config)

    def test_public_screenshot_copy_allows_neutral_pro_labels(self):
        generator = load_generator()
        config = {
            "screens": [
                {
                    "headline": "Know your day instantly",
                    "subheadline": "A useful dashboard.",
                    "cta": "Daily dashboard",
                },
                {
                    "headline": "Go deeper when it matters",
                    "subheadline": "Show paid depth clearly.",
                    "cta": "Pro feature",
                    "paid": True,
                },
            ]
        }
        generator.validate_public_screenshot_copy(config)

    def test_price_reference_override_requires_reason(self):
        generator = load_generator()
        config = {
            "allowPriceReferencesInScreenshots": True,
            "screens": [{"headline": "Internal review", "cta": "$4.99 weekly"}],
        }
        with self.assertRaisesRegex(ValueError, "priceReferenceOverrideReason"):
            generator.validate_public_screenshot_copy(config)
        config["priceReferenceOverrideReason"] = "Private internal diagnostic render, not public App Store screenshots."
        generator.validate_public_screenshot_copy(config)


if __name__ == "__main__":
    unittest.main()
