#!/usr/bin/env python3
"""Collect a local Speedtest diagnostic report without changing network settings."""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
from datetime import datetime, timezone
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import support

TEST_ARGS = ["--format=json", "--progress=yes", "--progress-update-interval=250"]
PROXY_NAMES = ("http_proxy", "https_proxy", "all_proxy", "no_proxy",
               "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")


def redact(text):
    # Never persist proxy endpoints, credentials, URLs or local home paths.
    text = str(text)
    secrets = [os.environ.get(name, "") for name in PROXY_NAMES]
    secrets.append(str(Path.home()))
    for secret in sorted(filter(None, secrets), key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
    text = re.sub(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://\S+", "[url]", text)
    text = re.sub(r"\b[^\s/@:]+:[^\s/@]+@[^\s/]+", "[credentials]", text)
    text = re.sub(r"(?i)\b(password|token|authorization|api[_-]?key)\s*[:=]\s*(?:(?:bearer|basic)\s+)?\S+",
                  r"\1=[redacted]", text)
    text = re.sub(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", "[mac]", text)
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[ip]", text)

    def ipv6(match):
        candidate = match.group().strip("[]")
        try:
            ipaddress.IPv6Address(candidate.split("%", 1)[0])
        except ValueError:
            return match.group()
        return "[ip]"

    return re.sub(r"\[?[0-9a-fA-F:]*:[0-9a-fA-F:.]+(?:%[\w.-]+)?\]?", ipv6, text)


def run(command, timeout):
    """Bound each probe and reap its process group on timeout or interruption."""
    started = time.monotonic()
    result = {"exitCode": None, "timedOut": False, "interrupted": False}
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, errors="replace", start_new_session=True)
    except OSError as error:
        result.update(error=str(error), stdout="", stderr="")
    else:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            result["timedOut" if isinstance(error, subprocess.TimeoutExpired) else "interrupted"] = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
        result.update(exitCode=process.returncode, stdout=stdout, stderr=stderr)
    result["elapsedSeconds"] = round(time.monotonic() - started, 3)
    return result


def safe_probe(result):
    return {key: redact(value)[-12000:] if isinstance(value, str) else value
            for key, value in result.items()}


def summarize_server_selection(result):
    """Keep the server list and connection milestones, not verbose config data."""
    summary = {key: value for key, value in result.items() if key not in ("stdout", "stderr")}
    summary["servers"] = [redact(line.strip())[:300] for line in result["stdout"].splitlines()
                          if re.match(r"^\s*\d+\s+\S", line)][:20]
    summary["log"] = [redact(line.strip())[:500] for line in result["stderr"].splitlines()
                      if re.match(r"(?i)^(?:\[[^]]+\]\s*)?(?:\[(?:info|warn|error)\]\s*)?"
                                  r"(?:resolved address|http request|error:|failed to|timeout\b)", line)
                      and len(line) < 2000][-30:]
    if "error" in summary:
        summary["error"] = redact(summary["error"])
    return summary


def summarize_test(result):
    summary = {key: value for key, value in result.items() if key not in ("stdout", "stderr")}
    summary.update(phases=[], resultReceived=False, errors=[])
    # Whitelist fields: never store raw interface, ISP, server or result objects.
    for stream in (result["stdout"], result["stderr"]):
        for line in stream.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                if line.strip():
                    summary["errors"].append(redact(line)[:2000])
                continue
            if not isinstance(event, dict):
                continue
            phase = event.get("type")
            if phase in ("testStart", "ping", "download", "upload", "result"):
                if phase not in summary["phases"]:
                    summary["phases"].append(phase)
            if phase == "result":
                summary["resultReceived"] = all(
                    isinstance(event.get(name), dict)
                    and isinstance(event[name].get("bandwidth"), (float, int))
                    and not isinstance(event[name]["bandwidth"], bool)
                    and math.isfinite(event[name]["bandwidth"])
                    and event[name]["bandwidth"] >= 0
                    for name in ("download", "upload"))
            if event.get("error") or (phase == "log" and event.get("level") == "error"):
                summary["errors"].append(redact(event.get("error") or event.get("message") or "Speedtest failed.")[:2000])
    summary["errors"] = summary["errors"][-20:]
    # The CLI can log a recoverable connection timeout before choosing a server.
    summary["success"] = (result["exitCode"] == 0 and summary["resultReceived"]
                          and not result["timedOut"]
                          and not result["interrupted"])
    if "error" in summary:
        summary["error"] = redact(summary["error"])
    return summary


def collect(label):
    report = {"schemaVersion": 1, "label": redact(label),
              "collectedAt": datetime.now(timezone.utc).isoformat(),
              "proxyVariablesPresent": {name: name in os.environ for name in PROXY_NAMES}}
    # Read-only, short local probes. A sandbox or missing utility is recorded.
    probes = (("ipv4DefaultRoute", ["ip", "-4", "route", "show", "default"]),
              ("ipv6DefaultRoute", ["ip", "-6", "route", "show", "default"]),
              ("dns", ["resolvectl", "dns"]))
    report["network"] = {}
    for name, command in probes:
        probe = run(command, 5)
        report["network"][name] = safe_probe(probe)
        if probe["interrupted"]:
            report["interrupted"] = True
            return report
    try:
        lines = Path("/etc/resolv.conf").read_text().splitlines()
        report["network"]["resolvConf"] = [redact(fields[1]) for line in lines
                                              if len(fields := line.split()) >= 2 and fields[0] == "nameserver"]
    except OSError as error:
        report["network"]["resolvConfError"] = redact(error)
    try:
        config = support.settings()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        report["settingsError"] = redact(error)
        return report
    cli = config["cliPath"]
    version = run([cli, "--version"], 3)
    report["cliVersion"] = safe_probe(version)
    if version["interrupted"]:
        report["interrupted"] = True
        return report
    print("Running a real speed test (up to 120 seconds)...", file=sys.stderr)
    report["test"] = summarize_test(run([cli, *TEST_ARGS], 120))
    if (not report["test"]["success"] or report["test"]["errors"]) and not report["test"]["interrupted"]:
        print("Collecting server selection diagnostics (up to 30 seconds)...", file=sys.stderr)
        report["serverSelection"] = summarize_server_selection(run([cli, "--servers", "--selection-details", "-vv"], 30))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, choices=("tun-on", "tun-off"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = collect(args.label)
    except KeyboardInterrupt:
        report = {"schemaVersion": 1, "label": args.label, "interrupted": True}
    try:
        support.atomic_json(args.output, report)
    except OSError as error:
        print(f"Could not write report: {redact(error)}", file=sys.stderr)
        return 1
    print(f"Diagnostic report saved to {args.output}")
    if report.get("interrupted") or report.get("test", {}).get("interrupted") or report.get("serverSelection", {}).get("interrupted"):
        return 130
    # Network failures are report data; a successfully saved report is usable.
    return 0


if __name__ == "__main__":
    sys.exit(main())
