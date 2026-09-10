#!/usr/bin/env python3
"""Small dependency-free local dashboard server."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).parent
ASSETS = {
    "logo-cpu.svg", "logo-nvidia.svg", "logo-amd.svg", "logo-ram.svg",
    "logo-orbit.svg", "logo-hermes.svg", "logo-openwebui.svg", "logo-openviking.svg",
    'logo-litellm.svg', 'logo-searxng.svg', 'logo-euro.svg', 'logo-portainer.svg',
}
HOST = os.environ.get("DASH_HOST", "0.0.0.0")
PORT = int(os.environ.get("DASH_PORT", "8090"))
SERVICE_REGISTRY = Path(os.environ.get("SERVICE_REGISTRY", ROOT / "services.json"))
WATCHDOG_STATE_FILE = Path(os.environ.get("WATCHDOG_STATE_FILE", "/home/rugent/.hermes/state/service-watchdog.json"))
WATCHDOG_OUTPUT_DIR = Path(os.environ.get("WATCHDOG_OUTPUT_DIR", "/home/rugent/.hermes/cron/output/ab1da72efeea"))


def load_services() -> list[dict]:
    """Load the service registry on every status request; edits need no rebuild."""
    try:
        payload = json.loads(SERVICE_REGISTRY.read_text(encoding="utf-8"))
        services = payload["services"]
        if not isinstance(services, list):
            raise ValueError("services must be a list")
        return [dict(item) for item in services]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid service registry: {SERVICE_REGISTRY}") from error


def service_registry() -> list[dict]:
    return load_services()


SERVICES = service_registry()

SESSIONS: dict[str, dict[str, str]] = {}
SESSION_COOKIE = "dash_session"
OPENVIKING_USER_ENV = Path("/run/dash-local-route/openviking-user.env")
OPENVIKING_BACKEND_ENV = Path("/run/dash-local-route/openviking-backend.env")


def _env_value(path: Path, name: str) -> str:
    """Read one secret from a mounted env file without logging its value."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('\\"').strip("'")
    except OSError:
        pass
    return ""


def _openviking_login_token(password: str) -> str:
    """Map the local dashboard password to a real upstream API token."""
    expected_password = _env_value(OPENVIKING_USER_ENV, "OPENVIKING_USER_API_KEY")
    upstream_token = _env_value(OPENVIKING_BACKEND_ENV, "OPENVIKING_API_KEY")
    return upstream_token if expected_password and secrets.compare_digest(password, expected_password) else ""
def proxy_services() -> dict[str, dict]:
    return {
        key: item for key, item in (("orbit", next((s for s in service_registry() if s["name"] == "Orbit"), None)), ("openviking", next((s for s in service_registry() if s["name"] == "OpenViking Studio"), None)))
        if item and item.get("protected") and item.get("proxy_target")
    }


def format_bytes(value: int) -> str:
    value = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"


def _meminfo() -> dict[str, int]:
    data = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, raw = line.split(":", 1)
        data[key] = int(raw.strip().split()[0]) * 1024
    return data


def _cpu_times() -> tuple[int, int]:
    parts = Path("/proc/stat").read_text().splitlines()[0].split()
    values = list(map(int, parts[1:]))
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def _cpu_percent() -> float:
    total_a, idle_a = _cpu_times()
    time.sleep(0.08)
    total_b, idle_b = _cpu_times()
    total = total_b - total_a
    return round(100 * (1 - (idle_b - idle_a) / total), 1) if total else 0.0


def _unavailable_gpu(vendor: str) -> dict:
    return {"vendor": vendor, "percent": None, "temperature_c": None, "vram_used": None, "vram_total": None, "vram_percent": None, "available": False}


def _gpu_metric(vendor: str, percent: float, vram_used: float | None = None, vram_total: float | None = None, temperature_c: float | None = None) -> dict:
    vram_percent = round(100 * vram_used / vram_total, 1) if vram_used is not None and vram_total else None
    return {"vendor": vendor, "percent": round(percent, 1), "temperature_c": temperature_c, "vram_used": vram_used, "vram_total": vram_total, "vram_percent": vram_percent, "available": True}


def _read_cpu_temperature() -> float | None:
    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        try:
            if (hwmon / "name").read_text().strip() != "k10temp":
                continue
            for input_path in sorted(hwmon.glob("temp*_input")):
                label_path = input_path.with_name(input_path.name.replace("_input", "_label"))
                if label_path.exists() and label_path.read_text().strip() == "Tctl":
                    return round(float(input_path.read_text().strip()) / 1000, 1)
        except (OSError, ValueError):
            continue
    return None


def _read_amd_temperature() -> float | None:
    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        try:
            if (hwmon / "name").read_text().strip() != "amdgpu":
                continue
            for input_path in sorted(hwmon.glob("temp*_input")):
                label_path = input_path.with_name(input_path.name.replace("_input", "_label"))
                if label_path.exists() and label_path.read_text().strip() == "edge":
                    return round(float(input_path.read_text().strip()) / 1000, 1)
        except (OSError, ValueError):
            continue
    return None


def _parse_gpu_utilization(output: str, vendor: str) -> dict:
    """Parse a `name, utilization` line into a dashboard metric."""
    for line in output.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) < 2:
            continue
        try:
            percent = float(fields[-1].rstrip("%"))
        except ValueError:
            continue
        return _gpu_metric(vendor, percent)
    return _unavailable_gpu(vendor)


def _parse_radeontop_utilization(output: str) -> dict:
    gpu_match = re.search(r"\bgpu\s+([0-9]+(?:\.[0-9]+)?)%", output)
    vram_match = re.search(r"\bvram\s+([0-9]+(?:\.[0-9]+)?)%\s+([0-9]+(?:\.[0-9]+)?)mb", output, re.IGNORECASE)
    if not gpu_match:
        return _unavailable_gpu("AMD")
    vram_used = None
    vram_total = None
    if vram_match and float(vram_match.group(1)):
        vram_used = float(vram_match.group(2)) * 1024 * 1024
        vram_total = vram_used * 100 / float(vram_match.group(1))
    return _gpu_metric("AMD", float(gpu_match.group(1)), vram_used, vram_total)


def _read_nvidia_gpu() -> dict:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=2,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return _unavailable_gpu("NVIDIA")
    metrics = []
    for line in result.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) < 5:
            continue
        try:
            metrics.append(_gpu_metric("NVIDIA", float(fields[1]), float(fields[2]) * 1024 * 1024, float(fields[3]) * 1024 * 1024, float(fields[4])))
        except ValueError:
            continue
    if not metrics:
        return _unavailable_gpu("NVIDIA")
    return _gpu_metric(
        "NVIDIA",
        sum(metric["percent"] for metric in metrics) / len(metrics),
        sum(metric["vram_used"] for metric in metrics),
        sum(metric["vram_total"] for metric in metrics),
        sum(metric["temperature_c"] for metric in metrics) / len(metrics),
    )


def _read_amd_gpu() -> dict:
    values = []
    for vendor_path in sorted(Path("/sys/class/drm").glob("card[0-9]*/device/vendor")):
        try:
            if vendor_path.read_text().strip().lower() != "0x1002":
                continue
            busy_path = vendor_path.parent / "gpu_busy_percent"
            values.append(float(busy_path.read_text().strip()))
        except (OSError, ValueError):
            continue
    try:
        result = subprocess.run(
            ["radeontop", "-d", "-", "-l", "1"],
            capture_output=True, text=True, check=True, timeout=3,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return _unavailable_gpu("AMD")
    metric = _parse_radeontop_utilization(result.stdout)
    if values and metric["available"]:
        metric["percent"] = round(sum(values) / len(values), 1)
    metric["temperature_c"] = _read_amd_temperature()
    return metric


def read_gpu_stats() -> dict:
    """Return independent NVIDIA and AMD utilization metrics."""
    return {"nvidia": _read_nvidia_gpu(), "amd": _read_amd_gpu()}


def _processes() -> list[dict]:
    try:
        result = subprocess.run(["ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%cpu", "--no-headers"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return []
    rows = []
    for line in result.stdout.splitlines()[:8]:
        fields = line.split()
        if len(fields) >= 4:
            rows.append({"pid": int(fields[0]), "name": fields[1], "cpu": float(fields[2]), "memory_percent": float(fields[3])})
    return rows


def watchdog_status() -> dict:
    """Return a safe, short view of the latest watchdog run for the dashboard."""
    state_records = {}
    try:
        raw_state = json.loads(WATCHDOG_STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(raw_state, dict):
            state_records = raw_state
    except (OSError, ValueError, TypeError):
        pass
    report = ""
    last_run_at = None
    try:
        reports = sorted(WATCHDOG_OUTPUT_DIR.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
        if reports:
            text = reports[0].read_text(encoding="utf-8", errors="replace")
            match = re.search(r"\*\*Run Time:\*\*\s*([^\n]+)", text)
            last_run_at = match.group(1).strip() if match else None
            report = text.split("## Response", 1)[-1].strip() if "## Response" in text else ""
            report = report[:1200]
    except OSError:
        pass
    attempts = sum(int(item.get("attempts", 0)) for item in state_records.values() if isinstance(item, dict))
    cooldowns = [max(0, int(3600 - (time.time() - float(item.get("last_attempt_at", 0))))) for item in state_records.values() if isinstance(item, dict) and item.get("last_attempt_at")]
    if report.startswith("PASS"):
        status = "ONLINE"
    elif report:
        status = "WARNING"
    else:
        status = "UNKNOWN"
    return {"status": status, "last_run_at": last_run_at, "report": report, "restart_attempts": attempts, "restart_limit": 2, "cooldown_active": any(cooldown > 0 for cooldown in cooldowns), "state_records": len(state_records)}


def read_system_stats() -> dict:
    mem = _meminfo()
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", mem.get("MemFree", 0))
    used = max(total - available, 0)
    return {"memory": {"total": total, "used": used, "available": available, "used_percent": round(100 * used / total, 1) if total else 0}, "cpu_percent": _cpu_percent(), "cpu_temperature_c": _read_cpu_temperature(), "gpu": read_gpu_stats(), "processes": _processes(), "updated_at": int(time.time())}


def discover_services() -> list[dict]:
    services = []
    for item in service_registry():
        entry = dict(item)
        request = urllib.request.Request(item.get("check_url", item["url"]), headers={"User-Agent": "dash-local-route/1.0"})
        started = time.perf_counter()
        try:
            context = None
            if item["scheme"] == "https":
                import ssl
                context = ssl._create_unverified_context()
            with urllib.request.urlopen(request, timeout=1.5, context=context) as response:
                entry.update({"online": response.status < 500, "status": response.status, "latency_ms": round((time.perf_counter() - started) * 1000)})
        except (urllib.error.URLError, TimeoutError, OSError):
            entry.update({"online": False, "status": None, "latency_ms": None})
        services.append(entry)
    return services




def _session_token(handler: BaseHTTPRequestHandler) -> str | None:
    raw = handler.headers.get("Cookie", "")
    for item in raw.split(";"):
        key, _, value = item.strip().partition("=")
        if key == SESSION_COOKIE and value in SESSIONS:
            return SESSIONS[value].get("token")
    return None


def _proxy_path(path: str, service: str) -> str | None:
    prefix = f"/proxy/{service}"
    if not path.startswith(prefix):
        return None
    suffix = path[len(prefix):] or "/"
    return suffix if suffix.startswith("/") else "/" + suffix


def _rewrite_proxy_assets(body: bytes, service: str, content_type: str) -> bytes:
    text = body.decode("utf-8", errors="replace")
    prefix = f"/proxy/{service}"
    if "javascript" in content_type or "css" in content_type:
        text = re.sub(r"([\"'`])/(api|studio|assets)(?=[/\"'`])", rf"\1{prefix}/\2", text)
    return text.encode("utf-8")


class DashboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict, extra: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/login":
            proxied = self._proxy_authenticated()
            if proxied:
                _service, upstream_url = proxied
                self._proxy_mutation(upstream_url, _session_token(self) or "")
                return
            if proxied is None and self.path.startswith("/proxy/"):
                return
            self.send_error(404)
            return
        try:
            payload = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 4096)))
            service = payload.get("service", "")
            token = str(payload.get("token", "")).strip()
            if len(token) >= 2 and token[0] == token[-1] and token[0] in "\\\"'":
                token = token[1:-1].strip()
            if token.lower().startswith("bearer "):
                token = token[7:].strip()
            target = proxy_services().get(service)
            if not target or not token or len(token) > 512:
                self._send_json(400, {"error": "Vyber službu a zadaj heslo."})
                return
            # OpenViking uses a friendly local password in the form. The real
            # upstream API key is loaded server-side and never sent to the UI.
            if service == "openviking":
                token = _openviking_login_token(token)
                if not token:
                    self._send_json(401, {"error": "Heslo OpenVikingu nie je správne alebo chýba backendový kľúč."})
                    return
            validation_path = "/api/v1/system/status" if service == "openviking" else "/"
            request = urllib.request.Request(target["proxy_target"] + validation_path, headers={"Authorization": f"Bearer {token}", "X-API-Key": token, "User-Agent": "dash-local-route/1.0"})
            with urllib.request.urlopen(request, timeout=3) as response:
                if response.status >= 400:
                    raise urllib.error.HTTPError(request.full_url, response.status, "upstream", {}, None)
            session_id = secrets.token_urlsafe(24)
            SESSIONS[session_id] = {"service": service, "token": token}
            self._send_json(200, {"redirect": target["url"]}, {"Set-Cookie": f"{SESSION_COOKIE}={session_id}; HttpOnly; SameSite=Strict; Path=/"})
        except (ValueError, KeyError, urllib.error.URLError, TimeoutError, OSError):
            self._send_json(401, {"error": "Služba token neprijala alebo nie je dostupná."})

    def _proxy_get(self, upstream_url: str, token: str) -> None:
        request = urllib.request.Request(upstream_url, headers={"Authorization": f"Bearer {token}", "X-API-Key": token, "User-Agent": "dash-local-route/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read(8 * 1024 * 1024)
                content_type = response.headers.get("Content-Type", "application/octet-stream")
                service = upstream_url.split("/proxy/")[-1] if "/proxy/" in upstream_url else ""
                # Keep HTML assets and form actions behind the authenticated prefix.
                if "text/html" in content_type:
                    body = _rewrite_proxy_assets(body, "openviking" if ":1933" in upstream_url else "orbit", "text/html")
                    text = body.decode("utf-8", errors="replace")
                    prefix = "/proxy/openviking" if ":1933" in upstream_url else "/proxy/orbit"
                    text = re.sub(r"(href|src|action)=(\"|')/(?!/)", rf"\1=\2{prefix}/", text)
                    body = text.encode("utf-8")
                elif "javascript" in content_type or "css" in content_type:
                    body = _rewrite_proxy_assets(body, "openviking" if ":1933" in upstream_url else "orbit", content_type)
                self.send_response(response.status)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                location = response.headers.get("Location")
                if location:
                    self.send_header("Location", location.replace("http://127.0.0.1:7878", "/proxy/orbit").replace("http://127.0.0.1:1933", "/proxy/openviking"))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as error:
            self._send_json(error.code, {"error": "Proxy upstream odpovedal chybou."})
        except (urllib.error.URLError, TimeoutError, OSError):
            self._send_json(502, {"error": "Proxy upstream nie je dostupný."})

    def _proxy_mutation(self, upstream_url: str, token: str) -> None:
        length = min(int(self.headers.get("Content-Length", "0")), 8 * 1024 * 1024)
        data = self.rfile.read(length)
        headers = {"Authorization": f"Bearer {token}", "X-API-Key": token, "User-Agent": "dash-local-route/1.0", "Content-Type": self.headers.get("Content-Type", "application/octet-stream")}
        request = urllib.request.Request(upstream_url, data=data, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read(8 * 1024 * 1024)
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/octet-stream"))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as error:
            self._send_json(error.code, {"error": "Proxy upstream odpovedal chybou."})
        except (urllib.error.URLError, TimeoutError, OSError):
            self._send_json(502, {"error": "Proxy upstream nie je dostupný."})

    def _proxy_authenticated(self) -> tuple[str, str] | None:
        for service, target in proxy_services().items():
            path = _proxy_path(self.path, service)
            if path is None:
                continue
            token = _session_token(self)
            raw_cookie = self.headers.get("Cookie", "")
            session_service = next((SESSIONS.get(item.strip().split("=", 1)[1], {}).get("service") for item in raw_cookie.split(";") if item.strip().startswith(SESSION_COOKIE + "=")), None)
            if not token or session_service != service:
                self._send_json(401, {"error": "Najprv sa prihláste."})
                return None
            return service, target["proxy_target"] + path
        return None

    def do_PUT(self):
        self._handle_proxy_mutation()

    def do_PATCH(self):
        self._handle_proxy_mutation()

    def do_DELETE(self):
        self._handle_proxy_mutation()

    def _handle_proxy_mutation(self) -> None:
        proxied = self._proxy_authenticated()
        if proxied:
            _service, upstream_url = proxied
            self._proxy_mutation(upstream_url, _session_token(self) or "")
        elif proxied is None and self.path.startswith("/proxy/"):
            return
        else:
            self.send_error(404)

    def do_GET(self):
        for service, target in proxy_services().items():
            upstream_path = _proxy_path(self.path, service)
            if upstream_path is not None:
                token = _session_token(self)
                session_service = None
                cookie = self.headers.get("Cookie", "")
                for item in cookie.split(";"):
                    key, _, value = item.strip().partition("=")
                    if key == SESSION_COOKIE:
                        session_service = SESSIONS.get(value, {}).get("service")
                if not token or session_service != service:
                    self._send_json(401, {"error": "Najprv sa prihláste."})
                    return
                self._proxy_get(target["proxy_target"] + upstream_path, token)
                return
        if self.path == "/api/status":
            payload = {"services": discover_services(), "system": read_system_stats(), "watchdog": watchdog_status()}
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/assets/"):
            asset_name = self.path.removeprefix("/assets/")
            if asset_name not in ASSETS:
                self.send_error(404)
                return
            body = (ROOT / "assets" / asset_name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(asset_name)[0] or "application/octet-stream")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/vasky_hero.png":
            body = (ROOT / "vasky_hero.png").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, *_args):
        pass


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"dash-local-route listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
