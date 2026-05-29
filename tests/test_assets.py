import json
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
        ]:
            with self.subTest(path=path):
                json.loads(path.read_text())

    def test_manifest_has_release_metadata(self):
        manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
        self.assertEqual(manifest["version"], "1.3.1")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["repository"], "https://github.com/mauriciorubio2/apple-app-store-connect-codex-plugin")
        self.assertIn("mcpServers", manifest)


if __name__ == "__main__":
    unittest.main()
