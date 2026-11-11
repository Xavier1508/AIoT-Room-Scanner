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

    def test_sensor_commands_and_status_are_in_contract(self):
        command_schema = self.spec["paths"]["/api/command"]["post"]["requestBody"]["content"]["text/plain"]["schema"]
        for command in ("sensors_start", "sensors_stop", "scan_mode_start", "scan_mode_stop",
                        "hlk_alert_on", "hlk_alert_off", "stepper_left_5", "stepper_right_5",
                        "servo_up_25", "servo_down_25"):
            self.assertIn(command, command_schema["enum"])
        status = self.spec["components"]["schemas"]["Status"]
        self.assertIn("sensors", status["required"])
        self.assertIn("scan", status["required"])
        self.assertIn("hlk_alert", status["required"])
        self.assertIn("ml", status["required"])
        self.assertIn("class", status["properties"]["ml"]["properties"])
        self.assertIn("confidence", status["properties"]["ml"]["properties"])
        self.assertIn("health", status["properties"]["sensors"]["properties"])
        self.assertIn("stats", status["properties"]["sensors"]["properties"])
        self.assertIn("hlk", status["properties"]["sensors"]["properties"])
        self.assertIn("hc_sr04", status["properties"]["sensors"]["properties"])
        self.assertIn("vl53l1x", status["properties"]["sensors"]["properties"])


if __name__ == "__main__":
    unittest.main()
