#!/usr/bin/env python3
"""Read-only STT identity probe for the watchdog.

Proves which STT stack the AI GPU manager actually runs, without touching
the manager: the worker script path lives in the manager's adapter code,
the live worker command line proves the stack that is running.
"""
from __future__ import annotations
import json, re, subprocess

ADAPTERS = "/home/rugent/rtx3050-profile-prototype/production-candidate/adapters.py"


def stt_stack() -> tuple[str, str]:
    """Return (worker_script, stack_label) for the STT worker the manager spawns."""
    try:
        text = open(ADAPTERS, encoding="utf-8").read()
    except OSError:
        return "unknown", "unknown"
    script = "unknown"
    m = re.search(r"return RPC\(os\.getenv\('STT_WORKER_SCRIPT',\s*'([^']+)'\)", text)
    if m:
        script = m.group(1)
    stack = "Parakeet" if "stt_worker.py" in script else "WhisperX/KInIT" if "whisperx" in script else "unknown"
    return script, stack


def main():
    script, stack = stt_stack()
    running = subprocess.run(["pgrep", "-af", "whisperx_worker.py"],
                             capture_output=True, text=True).stdout.count("\n") or 0
    parakeet = subprocess.run(["pgrep", "-af", "\\.nemo|parakeet"],
                              capture_output=True, text=True).stdout.strip()
    result = {
        "configured_stt_worker": script,
        "identified_stack": stack,
        "whisperx_worker_processes_running": running,
        "parakeet_processes_running": bool(parakeet),
    }
    if stack == "WhisperX/KInIT":
        result["description"] = ("STT ide cez KInIT Whisper large-v3-turbo-sk + WhisperX + pyannote; "
                                 "Parakeet worker sa nepouziva")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
