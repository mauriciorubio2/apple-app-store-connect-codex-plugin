import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "apple-app-store-connect"


class AssetTests(unittest.TestCase):
    def test_json_assets_load(self):
        for path in [
            ROOT / ".agents/plugins/marketplace.json",
            PLUGIN / ".codex-plugin/plugin.json",
            PLUGIN / ".mcp.json",
            PLUGIN / "assets/field-map.json",
            PLUGIN / "assets/submission-template.json",
            PLUGIN / "assets/screenshot-recipe.json",
            PLUGIN / "assets/screenshot-template.json",
            PLUGIN / "assets/app-icon-options-recipe.json",
            PLUGIN / "assets/subscription-onboarding-review-template.json",
        ]:
            with self.subTest(path=path):
                json.loads(path.read_text())

    def test_manifest_has_release_metadata(self):
        manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
        self.assertEqual(manifest["version"], "1.14.7")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["repository"], "https://github.com/mauriciorubio2/apple-app-store-connect-codex-plugin")
        self.assertIn("mcpServers", manifest)

    def test_screenshot_recipe_defaults_to_large_device_and_cta_layout(self):
        recipe = json.loads((PLUGIN / "assets/screenshot-recipe.json").read_text())
        self.assertGreaterEqual(recipe["phoneWidthRatio"], 0.84)
        self.assertLessEqual(recipe["phoneTopRatio"], 0.32)
        self.assertTrue(
            any("large enough device capture" in note for note in recipe["recipeNotes"])
        )

    def test_public_screenshot_recipes_avoid_price_references(self):
        forbidden = re.compile(
            r"(?i)([$€£¥]\s?\d|\bfree\b|\btrial\b|\bdiscount(?:ed)?\b|\bsale\b|\bsave\b|\b\d+\s?%\s?off\b|no payment)"
        )
        for path in [
            PLUGIN / "assets/screenshot-recipe.json",
            PLUGIN / "assets/screenshot-template.json",
        ]:
            with self.subTest(path=path):
                recipe = json.loads(path.read_text(encoding="utf-8"))
                for index, screen in enumerate(recipe.get("screens", [])):
                    for field in ("headline", "subheadline", "cta", "ctaNote", "paidBadge"):
                        value = screen.get(field)
                        if value:
                            self.assertIsNone(
                                forbidden.search(value),
                                f"{path.name} screens[{index}].{field} contains price-reference wording",
                            )


if __name__ == "__main__":
    unittest.main()
