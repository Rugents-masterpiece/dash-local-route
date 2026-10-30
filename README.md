# dash-local-route

Local dashboard for monitoring host resources (CPU, RAM, GPU VRAM, temperatures), Docker services, and the Laurincov-pes deterministic watchdog. Written in Python with a dependency-free HTTP server and a vanilla JS frontend.

## Features

- **System metrics**: CPU usage, temperature, NVIDIA GPU utilization + VRAM, DDR4 RAM, swap
- **Service health**: Checks web services and API endpoints via HTTP/HTTPS/MySQL
- **Watchdog UI**: Displays Laurincov-pes watchdog report (ONLINE/OFFLINE/PAUSED endpoints)
- **Service control**: Start/stop managed services via loopback controller (dash-control.service)
- **Auto-refresh**: Updates every 10 seconds
- **No external dependencies**: Pure Python stdlib + vanilla JS/CSS

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  dash-local-route (Python HTTP server on :8090)            │
│  ├── /api/status  → JSON with system + service + watchdog  │
│  ├── /index.html  → Frontend (served statically)           │
│  └── /assets/*    → SVG logos                              │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   ┌──────────┐       ┌──────────────┐     ┌──────────────┐
   │  System  │       │  Services    │     │  Watchdog    │
   │  (ps,    │       │  (HTTP/      │     │  (JSON file  │
   │  nvidia- │       │   MySQL)     │     │   from       │
   │  smi,    │       │              │     │   laurincov- │
   │  /proc)  │       │              │     │   pes)       │
   └──────────┘       └──────────────┘     └──────────────┘
```

## Prerequisites

- Python 3.10+
- `nvidia-smi` (for GPU metrics)
- `docker` (for container stats via `docker stats`)
- `systemd` (for service control via `dash-control.service` on :18002)

## Installation

```bash
# Clone
git clone https://github.com/Rugents-masterpiece/dash-local-route.git
cd dash-local-route

# Run directly (no venv needed)
python3 app.py

# Or with Docker
docker compose up -d --build
```

Access at `http://<host>:10001` (via gateway) or `http://<host>:8090` (direct).

## Configuration

Environment variables:
- `DASH_HOST` (default: `0.0.0.0`)
- `DASH_PORT` (default: `8090`)
- `SERVICE_REGISTRY` (default: `./services.json`)
- `WATCHDOG_STATE_FILE` (default: `/home/rugent/.hermes/state/service-watchdog.json`)
- `WATCHDOG_OUTPUT_DIR` (default: `/home/rugent/.hermes/cron/output/...`)
- `LAURINCOV_REPORT_FILE` (default: `/home/rugent/workspace/laurincov-pes/watchdog-report.json`)
- `SERVICE_CONTROL_URL` (default: `http://127.0.0.1:18002`)
- `SERVICE_CONTROL_TOKEN_FILE` (default: `/run/dash-local-route/control.env`)

## Service Registry

Edit `services.json` to define monitored services:

```json
{
  "services": [
    {
      "name": "OpenViking",
      "url": "http://127.0.0.1:1933/health",
      "check_url": "http://127.0.0.1:1933/health",
      "scheme": "http",
      "port": 1933,
      "managed": true,
      "kind": "web",
      "description": "OpenViking Studio"
    }
  ]
}
```

Fields: `name`, `url`, `check_url`, `scheme` (http/https/mysql), `port`, `managed`, `kind` (web/api), `description`, `paused`, `protected`, `proxy_target`.

## Security

- Service control requires token from `/run/dash-local-route/control.env`
- Protected services (Orbit, OpenViking) require password login
- Runs on loopback only by default

## License

MIT
