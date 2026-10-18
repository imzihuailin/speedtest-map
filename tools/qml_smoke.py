#!/usr/bin/env python3
"""Optional on-screen QML integration tests. Synthetic data, no network or host config edits."""
# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

FAKE = '''#!/usr/bin/env python3
import json,os,sys,time
from pathlib import Path
if '--version' in sys.argv:
 print('Speedtest by Ookla 1.2.0');sys.exit()
if '--help' in sys.argv:
 print('--progress-update-interval');sys.exit()
Path(os.environ['FIXTURE_PID']).write_text(str(os.getpid()))
scenario=os.environ['FIXTURE_SCENARIO']
if scenario=='license':
 print('EULA license acceptance required',file=sys.stderr);sys.exit(1)
if scenario=='missing': sys.exit(0)
events=[{'type':'testStart','isp':'Fixture Transit','interface':{'externalIp':'203.0.113.10'},'server':{'id':42,'name':'Fixture Server','location':'Example City','country':'Example Country','ip':'198.51.100.20','lat':47.6,'lon':-122.3}}, {'type':'download','download':{'bandwidth':12500000}},{'type':'upload','upload':{'bandwidth':6250000}},{'type':'result','download':{'bandwidth':12500000},'upload':{'bandwidth':6250000}}]
if scenario=='cancel': events=events[:2]
for i,event in enumerate(events):
 data=json.dumps(event)
 sys.stdout.write(data[:8]);sys.stdout.flush();time.sleep(.03)
 sys.stdout.write(data[8:]+('\\n' if i<len(events)-1 else ''));sys.stdout.flush();time.sleep(.1)
if scenario=='cancel': time.sleep(30)
print('Fixture diagnostic on stderr',file=sys.stderr)
'''


def main():
    host = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"
    with tempfile.TemporaryDirectory(prefix="speedtest-map-qml-") as directory:
        base = Path(directory)
        config = base / "config"
        for file in ROOT.iterdir():
            if file.suffix in {".qml", ".js"} or file.name == "support.py":
                shutil.copy2(file, base / file.name)
        for module in ["Commons", "Ui"]:
            (base / module).symlink_to(host / module, target_is_directory=True)
        cli = base / "fixture-cli"
        cli.write_text(FAKE)
        cli.chmod(0o755)
        (config / "speedtest-map").mkdir(parents=True)
        (config / "speedtest-map/config.json").write_text(json.dumps({"cliPath":str(cli),"reducedMotion":True}))
        for scenario in ["success", "license", "missing", "cancel"]:
            condition = {
                "success": 'panel.state.result && panel.state.download===100 && panel.state.upload===50 && !panel.running && panel.error===""',
                "license": '!panel.running && panel.error.indexOf("terms")>=0',
                "missing": '!panel.running && panel.error.indexOf("complete result")>=0',
                "cancel": '!panel.opened && !panel.running',
            }[scenario]
            (base / "shell.qml").write_text('''import QtQuick
import Quickshell
import "." as Plugin
ShellRoot {
 Plugin.Panel { id:panel; Component.onCompleted:open('{"connection":"Fixture Network"}') }
 Timer { interval:650;running:''' + str(scenario == "cancel").lower() + ''';onTriggered:panel.close() }
 Timer { interval:2400;running:true;onTriggered: {
  console.log((''' + condition + ''') ? "FIXTURE_PASS" : "FIXTURE_FAIL: "+panel.error);
  Qt.quit();
 } }
}
''')
            pidfile = base / "child.pid"
            pidfile.unlink(missing_ok=True)
            env = dict(os.environ, XDG_CONFIG_HOME=str(config), XDG_CACHE_HOME=str(base / "cache"),
                       XDG_STATE_HOME=str(base / "state"), FIXTURE_PID=str(pidfile), FIXTURE_SCENARIO=scenario)
            result = subprocess.run(["quickshell", "-p", str(base), "--no-color"], env=env,
                                    capture_output=True, text=True, timeout=12)
            log = result.stdout + result.stderr
            if result.returncode or "FIXTURE_PASS" not in log or "FIXTURE_FAIL" in log:
                raise RuntimeError(f"QML {scenario} failed:\n{log}")
            if pidfile.exists():
                try:
                    os.kill(int(pidfile.read_text()), 0)
                except ProcessLookupError:
                    pass
                else:
                    raise RuntimeError(f"QML {scenario} left its CLI process alive")
            print(f"QML {scenario}: passed; no CLI child left alive")


if __name__ == "__main__":
    main()
