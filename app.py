#!/usr/bin/env python3
"""Small dependency-free local dashboard server."""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
HOST = os.environ.get("DASH_HOST", "0.0.0.0")
PORT = int(os.environ.get("DASH_PORT", "8090"))
SERVICES = [
    {"name": "Orbit", "description": "Lokálny orchestrátor", "url": "http://127.0.0.1:7878/", "port": 7878, "scheme": "http"},
    {"name": "Hermes Agent", "description": "Lokálne AI rozhranie", "url": "http://127.0.0.1:9119/", "port": 9119, "scheme": "http"},
    {"name": "Open WebUI", "description": "Webové rozhranie pre AI", "url": "http://127.0.0.1:3080/", "port": 3080, "scheme": "http"},
    {"name": "OpenViking Studio", "description": "Lokálne znalostné úložisko", "url": "http://127.0.0.1:1933/studio/", "port": 1933, "scheme": "http"},
    {"name": "Firecrawl API", "description": "Lokálne API pre webový obsah", "url": "http://127.0.0.1:3002/", "port": 3002, "scheme": "http"},
    {"name": "API služba", "description": "Lokálna API dokumentácia", "url": "http://127.0.0.1:4000/", "port": 4000, "scheme": "http"},
    {"name": "Notebook", "description": "Lokálne notebookové rozhranie", "url": "http://127.0.0.1:8888/", "port": 8888, "scheme": "http"},
    {"name": "Bezpečná lokálna služba", "description": "HTTPS služba na tomto PC", "url": "https://127.0.0.1:9443/", "port": 9443, "scheme": "https"},
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
    return {"memory": {"total": total, "used": used, "available": available, "used_percent": round(100 * used / total, 1) if total else 0}, "cpu_percent": _cpu_percent(), "processes": _processes(), "updated_at": int(time.time())}


def discover_services() -> list[dict]:
    services = []
    for item in SERVICES:
        entry = dict(item)
        request = urllib.request.Request(item["url"], headers={"User-Agent": "dash-local-route/1.0"})
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
        if self.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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
