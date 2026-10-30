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


## 🤝 Contributing

Contributions are welcome! Whether it's bug fixes, new features, documentation improvements, or testing — every contribution helps.

### Ways to Contribute

| Type | Description |
|------|-------------|
| 🐛 **Bug Reports** | Found an issue? Open a GitHub Issue with steps to reproduce, expected vs actual behavior, and environment details |
| ✨ **Feature Requests** | Have an idea? Open a GitHub Issue with the "enhancement" label describing the use case |
| 📝 **Documentation** | Fix typos, clarify setup steps, add examples — PRs to `README.md` or `/docs` are always appreciated |
| 🔧 **Code** | Bug fixes, new features, refactoring, tests |
| 🧪 **Testing** | Test on different hardware/OS, report compatibility |
| 💡 **Ideas & Feedback** | Discussions, RFCs, architecture suggestions |

### Quick Start for Contributors

```bash
# 1. Fork the repository
# 2. Clone your fork
git clone https://github.com/YOUR-USERNAME/REPO-NAME.git
cd REPO-NAME

# 3. Create a feature branch
git checkout -b feature/your-feature-name

# 4. Make changes, test locally
# (see README for local development setup)

# 5. Commit with conventional commits
git commit -m "feat: add amazing feature"

# 6. Push and open a Pull Request
git push origin feature/your-feature-name
```

### Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat:     new feature
fix:      bug fix
docs:     documentation only
style:    formatting, no code change
refactor: code restructuring
test:     adding tests
chore:    maintenance, deps, build
```

Examples:
- `feat: add voice selection UI for TTS`
- `fix: handle GPU OOM in model offloading`
- `docs: clarify Docker setup for ARM64`

### Pull Request Guidelines

- ✅ **One feature/fix per PR** — keeps reviews focused
- ✅ **Tests pass** — run local tests before pushing
- ✅ **Update docs** — if behavior changes, update README/comments
- ✅ **No credentials** — never commit `.env`, keys, tokens
- ✅ **Small, focused commits** — easier to review

### Development Setup

See the **Installation** section above for local setup. Most projects use:

```bash
# Python projects
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# or pip install -e ".[dev]" for dev dependencies

# .NET projects
dotnet restore
dotnet build

# Docker projects
docker compose up -d --build
```

### Code Style

| Language | Formatter | Linter |
|----------|-----------|--------|
| Python | `black` | `ruff` |
| C# | `dotnet format` | Built-in |
| JavaScript/TypeScript | `prettier` | `eslint` |
| Blazor | `dotnet format` | Built-in |

Run formatters before committing:
```bash
# Python
black . && ruff check .

# .NET
dotnet format

# JS/TS (if applicable)
prettier --write .
```

### Reporting Security Issues

**Do not open public issues for security vulnerabilities.** Email directly or use GitHub's private vulnerability reporting.

### Community

- 💬 **Discussions**: Use GitHub Discussions for questions, ideas, RFCs
- 🐛 **Issues**: Bug reports, feature requests
- 📧 **Contact**: Open an issue for maintainer contact

### Recognition

Contributors are recognized in:
- GitHub Contributors graph
- Release notes (for significant contributions)
- `AUTHORS.md` or `CONTRIBUTORS.md` (if maintained)

---

**Thank you for contributing!** 🎉

---

## 📄 License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

MIT License allows:
- ✅ Commercial use
- ✅ Modification
- ✅ Distribution
- ✅ Private use
- ❌ No liability
- ❌ No warranty

---

## ⭐ Star History

If you find this project useful, please consider giving it a star! It helps with visibility and motivation.

## License

MIT
