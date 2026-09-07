#!/usr/bin/env python3
"""Small dependency-free local dashboard server."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
ASSETS = {
    "logo-cpu.svg", "logo-nvidia.svg", "logo-amd.svg", "logo-ram.svg",
    "logo-orbit.svg", "logo-hermes.svg", "logo-openwebui.svg", "logo-openviking.svg",
    'logo-litellm.svg', 'logo-searxng.svg', 'logo-euro.svg', 'logo-portainer.svg',
}
HOST = os.environ.get("DASH_HOST", "0.0.0.0")
PORT = int(os.environ.get("DASH_PORT", "8090"))
SERVICES = [
    {"name": "Orbit", "description": "Lokálny orchestrátor", "url": "http://127.0.0.1:7878/", "port": 7878, "scheme": "http"},
    {"name": "Hermes Agent", "description": "Lokálne AI rozhranie", "url": "http://127.0.0.1:9119/", "port": 9119, "scheme": "http"},
    {"name": "Open WebUI", "description": "Webové rozhranie pre AI", "url": "http://127.0.0.1:3080/", "port": 3080, "scheme": "http"},
    {"name": "OpenViking Studio", "description": "Lokálne znalostné úložisko", "url": "http://127.0.0.1:1933/studio/", "port": 1933, "scheme": "http"},
    {"name": "Firecrawl API", "description": "Lokálne API · nemá samostatné GUI", "url": "http://192.168.16.42:3002/", "port": 3002, "scheme": "http", "kind": "api"},
    {"name": "Qwen Prisma", "description": "LiteLLM model · vLLM na 192.168.16.243", "url": "http://192.168.16.243:8001/v1/models", "port": 8001, "scheme": "http", "kind": "api"},
    {"name": "Nemo Rugent", "description": "LiteLLM model · llama.cpp na tomto PC", "url": "http://127.0.0.1:8089/v1/models", "port": 8089, "scheme": "http", "kind": "api"},
    {"name": "Multilingual E5 Small", "description": "LiteLLM embedding model · llama.cpp", "url": "http://127.0.0.1:8081/v1/models", "port": 8081, "scheme": "http", "kind": "api"},
    {"name": "BGE Reranker v2 M3", "description": "LiteLLM reranking model · llama.cpp", "url": "http://127.0.0.1:8082/v1/models", "port": 8082, "scheme": "http", "kind": "api"},
    {"name": "Hermes Gateway API", "description": "Health a stav Hermes gateway", "url": "http://192.168.16.42:9119/api/health", "check_url": "http://127.0.0.1:9119/api/health", "port": 9119, "scheme": "http", "kind": "api"},
    {"name": "LiteLLM OpenAI API", "description": "OpenAI-kompatibilné API proxy", "url": "http://192.168.16.42:4000/v1", "check_url": "http://127.0.0.1:4000/ui/", "port": 4000, "scheme": "http", "kind": "api"},
    {"name": "LiteLLM", "description": "Dashboard pre lokálny LLM proxy", "url": "http://192.168.16.42:4000/ui/", "check_url": "http://127.0.0.1:4000/ui/", "port": 4000, "scheme": "http"},
    {"name": "SearXNG", "description": "Lokálny metavyhľadávač", "url": "http://192.168.16.42:8888/", "check_url": "http://127.0.0.1:8888/", "port": 8888, "scheme": "http"},
    {"name": "Templator Peppol", "description": "Vizualizácia elektronických faktúr", "url": "http://192.168.16.42:10001/", "check_url": "http://127.0.0.1:10001/", "port": 10001, "scheme": "http"},
    {"name": "Portainer", "description": "Správa Docker kontajnerov · vyžaduje reštart", "url": "https://192.168.16.42:9443/", "check_url": "https://127.0.0.1:9443/", "port": 9443, "scheme": "https"},
    {"name": "Prometheus", "description": "Monitorovanie a časové rady", "url": "http://192.168.16.42:9090", "port": 9090, "scheme": "http"},
    {"name": "cAdvisor", "description": "Metriky Docker kontajnerov · metrics endpoint", "url": "http://192.168.16.42:8080/metrics", "port": 8080, "scheme": "http", "kind": "api"},
    {"name": "Grafana · Hetzner Cloud", "description": "Metriky Hetzner Cloud servera", "url": "http://192.168.16.164:3000/d/ad7ghz7/my-htzner-dash?from=now-6h&to=now&timezone=browser&var-filter0=&dtab=New-tab", "port": 3000, "scheme": "http"},
]


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


def read_system_stats() -> dict:
    mem = _meminfo()
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", mem.get("MemFree", 0))
    used = max(total - available, 0)
    return {"memory": {"total": total, "used": used, "available": available, "used_percent": round(100 * used / total, 1) if total else 0}, "cpu_percent": _cpu_percent(), "cpu_temperature_c": _read_cpu_temperature(), "gpu": read_gpu_stats(), "processes": _processes(), "updated_at": int(time.time())}


def discover_services() -> list[dict]:
    services = []
    for item in SERVICES:
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


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            payload = {"services": discover_services(), "system": read_system_stats()}
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
