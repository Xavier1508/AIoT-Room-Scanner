import importlib.util
from pathlib import Path
import struct
import unittest
from unittest import mock

source = Path(__file__).resolve().parents[1] / "tools" / "ops" / "device.py"
spec = importlib.util.spec_from_file_location("device", source)
device = importlib.util.module_from_spec(spec)
spec.loader.exec_module(device)


class ImageValidation(unittest.TestCase):
    def image(self):
        data = bytearray(512)
        data[0:2] = bytes([0xE9, 3])
        struct.pack_into("<H", data, 12, 9)
        struct.pack_into("<I", data, 32, 0xABCD5432)
        return data

    def test_fixture_header(self):
        self.assertEqual(len(device.validate_image(self.image())), 64)

    def test_wrong_chip(self):
        data = self.image()
        struct.pack_into("<H", data, 12, 0)
        with self.assertRaises(ValueError):
            device.validate_image(data)

    def test_bootloader_without_app_descriptor(self):
        data = self.image()
        data[32:36] = bytes(4)
        with self.assertRaises(ValueError):
            device.validate_image(data)

    def test_short_and_oversized(self):
        for data, slot in ((bytes(10), 1024), (self.image(), 300)):
            with self.assertRaises(ValueError):
                device.validate_image(data, slot)

    def test_private_device_url_only(self):
        self.assertEqual(device.safe_host("http://192.168.1.20"), "http://192.168.1.20")
        for host in ("https://192.168.1.20", "http://8.8.8.8", "http://user:secret@192.168.1.20",
                     "http://127.0.0.1", "http://192.168.1.20:8080", "http://192.168.1.20/other"):
            with self.assertRaises(ValueError):
                device.safe_host(host)


class UsbFraming(unittest.TestCase):
    class FakeSerial:
        def __init__(self, responses):
            self.responses = list(responses)
            self.writes = []

        def reset_input_buffer(self):
            pass

        def write(self, data):
            self.writes.append(data)

        def flush(self):
            pass

        def read(self, size):
            return self.responses.pop(0) if self.responses else b""

    def fake_usb(self, responses):
        usb = device.Usb.__new__(device.Usb)
        usb.connection = self.FakeSerial(responses)
        usb.last_response = 0.0
        return usb

    def test_status_does_not_accept_stale_generic_reply(self):
        usb = self.fake_usb([b'AIOT {"ok":false,"message":"old"}\n',
                             b'AIOT {"version":"fixture","mode":"IDLE"}\n'])
        self.assertEqual(usb.transact("status")["version"], "fixture")

    def test_long_provisioning_is_chunked_not_retried(self):
        usb = self.fake_usb([b'AIOT {"ok":true,"message":"provisioned"}\n'])
        payload = "provision\t" + ("ab" * 160)
        with mock.patch.object(device.time, "sleep"):
            self.assertTrue(usb.transact(payload)["ok"])
        self.assertTrue(all(len(chunk) <= 64 for chunk in usb.connection.writes))
        self.assertEqual(b"".join(usb.connection.writes), payload.encode() + b"\n")

    def test_ignores_boot_event_and_handles_partial_lines(self):
        usb = self.fake_usb([b'AIOT {"event":"ready"}\nAIOT {"synthetic_',
                             b'only":true,"passed":34,"failed":0}\n'])
        self.assertEqual(usb.transact("selftest")["failed"], 0)

    def test_recovers_prefix_after_an_old_partial_record(self):
        usb = self.fake_usb([b'old-truncated-dataAIOT {"version":"fixture","mode":"IDLE"}\n'])
        self.assertEqual(usb.transact("status")["mode"], "IDLE")


class WifiScanSetup(unittest.TestCase):
    def test_ssid_hex_preserves_real_bytes(self):
        self.assertEqual(device.ssid_bytes({"ssid_hex": "726f6f6d2d6e6574"}), b"room-net")
        self.assertEqual(device.ssid_bytes({"ssid_hex": "c3a9"}), "é".encode("utf-8"))

    def test_rejects_bad_ssid_records(self):
        for value in ("", "0", "zz", "00", "610062", "61  62", "ab" * 33):
            with self.assertRaises(ValueError):
                device.ssid_bytes({"ssid_hex": value})

    def test_terminal_control_sequences_are_not_printed(self):
        display = device.display_ssid(b"name\x1b[31m\nnext\t")
        self.assertNotIn("\x1b", display)
        self.assertNotIn("\n", display)
        self.assertNotIn("\t", display)
        self.assertIn("name", display)

    def test_scan_pages_and_duplicates_use_device_inventory_only(self):
        class FakeUsb:
            def status(self):
                return {"mode": "IDLE", "motor_armed": False, "servo_armed": False,
                        "actuators": {"buzzer_commanded_on": False, "stepper_energized": False, "servo_attached": False}}

            def transact(self, command):
                if command == "wifi_scan":
                    return {"ok": True}
                result = {"state": "done", "scan_id": 2, "passive": True, "band": "2.4GHz",
                          "pages": 1, "retained_networks": 1, "page": 0,
                          "networks": [{"ssid_hex": "726f6f6d", "rssi_dbm": -50, "channel": 6, "auth": 3}]}
                return {"wifi_scan": result}
        scan = device.scan_wifi(FakeUsb())
        self.assertEqual(device.ssid_bytes(scan["networks"][0]), b"room")
        self.assertEqual(scan["scan_id"], 2)

    def test_numbered_selection_does_not_ask_for_ssid_text(self):
        scan = {"observed_ap_count": 1, "networks": [
            {"ssid_hex": "726f6f6d", "rssi_dbm": -50, "channel": 6, "auth": 3}]}
        with mock.patch.object(device, "scan_wifi", return_value=scan), \
                mock.patch("builtins.input", return_value="1") as input_mock, \
                mock.patch("builtins.print"):
            raw, auth = device.choose_wifi(object())
        self.assertEqual(raw, b"room")
        self.assertEqual(auth, 3)
        self.assertEqual(input_mock.call_count, 1)

    def test_cancel_does_not_request_password_or_send_credentials(self):
        with mock.patch.object(device, "scan_wifi", return_value={"observed_ap_count": 0, "networks": []}), \
                mock.patch("builtins.input", return_value="q"), mock.patch("builtins.print"), \
                mock.patch.object(device.getpass, "getpass") as password:
            with self.assertRaises(ValueError):
                device.choose_wifi(object())
            password.assert_not_called()


if __name__ == "__main__":
    unittest.main()
