// SPDX-License-Identifier: GPL-3.0-only
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import "Model.js" as Model

Item {
    id: root
    property var shell: null
    property var manifest: null
    readonly property alias previewWindow: overlay
    property bool opened: false
    property bool demo: false
    property bool reducedMotion: false
    property bool running: false
    property string connectionName: ""
    property var state: Model.initial()
    property string error: ""
    property int generation: 0
    property int step: 0
    property bool exited: false
    property bool stdoutDone: false
    property bool stderrDone: false
    property bool testActive: false
    property int exitCode: 0
    property int stdoutOffset: 0
    property int stderrOffset: 0
    property string stderrPlain: ""
    readonly property string supportPath: decodeURIComponent(Qt.resolvedUrl("support.py").toString().replace(/^file:\/\//, ""))

    function open(payloadJson) {
        var payload = {};
        try { payload = JSON.parse(payloadJson || "{}"); } catch (e) {}
        demo = payload.demo === true;
        connectionName = payload.connection ? String(payload.connection) : "";
        opened = true;
        if (!connectionName) statusProc.running = true;
        runSpeedTest();
    }
    function close() {
        opened = false; running = false; generation++;
        deadline.stop(); demoTimer.stop();
        settingsProc.running = false; testProc.running = false;
        statusProc.running = false;
    }
    Component.onDestruction: close()
    function dismiss() {
        close();
        if (shell && typeof shell.hide === "function") shell.hide((manifest && manifest.id) || "speedtest-map");
    }
    function status() {
        // Useful for local checks without logging public IPs or the CLI's raw output.
        return JSON.stringify({opened:opened,running:running,phase:state.phase,result:state.result,
            download:state.download,upload:state.upload,isp:state.isp,server:state.server.name || "",
            error:error});
    }
    function reloadSource() {
        close();
        // Omarchy's manifest rescan does not invalidate cached external QML.
        // A hard QML reload is required for source-linked development changes.
        Qt.callLater(function() { Quickshell.reload(true); });
    }
    function runSpeedTest() {
        if (!opened || running || testActive || testProc.running || settingsProc.running) return;
        generation++; state = Model.initial(); error = ""; stderrPlain = "";
        stdoutOffset = 0; stderrOffset = 0; exited = false; stdoutDone = false; stderrDone = false;
        running = true; deadline.start();
        settingsProc.token = generation;
        settingsProc.command = ["python3", supportPath, demo ? "demo-settings" : "settings"];
        settingsProc.running = true;
    }
    function fail(message) {
        error = message; running = false; deadline.stop(); demoTimer.stop();
        testProc.running = false;
    }
    function eventReceived(event) {
        if (!opened || !running) return;
        state = Model.reduce(state, event);
        if (state.error) { fail(state.error); return; }
    }
    function parseStream(text, isError, finalChunk) {
        if (!opened || !running) return;
        var offset = isError ? stderrOffset : stdoutOffset;
        if (text.length < offset) offset = 0;
        var end = finalChunk ? text.length : text.lastIndexOf("\n") + 1;
        if (end <= offset) return;
        var lines = text.slice(offset,end).split(/\r?\n/);
        if (isError) stderrOffset = end; else stdoutOffset = end;
        for (var i=0;i<lines.length;i++) {
            var line = lines[i].trim();
            if (!line) continue;
            try { eventReceived(JSON.parse(line)); }
            catch (e) { if (isError) stderrPlain = (stderrPlain + "\n" + line).slice(-3000); }
        }
    }
    function finish() {
        if (!Model.canFinish(exited,stdoutDone,stderrDone)) return;
        testActive = false;
        if (!opened || !running) return;
        if (exitCode !== 0 || !state.result) {
            var detail = stderrPlain.trim();
            if (/license|gdpr|eula/i.test(detail)) detail = "Open a terminal and run Ookla speedtest once to review its terms, then try again.";
            fail(detail || "Speedtest exited without a complete result.");
        } else { running = false; deadline.stop(); }
    }
    Process {
        id: settingsProc
        property int token: -1
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                if (!root.opened || !root.running || settingsProc.token !== root.generation) return;
                try {
                    var config = JSON.parse(text);
                    if (config.error) { root.fail(config.error); return; }
                    root.reducedMotion = config.reducedMotion;
                    if (root.demo) { root.step=0; demoTimer.start(); return; }
                    testProc.command = [config.cliPath,"--format=json","--progress=yes","--progress-update-interval=250"];
                    root.testActive = true;
                    testProc.running = true;
                } catch(e) { root.fail("Could not read settings: " + e); }
            }
        }
    }
    Process {
        id: testProc
        stdout: StdioCollector {
            waitForEnd: false
            onTextChanged: root.parseStream(text,false,false)
            onStreamFinished: { root.parseStream(text,false,true); root.stdoutDone=true; root.finish(); }
        }
        stderr: StdioCollector {
            waitForEnd: false
            onTextChanged: root.parseStream(text,true,false)
            onStreamFinished: { root.parseStream(text,true,true); root.stderrDone=true; root.finish(); }
        }
        onExited: function(code) { root.exited=true; root.exitCode=code; root.finish(); }
    }
    Process {
        id: statusProc
        command:["omarchy-network-status"]
        stdout:StdioCollector {
            waitForEnd:true
            onStreamFinished: {
                if (!root.opened) return;
                var fields=String(text).trim().split("\t");
                root.connectionName=fields[0]==="wifi" ? (fields[1] || "Wi-Fi") : fields[0]==="ethernet" ? "Ethernet" : "Network";
            }
        }
    }
    Timer { id:deadline; interval:120000; onTriggered:root.fail("Speedtest timed out after 120 seconds.") }
    Timer {
        id:demoTimer; interval:400; repeat:true
        onTriggered: {
            root.eventReceived(Model.fixture(root.step));
            if (root.step>=36) { stop(); root.running=false; deadline.stop(); }
            root.step++;
        }
    }
    OoklaOverlay {
        id: overlay
        fontFamily:Style.font.family
        layerNamespace:"speedtest-map"
        title:root.connectionName
        leftLabel:"DOWNLOAD"; rightLabel:"UPLOAD"
        runAgainTooltip:"Measure again via Speedtest by Ookla"
        running:root.running
        leftValue:root.state.download; rightValue:root.state.upload
        leftLive:root.running && root.state.phase==="download"
        rightLive:root.running && root.state.phase==="upload"
        error:root.error; open:root.opened
        reducedMotion:root.reducedMotion
        statusText:root.error ? "" : root.running ? ({prepare:"Finding a server",ping:"Measuring latency",download:"Downloading",upload:"Uploading"}[root.state.phase] || "Finishing") : "Complete"
        exitProvider:root.state.isp || "—"
        serverProvider:root.state.server.name || "—"
        serverLocation:[root.state.server.location,root.state.server.country].filter(function(v){return !!v;}).join(", ") || "—"
        serverId:root.state.server.id ? "#" + root.state.server.id : ""
        demoMode:root.demo
        onCloseRequested:root.dismiss()
        onRunAgainRequested:root.runSpeedTest()
    }
}
