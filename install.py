#!/usr/bin/env python3
"""Install a source-linked Speedtest Map, or restore the previous speed-test entry."""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import fcntl
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from support import atomic_json, settings, xdg

PLUGIN_ID = "speedtest-map"
ORIGINAL = "omarchy.speedtest"
ROOT = Path(__file__).resolve().parent


class Installer:
    def __init__(self, source=ROOT, config=None, state=None, runner=subprocess.run):
        self.source = Path(source).resolve()
        self.config = Path(config or os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.target = self.config / "omarchy/plugins" / PLUGIN_ID
        self.state_dir = Path(state) if state else xdg("STATE", ".local/state")
        self.record = self.state_dir / "install.json"
        self.runner = runner

    def command(self, args):
        result = self.runner(args, capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip() or f"Command failed: {args[0]}")
        return result.stdout.strip()

    def ipc(self, method, *args):
        return self.command(["omarchy-shell", "shell", method, *args])

    def plugins(self):
        return json.loads(self.ipc("listPlugins"))

    def enabled(self, plugin_id, plugins=None):
        return any(p["id"] == plugin_id and p.get("enabled") for p in (plugins if plugins is not None else self.plugins()))

    def set_enabled(self, plugin_id, enabled):
        reply = self.ipc("setPluginEnabled", plugin_id, "true" if enabled else "false")
        if reply != "ok":
            raise RuntimeError(f"Cannot change {plugin_id}: {reply}")

    def rescan(self, expect=None):
        self.ipc("rescanPlugins")
        for _ in range(40):
            entries = self.plugins()
            exists = any(p["id"] == PLUGIN_ID for p in entries)
            if expect is None or exists == expect:
                return
            time.sleep(.1)
        raise RuntimeError("Omarchy did not discover the plugin change")

    def baseline(self):
        if not self.record.exists():
            return None
        record = json.loads(self.record.read_text())
        if record.get("id") != PLUGIN_ID or record.get("target") != str(self.target):
            raise RuntimeError("Installation record does not match this plugin directory")
        return record

    def check(self, demo=False):
        self.command(["omarchy", "plugin", "validate", str(self.source)])
        for program in ("python3", "qs", "omarchy-shell"):
            if not shutil.which(program):
                raise RuntimeError(f"Missing dependency: {program}")
        entries = self.plugins()
        if not any(p["id"] == ORIGINAL for p in entries):
            raise RuntimeError("Omarchy's standalone speed-test plugin is required (Quattro 4.0.5+)")
        version = self.command(["qs", "--version"])
        match = re.search(r"Quickshell\s+(\d+)\.(\d+)\.(\d+)", version)
        if not match or tuple(map(int, match.groups())) < (0, 3, 1):
            raise RuntimeError("Quickshell 0.3.1+ is required")
        qtpaths = shutil.which("qtpaths6") or shutil.which("qtpaths")
        if not qtpaths and Path("/usr/lib/qt6/bin/qtpaths").is_file():
            qtpaths = "/usr/lib/qt6/bin/qtpaths"
        if not qtpaths:
            raise RuntimeError("Qt6 qtpaths is required to check the Qt version")
        qt_version = self.command([qtpaths, "--qt-version"])
        if tuple(map(int, qt_version.split(".")[:2])) < (6, 9):
            raise RuntimeError("Qt 6.9+ is required")
        settings(require_cli=not demo)
        return entries

    def install(self, demo=False):
        entries = self.check(demo)
        others = [p["id"] for p in entries if p.get("clonedFrom") == ORIGINAL and p["id"] != PLUGIN_ID and p.get("enabled")]
        if others:
            raise RuntimeError("Another speed-test replacement is enabled: " + ", ".join(others))
        record = self.baseline()
        old_link = os.readlink(self.target) if self.target.is_symlink() else None
        checkout = self.target.is_dir() and not self.target.is_symlink() and self.target.resolve() == self.source
        if self.target.exists() or self.target.is_symlink():
            expected = [record.get("source"), record.get("previousSource")] if record else []
            managed_link = record and old_link is not None and old_link in expected
            if not checkout and not managed_link:
                raise RuntimeError(f"Preserving an unmanaged or modified plugin entry: {self.target}")
        source_before = self.enabled(ORIGINAL, entries)
        own_before = self.enabled(PLUGIN_ID, entries)
        new_record = record or {"id": PLUGIN_ID, "target": str(self.target), "originalEnabled": source_before}
        new_record = dict(new_record, source=str(self.source), mode="checkout" if checkout else "link")
        new_record.pop("pending", None)
        new_record.pop("previousSource", None)
        self.target.parent.mkdir(parents=True, exist_ok=True)
        # Persist a recovery record before changing either filesystem or shell state.
        atomic_json(self.record, dict(new_record, pending=True, previousSource=old_link))
        changed_link = False
        try:
            if not checkout:
                if self.target.is_symlink():
                    self.target.unlink()
                self.target.symlink_to(self.source, target_is_directory=True)
                changed_link = True
            self.rescan(expect=True)
            self.set_enabled(PLUGIN_ID, True)
            if not self.enabled(PLUGIN_ID):
                raise RuntimeError("The replacement did not become enabled")
            atomic_json(self.record, new_record)
        except Exception:
            try:
                if self.enabled(PLUGIN_ID):
                    self.set_enabled(PLUGIN_ID, False)
                if changed_link and self.target.is_symlink() and os.readlink(self.target) == str(self.source):
                    self.target.unlink()
                    if old_link is not None:
                        self.target.symlink_to(old_link, target_is_directory=True)
                self.rescan()
                if own_before:
                    self.set_enabled(PLUGIN_ID, True)
                self.set_enabled(ORIGINAL, source_before)
                if record:
                    atomic_json(self.record, record)
                else:
                    self.record.unlink(missing_ok=True)
            except Exception as rollback:
                print(f"Recovery needs attention; installation record retained: {rollback}", file=sys.stderr)
            raise
        print(f"Installed {PLUGIN_ID}. The original network Speed Test button now opens it.")
        if not checkout:
            print(f"Source directory must stay available: {self.source}")

    def uninstall(self, purge=False):
        record = self.baseline()
        present = self.target.exists() or self.target.is_symlink()
        if not present and not record:
            print("Speedtest Map is already removed.")
            if purge:
                self.purge()
            return
        checkout = present and not self.target.is_symlink() and self.target.resolve() == self.source
        expected = [record.get("source"), record.get("previousSource")] if record else []
        owned = record and self.target.is_symlink() and os.readlink(self.target) in expected
        if present and not owned and not checkout:
            raise RuntimeError(f"Preserving an unmanaged or modified plugin entry: {self.target}")
        entries = self.plugins()
        was_enabled = self.enabled(PLUGIN_ID, entries)
        original_before = self.enabled(ORIGINAL, entries)
        other_active = any(p.get("clonedFrom") == ORIGINAL and p["id"] != PLUGIN_ID and p.get("enabled") for p in entries)
        self.ipc("hide", PLUGIN_ID)
        if any(p["id"] == PLUGIN_ID for p in entries):
            self.set_enabled(PLUGIN_ID, False)
        if was_enabled:
            desired = False if other_active else bool(record.get("originalEnabled", True) if record else True)
            self.set_enabled(ORIGINAL, desired)
        elif self.enabled(ORIGINAL) != original_before:
            # Disabling an already-disabled clone may still mutate its source.
            self.set_enabled(ORIGINAL, original_before)
        if owned:
            self.target.unlink()
        elif checkout:
            # Preserve a standard git installation, including untracked user edits.
            backup = self.target.with_name(f".speedtest-map.removed-{time.time_ns()}")
            self.target.rename(backup)
            print(f"Standard installation moved to backup: {backup}")
        self.rescan(expect=False)
        self.record.unlink(missing_ok=True)
        if purge:
            self.purge()
        print("Removed Speedtest Map; restored the speed-test entry without deleting source code.")

    @staticmethod
    def purge():
        for directory in (xdg("CONFIG", ".config"), xdg("CACHE", ".cache")):
            if directory.is_symlink():
                raise RuntimeError(f"Refusing to purge a symlink: {directory}")
            if directory.exists():
                shutil.rmtree(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Read-only dependency and host checks")
    mode.add_argument("--uninstall", action="store_true")
    parser.add_argument("--purge", action="store_true", help="Remove this plugin's config/cache when uninstalling")
    parser.add_argument("--demo", action="store_true", help="Allow installation/checks without Ookla for demo development")
    args = parser.parse_args()
    if args.purge and not args.uninstall:
        parser.error("--purge requires --uninstall")
    installer = Installer()
    try:
        if args.check:
            installer.check(args.demo)
            print("Checks passed. No files or settings changed.")
        else:
            installer.state_dir.mkdir(parents=True, exist_ok=True)
            with (installer.state_dir / "install.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                installer.uninstall(args.purge) if args.uninstall else installer.install(args.demo)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"speedtest-map: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
