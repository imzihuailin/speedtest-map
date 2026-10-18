#!/usr/bin/env python3
"""Read settings and validate the external Ookla CLI. Never starts a test or accepts terms."""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def xdg(kind, fallback):
    return Path(os.environ.get(f"XDG_{kind}_HOME", Path.home() / fallback)) / "speedtest-map"


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def settings(require_cli=True):
    path = xdg("CONFIG", ".config") / "config.json"
    value = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(value, dict):
        raise ValueError("config.json must contain an object")
    reduced = value.get("reducedMotion", False)
    if not isinstance(reduced, bool):
        raise ValueError("reducedMotion must be true or false")
    configured = value.get("cliPath", "speedtest")
    if not isinstance(configured, str) or not configured:
        raise ValueError("cliPath must be a non-empty executable path")
    binary = shutil.which(os.path.expanduser(configured))
    # Desktop PATH on Omarchy can omit ~/.local/bin.
    if not binary and configured == "speedtest":
        candidate = Path.home() / ".local/bin/speedtest"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            binary = str(candidate)
    if require_cli:
        if not binary:
            raise RuntimeError("Ookla Speedtest CLI is missing. See README for installation and first-run terms.")
        version = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=3)
        help_text = subprocess.run([binary, "--help"], capture_output=True, text=True, timeout=3)
        if "Ookla" not in version.stdout + version.stderr or "--progress-update-interval" not in help_text.stdout:
            raise RuntimeError("Use the official Ookla Speedtest CLI 1.2.0 or newer, not Python speedtest-cli.")
    return {"cliPath": binary or configured, "reducedMotion": reduced}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["settings", "demo-settings"])
    args = parser.parse_args()
    try:
        result = settings(args.action != "demo-settings")
        print(json.dumps(result))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
