# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from install import Installer, ORIGINAL, PLUGIN_ID


class FakeShell:
    def __init__(self, target):
        self.target = target
        self.entries = {ORIGINAL: {"id": ORIGINAL, "enabled": True}}
        self.fail_enable = False

    def __call__(self, args, **kwargs):
        if args[:3] == ["omarchy", "plugin", "validate"]:
            return subprocess.CompletedProcess(args, 0, "Valid", "")
        method, *params = args[2:]
        if method == "listPlugins":
            result = json.dumps(list(self.entries.values()))
        elif method == "rescanPlugins":
            if self.target.exists():
                self.entries.setdefault(PLUGIN_ID, {"id": PLUGIN_ID, "enabled": False, "clonedFrom": ORIGINAL})
            else:
                self.entries.pop(PLUGIN_ID, None)
            result = ""
        elif method == "setPluginEnabled":
            key, enabled = params
            if key == PLUGIN_ID and enabled == "true" and self.fail_enable:
                self.fail_enable = False
                return subprocess.CompletedProcess(args, 1, "", "Simulated activation failure")
            self.entries[key]["enabled"] = enabled == "true"
            if key == PLUGIN_ID:
                self.entries[ORIGINAL]["enabled"] = enabled != "true"
            result = "ok"
        else:
            result = ""
        return subprocess.CompletedProcess(args, 0, result, "")


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.source = base / "source"
        self.source.mkdir()
        (self.source / "manifest.json").write_text('{"id":"speedtest-map"}')
        self.installer = Installer(self.source, base / "config", base / "state")
        self.host = FakeShell(self.installer.target)
        self.installer.runner = self.host
        self.installer.check = lambda demo: self.host.entries.values()

    def test_install_repeat_uninstall_preserves_source(self):
        self.installer.install()
        original_record = json.loads(self.installer.record.read_text())
        self.installer.install()
        self.assertEqual(original_record, json.loads(self.installer.record.read_text()))
        self.assertTrue(self.installer.target.is_symlink())
        self.installer.uninstall()
        self.installer.uninstall()
        self.assertTrue(self.source.exists())
        self.assertFalse(self.installer.target.is_symlink())
        self.assertTrue(self.host.entries[ORIGINAL]["enabled"])

    def test_moved_source_can_update_broken_link(self):
        self.installer.install()
        moved = self.source.with_name("moved source")
        self.source.rename(moved)
        self.installer.source = moved
        self.installer.install()
        self.assertEqual(self.installer.target.resolve(), moved)
        self.installer.uninstall()
        self.assertTrue(moved.exists())

    def test_foreign_directory_and_modified_link_preserved(self):
        self.installer.target.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError, "unmanaged"):
            self.installer.install()
        self.assertTrue(self.installer.target.is_dir())
        self.installer.target.rmdir()
        self.installer.install()
        self.installer.target.unlink()
        foreign = self.source.with_name("foreign")
        foreign.mkdir()
        self.installer.target.symlink_to(foreign)
        with self.assertRaisesRegex(RuntimeError, "modified"):
            self.installer.uninstall()
        self.assertEqual(self.installer.target.resolve(), foreign)

    def test_activation_failure_rolls_back(self):
        self.host.fail_enable = True
        with self.assertRaisesRegex(RuntimeError, "activation failure"):
            self.installer.install()
        self.assertFalse(self.installer.target.is_symlink())
        self.assertFalse(self.installer.record.exists())
        self.assertTrue(self.host.entries[ORIGINAL]["enabled"])

    def test_original_disabled_stays_disabled(self):
        self.host.entries[ORIGINAL]["enabled"] = False
        self.installer.install()
        self.installer.uninstall()
        self.assertFalse(self.host.entries[ORIGINAL]["enabled"])

    def test_other_replacement_conflict(self):
        self.host.entries["other"] = {"id":"other", "enabled":True, "clonedFrom":ORIGINAL}
        with self.assertRaisesRegex(RuntimeError,"Another"):
            self.installer.install()
        self.assertFalse(self.installer.target.exists())

    def test_later_replacement_survives_uninstall(self):
        self.installer.install()
        self.host.entries["other"] = {"id":"other", "enabled":True, "clonedFrom":ORIGINAL}
        self.installer.uninstall()
        self.assertTrue(self.host.entries["other"]["enabled"])
        self.assertFalse(self.host.entries[ORIGINAL]["enabled"])

    def test_standard_checkout_is_backed_up_not_deleted(self):
        self.installer.target.parent.mkdir(parents=True)
        self.source.rename(self.installer.target)
        self.installer.source = self.installer.target
        self.installer.rescan(True)
        self.installer.set_enabled(PLUGIN_ID, True)
        self.installer.uninstall()
        backups = list(self.installer.target.parent.glob(".speedtest-map.removed-*"))
        self.assertEqual(len(backups), 1)
        self.assertTrue((backups[0] / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
