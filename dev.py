#!/usr/bin/env python3
"""Open the installed plugin and refresh it when this source tree changes."""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent


def ipc(method, *args):
    result = subprocess.run(["omarchy-shell", "shell", method, *args], check=True,
                            capture_output=True, text=True, timeout=10)
    if result.stdout.strip() in {"unknown", "error"}:
        raise RuntimeError("Plugin unavailable; run 'python install.py' before opening the developer preview")


def snapshot():
    return {str(p): p.stat().st_mtime_ns for p in ROOT.rglob("*")
            if p.is_file() and p.suffix in {".qml", ".js", ".py", ".svg", ".json"}
            and not any(part in {".git", "__pycache__", "test-results", "tests"} for part in p.relative_to(ROOT).parts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Synthetic data only; no network or CLI dependency")
    parser.add_argument("--once", action="store_true", help="Open without watching source changes")
    args = parser.parse_args()
    payload = json.dumps({"demo": args.demo, "connection": "Demo Network"} if args.demo else {})
    ipc("summon", "speedtest-map", payload)
    previous = snapshot()
    try:
        while not args.once:
            time.sleep(.3)
            current = snapshot()
            if current != previous:
                time.sleep(.25)
                previous = snapshot()
                # Mount the current implementation without network traffic so its
                # reloadSource hook can replace the QML engine and its cache.
                ipc("summon", "speedtest-map", json.dumps({"demo":True}))
                for _ in range(40):
                    time.sleep(.1)
                    reply = subprocess.run(["omarchy-shell", "shell", "call", "speedtest-map", "reloadSource", ""],
                                           capture_output=True, text=True, timeout=10)
                    if reply.returncode == 0 and reply.stdout.strip() == "ok":
                        break
                else:
                    raise RuntimeError("Reload hook unavailable; run 'omarchy restart shell' once, then retry")
                # Wait for hard reload and asynchronous discovery before opening.
                time.sleep(.4)
                for _ in range(40):
                    time.sleep(.1)
                    reply = subprocess.run(["omarchy-shell", "shell", "summon", "speedtest-map", payload], capture_output=True, text=True, timeout=10)
                    if reply.returncode == 0 and reply.stdout.strip() == "ok":
                        break
                else:
                    raise RuntimeError("Plugin did not reload; check Omarchy shell logs")
    except KeyboardInterrupt:
        ipc("hide", "speedtest-map")


if __name__ == "__main__":
    main()
