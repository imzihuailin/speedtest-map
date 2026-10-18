// SPDX-License-Identifier: GPL-3.0-only
// Pure event reduction, shared by QML and the fixture tests.
function initial() {
    return {phase: "prepare", download: 0, upload: 0, isp: "",
        server: {}, result: false, error: ""};
}
function mbps(value) {
    return typeof value === "number" && isFinite(value) && value >= 0 ? value * 8 / 1000000 : null;
}
function reduce(state, event) {
    var next = Object.assign({}, state);
    if (!event || typeof event !== "object") return next;
    if (event.isp) next.isp = String(event.isp);
    if (event.server) next.server = Object.assign({}, next.server, event.server);
    var type = event.type;
    if (state.result && type !== "result") return next;
    if (type === "ping") next.phase = "ping";
    if (type === "download" || type === "upload") {
        var data = event[type] || {};
        var rate = mbps(data.bandwidth);
        if (rate !== null) {
            next.phase = type;
            next[type] = rate;
        }
    }
    if (type === "result") {
        var down = mbps((event.download || {}).bandwidth);
        var up = mbps((event.upload || {}).bandwidth);
        if (down === null || up === null) next.error = "Speedtest returned an incomplete result.";
        else { next.download = down; next.upload = up; next.result = true; next.phase = "complete"; }
    }
    if (event.error || (type === "log" && event.level === "error"))
        next.error = String(event.error || event.message || "Speedtest failed.");
    return next;
}
function canFinish(exited, stdoutDone, stderrDone) { return exited && stdoutDone && stderrDone; }
function fixture(step) {
    var meta = {isp: "Example Transit", interface: {externalIp: "203.0.113.10"},
        server: {id: 12345, name: "Example Network", location: "Seattle, WA", country: "United States", ip: "198.51.100.20"}};
    if (step === 0) return Object.assign({type: "testStart"}, meta);
    if (step < 4) return {type: "ping", ping: {latency: 38.2, jitter: 1.1}};
    if (step < 20) return {type: "download", download: {bandwidth: (245 + Math.sin(step * .8) * 25) * 125000}};
    if (step < 36) return {type: "upload", upload: {bandwidth: (110 + Math.sin(step * .7) * 15) * 125000}};
    return Object.assign({type: "result", download: {bandwidth: 31250000}, upload: {bandwidth: 14375000}}, meta);
}
if (typeof module !== "undefined") module.exports = {initial: initial, mbps: mbps, reduce: reduce, canFinish: canFinish, fixture: fixture};
