import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LocalContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))

    def test_internal_references_resolve(self):
        def walk(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    target = self.spec
                    for part in value["$ref"].removeprefix("#/").split("/"):
                        target = target[part]
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(self.spec)

    def test_all_routes_inherit_authentication(self):
        self.assertEqual(self.spec["security"], [{"localBasic": []}])
        for path in self.spec["paths"].values():
            for operation in path.values():
                self.assertNotEqual(operation.get("security"), [])

    def test_mutations_post_only_and_csrf(self):
        for path in ("/api/command", "/api/ota"):
            self.assertEqual(set(self.spec["paths"][path]), {"post"})
            params = self.spec["paths"][path]["post"]["parameters"]
            self.assertIn({"$ref": "#/components/parameters/Csrf"}, params)

    def test_ui_commands_are_in_contract(self):
        page = (ROOT / "include/web_page.h").read_text(encoding="utf-8")
        commands = set(re.findall(r'data-command="([a-z_]+)"', page))
        allowed = self.spec["paths"]["/api/command"]["post"]["requestBody"]["content"]["text/plain"]["schema"]["enum"]
        self.assertTrue(commands.issubset(allowed))


if __name__ == "__main__":
    unittest.main()
