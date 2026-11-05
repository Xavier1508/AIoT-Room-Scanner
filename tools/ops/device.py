#!/usr/bin/env python3
"""Reusable USB provisioning, LAN diagnostics and OTA. No password logging.

Run with the existing PlatformIO Python (pyserial 3.5 is already bundled).
Wi-Fi secrets are sent only to the ESP over USB and never saved on the PC.
The optional local web-access file is gitignored, NOT encrypted at rest.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import getpass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import struct
import sys
import time
from urllib import error, parse, request
import webbrowser

ROOT = Path(__file__).resolve().parents[2]
ACCESS = Path(__file__).with_name("device.local.json")
SETUP_STAGE = "idle"


def emit(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def select_port(explicit=None):
    if explicit:
        return explicit
    from serial.tools import list_ports
    candidates = [p.device for p in list_ports.comports()
                  if p.vid == 0x303A and p.pid == 0x1001]
    if len(candidates) != 1:
        raise ValueError("ESP USB port ambiguous/unavailable; specify --port after checking enumeration.")
    return candidates[0]


class Usb:
    def __init__(self, port):
        import serial
        self.connection = serial.Serial(port=None, baudrate=115200, timeout=0.1,
                                        write_timeout=2)
        self.connection.dtr = False
        self.connection.rts = False
        self.connection.port = port
        self.connection.open()
        self.last_response = 0.0
        time.sleep(0.25)  # Let Windows finish opening the native USB CDC pipe.

    def close(self):
        self.connection.close()

    def transact(self, line, expected=None, timeout=8):
        pause = 0.25 - (time.monotonic() - self.last_response)
        if pause > 0:
            time.sleep(pause)
        if expected is None and line == "status":
            expected = lambda value: "version" in value and "mode" in value
        elif expected is None and line == "selftest":
            expected = lambda value: "synthetic_only" in value
        elif expected is None and line.startswith("provision\t"):
            expected = lambda value: value.get("message") in (
                "provisioned", "invalid_config_or_nvs_failure", "busy_no_config_change")
        elif expected is None and (line == "wifi_scan_results" or line.startswith("wifi_scan_page_")):
            expected = lambda value: "wifi_scan" in value
        # Do not PurgeComm a live native-USB endpoint between transactions:
        # queued device packets can still be completing after the prior line.
        payload = line.encode("utf-8") + b"\n"
        # Native USB can outrun the core's RX queue. Pace long provisioning
        # records; never retry a timed-out actuator command automatically.
        for offset in range(0, len(payload), 64):
            self.connection.write(payload[offset:offset + 64])
            self.connection.flush()
            if len(payload) > 64:
                time.sleep(0.005)
        until = time.monotonic() + timeout
        buffer = bytearray()
        received = 0
        frames = 0
        while time.monotonic() < until:
            chunk = self.connection.read(4096)
            received += len(chunk)
            buffer.extend(chunk)
            while b"\n" in buffer:
                raw, _, remainder = buffer.partition(b"\n")
                buffer[:] = remainder
                marker = raw.rfind(b"AIOT ")
                if marker < 0:
                    continue
                try:
                    result = json.loads(raw[marker + 5:])
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(result, dict):
                    continue
                frames += 1
                if result.get("event") == "ready":
                    continue
                if expected is None or expected(result):
                    self.last_response = time.monotonic()
                    return result
            if len(buffer) > 32768:
                raise ValueError("Oversized serial response rejected.")
        kind = "provision" if line.startswith("provision\t") else (line if line in ("status", "selftest", "stop") else "command")
        raise TimeoutError(f"No matching {kind} response ({received} bytes, {frames} JSON frames). No automatic retry/reset attempted.")

    def status(self):
        return self.transact("status", lambda v: "version" in v and "mode" in v)


def validate_image(data, slot=0x640000):
    """Non-semantic ESP application format check, not a signature/security audit."""
    if not 288 <= len(data) <= slot:
        raise ValueError("Application image size does not fit the OTA slot.")
    if data[0] != 0xE9 or not 1 <= data[1] <= 16:
        raise ValueError("Not an ESP application image.")
    if struct.unpack_from("<H", data, 12)[0] != 9:
        raise ValueError("Image is not for ESP32-S3.")
    if struct.unpack_from("<I", data, 32)[0] != 0xABCD5432:
        raise ValueError("Application descriptor missing; bootloader/merged images are forbidden.")
    return hashlib.sha256(data).hexdigest()


def safe_host(host):
    parts = parse.urlsplit(host)
    if parts.scheme != "http" or parts.username or parts.password or parts.path not in ("", "/"):
        raise ValueError("Expected a plain local-device HTTP URL without credentials/path.")
    address = ipaddress.ip_address(parts.hostname or "")
    private_ranges = (ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("172.16.0.0/12"),
                      ipaddress.ip_network("192.168.0.0/16"))
    if address.version != 4 or not any(address in network for network in private_ranges):
        raise ValueError("Only the ESP's private IPv4 LAN address is permitted.")
    if parts.port not in (None, 80):
        raise ValueError("Only the firmware's port 80 is permitted.")
    return f"http://{address}"


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward device credentials to a redirect target.


class Lan:
    def __init__(self):
        if not ACCESS.is_file():
            raise ValueError("No local web access configured. Run device.py setup in your terminal first.")
        access = json.loads(ACCESS.read_text(encoding="utf-8"))
        self.host = safe_host(access["host"])
        raw = (access["username"] + ":" + access["password"]).encode("utf-8")
        self.authorization = "Basic " + base64.b64encode(raw).decode("ascii")
        self.opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
        self.csrf = None

    def call(self, path, method="GET", data=None, authenticated=True, csrf=True,
             headers=None, timeout=8):
        outgoing = dict(headers or {})
        if authenticated:
            outgoing["Authorization"] = self.authorization
        if csrf and method == "POST" and self.csrf:
            outgoing["X-CSRF-Token"] = self.csrf
        req = request.Request(self.host + path, data=data, headers=outgoing, method=method)
        try:
            response = self.opener.open(req, timeout=timeout)
        except error.HTTPError as exc:
            response = exc
        with response:
            body = response.read(65536)
            try:
                value = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                value = {"non_json_response": True}
            return response.status, value

    def session(self):
        code, value = self.call("/api/session")
        if code != 200 or "csrf" not in value:
            raise ValueError(f"Cannot authenticate to device (HTTP {code}); no credentials logged.")
        self.csrf = value["csrf"]

    def status(self):
        code, value = self.call("/api/status")
        if code != 200 or "version" not in value:
            raise ValueError(f"Device status unavailable (HTTP {code}).")
        return value

    def command(self, name):
        if self.csrf is None:
            self.session()
        code, value = self.call("/api/command", "POST", name.encode("ascii"),
                                headers={"Content-Type": "text/plain"})
        if code != 202:
            return {"http_status": code, "result": value}
        ident = value["command_id"]
        until = time.monotonic() + 3
        while time.monotonic() < until:
            state = self.status()
            if ident == 0:
                if state["mode"] == "IDLE" and not state["motor_armed"] and not state["servo_armed"]:
                    return {"ok": True, "message": "stopped_disarmed"}
            elif state["last_command_id"] == ident:
                return state["last_result"]
            time.sleep(0.15)
        raise TimeoutError("Command result not observed. Do not retry a movement blindly.")


def assert_safe(state):
    assert state["mode"] == "IDLE", "Firmware not IDLE"
    assert not state["motor_armed"] and not state["servo_armed"], "Unexpected armed state"
    actuators = state["actuators"]
    assert not actuators["buzzer_commanded_on"], "Unexpected buzzer output"
    assert not actuators["stepper_energized"], "Unexpected coil output"
    assert not actuators["servo_attached"], "Unexpected servo attachment"


def usb_verify(usb):
    report = {"transport": "USB", "physical_peripherals_tested": False, "cases": []}
    state = usb.status()
    assert_safe(state)
    report["before"] = state
    for command in ("step_test", "servo_test", "step_test 1000", "unknown_command",
                    "step_test\x00ignored", "provision\t00\t00\t00"):
        result = usb.transact(command)
        assert result.get("ok") is False, "Unsafe command unexpectedly accepted"
        assert_safe(usb.status())
        report["cases"].append({"command": command, "result": result, "passed": True})
    assert usb.status()["wifi"]["configured"] == state["wifi"]["configured"]
    result = usb.transact("selftest")
    assert result.get("synthetic_only") and result.get("failed") == 0
    report["cases"].append({"selftest": result, "passed": True})
    assert usb.transact("stop").get("ok") is True
    report["after"] = usb.status()
    assert_safe(report["after"])
    return report


def display_ssid(raw):
    text = raw.decode("utf-8", errors="replace")
    return "".join(c if c.isprintable() else "?" for c in text)


def ssid_bytes(record):
    text = record.get("ssid_hex", "")
    if (not isinstance(text, str) or not 2 <= len(text) <= 64 or len(text) % 2 or
            any(c not in "0123456789abcdefABCDEF" for c in text)):
        raise ValueError("Invalid SSID record received from device.")
    try:
        value = bytes.fromhex(text)
    except ValueError:
        raise ValueError("Invalid SSID encoding received from device.") from None
    if not 1 <= len(value) <= 32 or b"\0" in value:
        raise ValueError("Unsupported empty/NUL-containing SSID record.")
    return value


def scan_wifi(usb):
    assert_safe(usb.status())
    started = usb.transact("wifi_scan")
    if not started.get("ok"):
        raise ValueError("Cannot start ESP Wi-Fi scan; use firmware 0.2.0-scan or newer, with no OTA active.")
    until = time.monotonic() + 25
    scan = None
    while time.monotonic() < until:
        scan = usb.transact("wifi_scan_results")["wifi_scan"]
        if scan["state"] == "done":
            break
        if scan["state"] in ("failed", "cancelled"):
            raise ValueError("ESP passive Wi-Fi scan failed/cancelled; no credentials sent.")
        time.sleep(0.5)
    if not scan or scan["state"] != "done":
        usb.transact("wifi_scan_cancel")
        raise TimeoutError("Wi-Fi scan timed out; no credentials sent.")
    if not scan.get("passive") or scan.get("band") != "2.4GHz" or not 0 <= scan.get("pages", -1) <= 8:
        raise ValueError("Unexpected scan protocol; refusing setup.")
    networks = []
    for page in range(scan["pages"]):
        result = usb.transact(f"wifi_scan_page_{page}")["wifi_scan"]
        if result["state"] != "done" or result["scan_id"] != scan["scan_id"] or result["page"] != page:
            raise ValueError("Wi-Fi scan changed while reading pages; scan again.")
        if len(result["networks"]) > 6:
            raise ValueError("Oversized scan page rejected.")
        for record in result["networks"]:
            ssid_bytes(record)  # Validate arbitrary over-the-air bytes.
            networks.append(record)
    if len(networks) != scan["retained_networks"] or len(networks) > 48:
        raise ValueError("Incomplete scan results; no credentials sent.")
    scan["networks"] = networks
    usb.transact("stop")  # Keep IDLE and remove SSID pages from last-result status.
    assert_safe(usb.status())
    return scan


AUTH_NAMES = {0: "OPEN", 1: "WEP", 2: "WPA-Personal", 3: "WPA2-Personal",
              4: "WPA/WPA2-Personal", 5: "Enterprise", 6: "WPA3-Personal",
              7: "WPA2/WPA3-Personal"}


def choose_wifi(usb):
    while True:
        print("\nESP32-S3 memindai beacon Wi-Fi 2,4 GHz secara pasif...")
        scan = scan_wifi(usb)
        print(f"Terlihat {scan['observed_ap_count']} AP; {len(scan['networks'])} pilihan SSID/keamanan, terkuat dahulu.")
        if scan.get("truncated"):
            print("Daftar dibatasi 48 pilihan terkuat; hasil bukan seluruh jaringan di semua lokasi.")
        if scan.get("hidden_ap_count"):
            print("Ada SSID tersembunyi; namanya tidak dapat ditemukan dari beacon pasif. Gunakan M bila milik Anda.")
        for index, record in enumerate(scan["networks"], 1):
            name = display_ssid(ssid_bytes(record))
            security = AUTH_NAMES.get(record["auth"], "auth " + str(record["auth"]))
            print(f" {index:2d}. {name!r} | {record['rssi_dbm']} dBm | kanal {record['channel']} | {security}")
        print("Pilih hanya jaringan milik Anda/yang diizinkan; SSID terlihat bukan bukti kepemilikan.")
        while True:
            choice = input("Nomor SSID / R scan ulang / M input tersembunyi / Q batal: ").strip()
            if choice.lower() == "q":
                raise ValueError("Setup dibatalkan; tidak ada kredensial baru dikirim.")
            if choice.lower() == "r":
                break
            if choice.lower() == "m":
                raw = input("SSID tersembunyi milik Anda (opsional/manual): ").encode("utf-8")
                if not 1 <= len(raw) <= 32 or b"\0" in raw:
                    print("SSID harus 1-32 byte dan tidak mengandung NUL.")
                    continue
                return raw, None
            if choice.isdecimal() and 1 <= int(choice) <= len(scan["networks"]):
                record = scan["networks"][int(choice)-1]
                if record["auth"] not in (0, 3, 4, 6, 7):
                    print("Pilih OPEN yang diizinkan atau WPA2/WPA3 Personal; WEP/WPA1/Enterprise tidak didukung setup ini.")
                    continue
                return ssid_bytes(record), record["auth"]
            print("Pilih nomor yang ada, R, M, atau Q.")


def setup(usb):
    global SETUP_STAGE
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("Setup requires your own interactive terminal, not agent logs or redirected input.")
    SETUP_STAGE = "safe-state-check"
    assert_safe(usb.status())
    print("Provisioning USB lokal. Jangan pasang adaptor jack saat USB masih terhubung.")
    print("Password Wi-Fi tidak disimpan di PC. Akses web disimpan lokal di device.local.json (gitignored, tidak terenkripsi).")
    SETUP_STAGE = "scan-and-select-ssid"
    ssid, auth = choose_wifi(usb)
    print("SSID dipilih: " + repr(display_ssid(ssid)))
    if auth == 0:
        if input("Jaringan OPEN tidak terenkripsi. Tetap gunakan jaringan berizin ini? [y/N]: ").lower() != "y":
            raise ValueError("Setup dibatalkan sebelum mengirim kredensial.")
    SETUP_STAGE = "wifi-password-input"
    wifi = "" if auth == 0 else getpass.getpass("Password Wi-Fi (input tersembunyi): ")
    SETUP_STAGE = "web-password-input"
    password = getpass.getpass("Password web unik, 16–64 karakter ASCII tanpa spasi: ")
    confirmation = getpass.getpass("Ulangi password web: ")
    SETUP_STAGE = "validate-input"
    if not 1 <= len(ssid) <= 32:
        raise ValueError("SSID must be 1–32 UTF-8 bytes.")
    if wifi and not 8 <= len(wifi.encode("utf-8")) <= 63:
        raise ValueError("Wi-Fi password must be 8–63 UTF-8 bytes (or empty for an intentionally open network).")
    if password != confirmation or not 16 <= len(password) <= 64 or password == wifi:
        raise ValueError("Web password mismatch, invalid length, or same as Wi-Fi password.")
    if any(ord(c) < 33 or ord(c) > 126 for c in password):
        raise ValueError("Web password must use printable ASCII without spaces.")
    if auth == 0 and wifi:
        raise ValueError("Jaringan OPEN harus memakai password Wi-Fi kosong.")
    if auth is not None and auth != 0 and not wifi:
        raise ValueError("Jaringan Personal yang dipilih memerlukan password Wi-Fi.")
    fields = [ssid.hex(), wifi.encode("utf-8").hex(), password.encode("ascii").hex()]
    SETUP_STAGE = "send-to-device"
    result = usb.transact("provision\t" + "\t".join(fields), timeout=15)
    if not result.get("ok"):
        raise ValueError("Firmware rejected provisioning; old config has not intentionally been erased.")
    print("Konfigurasi tersimpan di ESP. Menunggu koneksi Wi-Fi…")
    SETUP_STAGE = "wait-for-wifi"
    until = time.monotonic() + 60
    state = None
    while time.monotonic() < until:
        state = usb.status()
        if state["wifi"]["connected"] and state["wifi"]["web_ready"]:
            break
        time.sleep(1)
    if not state or not state["wifi"]["connected"]:
        raise TimeoutError("Wi-Fi belum terhubung. USB tetap terpasang; cek SSID/password/2,4 GHz, lalu ulangi setup.")
    host = safe_host("http://" + state["wifi"]["ip"])
    access = {"host": host, "username": "admin", "password": password}
    SETUP_STAGE = "save-local-web-access"
    fd = os.open(ACCESS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(access, file)
        file.write("\n")
    print("Web siap: " + host + " (username admin; password yang baru Anda tentukan).")
    print("Jangan cabut USB dahulu. Jalankan lan-test atau minta agen memverifikasi jaringan.")
    summary = {"ok": True, "host": host, "version": state["version"],
               "credentials_saved_locally": True, "wifi_password_saved_on_pc": False,
               "mode": state["mode"], "web_ready": state["wifi"]["web_ready"]}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    evidence = ROOT / "analysis" / "device" / ("provision-" + stamp)
    evidence.mkdir(parents=True)
    (evidence / "result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    SETUP_STAGE = "done"
    return summary


def lan_verify(lan):
    report = {"transport": "LAN", "physical_peripherals_tested": False, "cases": []}
    report["before"] = lan.status()
    assert_safe(report["before"])
    code, _ = lan.call("/api/status", authenticated=False)
    assert code == 401
    report["cases"].append({"name": "status_requires_auth", "http": code, "passed": True})
    code, _ = lan.call("/api/command", "POST", b"motor_arm", csrf=False,
                       headers={"Content-Type": "text/plain"})
    assert code == 403
    report["cases"].append({"name": "actuator_requires_csrf", "http": code, "passed": True})
    lan.session()
    code, _ = lan.call("/api/command", "GET")
    assert code in (404, 405)
    report["cases"].append({"name": "no_get_command", "http": code, "passed": True})
    for command in ("step_test", "servo_test", "unknown_command"):
        result = lan.command(command)
        if command == "unknown_command":
            assert result.get("http_status") == 400
        else:
            assert result.get("ok") is False
        report["cases"].append({"command": command, "result": result, "passed": True})
        assert_safe(lan.status())
    synthetic = lan.command("selftest")
    assert synthetic.get("synthetic_only") and synthetic.get("failed") == 0
    report["cases"].append({"name": "synthetic_selftest", "result": synthetic, "passed": True})
    code, result = lan.call("/api/ota", "POST", bytes(288), headers={
        "Content-Type": "application/octet-stream", "X-Firmware-Name": "firmware.bin"})
    assert code == 400
    report["cases"].append({"name": "reject_non_application_ota", "http": code, "passed": True})
    time.sleep(0.3)
    report["after"] = lan.status()
    assert_safe(report["after"])
    return report


def ota(lan, path, expected):
    path = Path(path)
    if path.name != "firmware.bin":
        raise ValueError("Only application firmware.bin is accepted, never merged/factory/bootloader images.")
    before = lan.status()
    assert_safe(before)
    if before["version"] == expected:
        raise ValueError("Expected OTA version must differ from the currently running version.")
    data = path.read_bytes()
    digest = validate_image(data, before["ota"]["next_slot_bytes"])
    lan.session()
    code, result = lan.call("/api/ota", "POST", data, headers={
        "Content-Type": "application/octet-stream", "X-Firmware-Name": "firmware.bin",
        "X-Firmware-SHA256": digest}, timeout=125)
    if code != 200 or not result.get("ok"):
        raise ValueError(f"OTA rejected/failed (HTTP {code}); do not assume a new version booted.")
    until = time.monotonic() + 45
    after = None
    while time.monotonic() < until:
        time.sleep(1)
        try:
            after = lan.status()
        except (OSError, ValueError):
            continue
        if after["version"] == expected:
            break
    if not after or after["version"] != expected:
        raise TimeoutError("Upload accepted, but the expected new version was NOT observed.")
    assert_safe(after)
    return {"transport": "LAN_OTA", "sha256": digest, "expected_version": expected,
            "before": before, "upload_response": result, "after": after,
            "new_version_observed": True, "power_mode_requires_operator_evidence": True}


def main():
    global SETUP_STAGE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Verified USB port; default selects exactly one Espressif native USB device")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("ports")
    serial_parser = sub.add_parser("serial")
    serial_parser.add_argument("command", nargs="?", default="status")
    for action in ("setup", "verify-usb", "status", "lan-test", "open"):
        sub.add_parser(action)
    scan_parser = sub.add_parser("scan")
    scan_parser.add_argument("--summary", action="store_true", help="Do not print SSID metadata; show only counts/signal/channel")
    command_parser = sub.add_parser("command")
    command_parser.add_argument("command")
    ota_parser = sub.add_parser("ota")
    ota_parser.add_argument("firmware")
    ota_parser.add_argument("--expect-version", required=True)
    args = parser.parse_args()
    if args.action == "ports":
        from serial.tools import list_ports
        emit([{"port": p.device, "description": p.description, "vid": p.vid, "pid": p.pid}
              for p in list_ports.comports()])
    elif args.action in ("serial", "setup", "verify-usb", "scan"):
        if args.action == "setup":
            SETUP_STAGE = "open-usb"
        usb = Usb(select_port(args.port))
        try:
            if args.action == "serial":
                emit(usb.transact(args.command))
            elif args.action == "setup":
                emit(setup(usb))
            elif args.action == "scan":
                scan = scan_wifi(usb)
                if args.summary:
                    scan = {key: value for key, value in scan.items() if key != "networks"}
                emit({"wifi_scan": scan})
            else:
                emit(usb_verify(usb))
        finally:
            usb.close()
    else:
        lan = Lan()
        if args.action == "status":
            emit(lan.status())
        elif args.action == "lan-test":
            emit(lan_verify(lan))
        elif args.action == "command":
            emit(lan.command(args.command))
        elif args.action == "ota":
            emit(ota(lan, args.firmware, args.expect_version))
        else:
            webbrowser.open(lan.host)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TimeoutError, AssertionError, KeyError, EOFError, KeyboardInterrupt) as exc:
        if SETUP_STAGE != "idle":
            # Persist only a fixed stage/type, never exception text or inputs.
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            folder = ROOT / "analysis" / "device" / ("provision-error-" + stamp)
            folder.mkdir(parents=True)
            (folder / "result.json").write_text(json.dumps({"operation": "setup", "stage": SETUP_STAGE,
                "error_type": type(exc).__name__, "credentials_logged": False}, indent=2) + "\n", encoding="utf-8")
        message = "Input/setup dibatalkan oleh pengguna." if isinstance(exc, (EOFError, KeyboardInterrupt)) else str(exc)
        print(f"ERROR: {message}", file=sys.stderr)
        sys.exit(1)
