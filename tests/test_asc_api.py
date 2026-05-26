import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASC_API = ROOT / "plugins" / "apple-app-store-connect" / "scripts" / "asc_api.py"


def load_module():
    spec = importlib.util.spec_from_file_location("asc_api", ASC_API)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["asc_api"] = module
    spec.loader.exec_module(module)
    return module


class AscApiTests(unittest.TestCase):
    def test_b64url_strips_padding(self):
        api = load_module()
        self.assertEqual(api.b64url(b"hello"), "aGVsbG8")

    def test_der_ecdsa_to_raw(self):
        api = load_module()
        r = bytes.fromhex("01")
        s = bytes.fromhex("02")
        der = b"\x30\x06\x02\x01" + r + b"\x02\x01" + s
        raw = api.der_ecdsa_to_raw(der)
        self.assertEqual(len(raw), 64)
        self.assertEqual(raw[:31], b"\x00" * 31)
        self.assertEqual(raw[31], 1)
        self.assertEqual(raw[63], 2)


if __name__ == "__main__":
    unittest.main()
