#!/usr/bin/env python3
"""Manage dash-local-route's external service registry atomically."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
REGISTRY = Path(os.environ.get("SERVICE_REGISTRY", ROOT / "services.json"))


def read() -> dict:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(payload.get("services"), list):
        raise SystemExit("services.json: services must be a list")
    return payload


def write(payload: dict) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="services.", suffix=".json", dir=REGISTRY.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, REGISTRY)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Update the dash-local-route service registry")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    add = sub.add_parser("add")
    add.add_argument("name")
    add.add_argument("url")
    add.add_argument("--description", default="")
    add.add_argument("--check-url")
    add.add_argument("--kind", choices=("web", "api"), default="web")
    add.add_argument("--managed", action=argparse.BooleanOptionalAction, default=True)
    add.add_argument("--source")
    add.add_argument("--restart-command")
    remove = sub.add_parser("remove")
    remove.add_argument("name")
    pause = sub.add_parser("maintenance")
    pause.add_argument("name")
    pause.add_argument("state", choices=("on", "off"))
    args = parser.parse_args()
    payload = read()
    services = payload["services"]

    if args.command == "list":
        for item in services:
            print(f"{item['name']}\tmanaged={item.get('managed', False)}\tmaintenance={item.get('maintenance', False)}\t{item['url']}")
        return

    if args.command == "remove":
        before = len(services)
        payload["services"] = [item for item in services if item.get("name") != args.name]
        if len(payload["services"]) == before:
            raise SystemExit(f"service not found: {args.name}")
    elif args.command == "maintenance":
        item = next((item for item in services if item.get("name") == args.name), None)
        if item is None:
            raise SystemExit(f"service not found: {args.name}")
        item["maintenance"] = args.state == "on"
    elif args.command == "add":
        if any(item.get("name") == args.name for item in services):
            raise SystemExit(f"service already exists: {args.name}")
        parsed = urlsplit(args.url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise SystemExit("url must be an absolute http(s) URL")
        entry = {
            "name": args.name, "description": args.description, "url": args.url,
            "check_url": args.check_url or args.url, "port": parsed.port or (443 if parsed.scheme == "https" else 80),
            "scheme": parsed.scheme, "managed": args.managed, "kind": args.kind,
        }
        if args.source:
            entry["source"] = args.source
        if args.restart_command:
            entry["restart_command"] = args.restart_command
        services.append(entry)
    write(payload)
    print(f"updated {REGISTRY}: {len(payload['services'])} services")


if __name__ == "__main__":
    main()
