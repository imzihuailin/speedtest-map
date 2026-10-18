#!/usr/bin/env python3
"""Render a shareable, synthetic preview without capturing the user's desktop."""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "preview.png")
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="speedtest-map-preview-") as directory:
        base = Path(directory)
        host = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"
        for file in ROOT.iterdir():
            if file.suffix in {".qml", ".js"} or file.name == "support.py":
                shutil.copy2(file, base / file.name)
        for module in ["Commons", "Ui"]:
            (base / module).symlink_to(host / module, target_is_directory=True)
        (base / "shell.qml").write_text('''import QtQuick
import Quickshell
import "." as Plugin
ShellRoot {
 Plugin.Panel {
  id:panel
  Component.onCompleted: {
   previewWindow.captureItem.children[0].color="#111318";
   open('{"demo":true,"connection":"Demo Network"}');
  }
 }
 Timer { interval:11000;running:true;onTriggered: {
  panel.previewWindow.captureItem.grabToImage(function(image) {
   console.log(image.saveToFile(''' + json.dumps(str(output)) + ''') ? "PREVIEW_SAVED" : "PREVIEW_FAILED");
  });
 } }
 Timer { interval:13500;running:true;onTriggered:Qt.quit() }
}
''')
        env = dict(os.environ, XDG_CONFIG_HOME=str(base / "config"),
                   XDG_CACHE_HOME=str(base / "cache"), XDG_STATE_HOME=str(base / "state"))
        result = subprocess.run(["quickshell", "-p", str(base), "--no-color"], capture_output=True,
                                text=True, timeout=20, env=env)
        if result.returncode or "PREVIEW_SAVED" not in result.stdout + result.stderr:
            raise RuntimeError(result.stdout + result.stderr)
    print(f"Synthetic preview saved: {output}")


if __name__ == "__main__":
    main()
