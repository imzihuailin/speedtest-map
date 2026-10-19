# Speedtest

Ookla Speedtest with Omarchy’s original dials and provider/server details. Open it from the network panel’s **Speed Test** button.

[简体中文](README.zh-CN.md)

![Preview](preview.png)

## Install

Requires Omarchy Quattro 4.0.5+, Python 3.10+ and [Ookla’s official CLI](https://www.speedtest.net/apps/cli) 1.2.0+ (`speedtest`, not Python `speedtest-cli`). Place the CLI on PATH or at `~/.local/bin/speedtest`, then run it once to review its terms.

From this repository:

```bash
git clone https://github.com/imzihuailin/speedtest-map.git
cd speedtest-map
python install.py
```

Installation links the source directory into Omarchy and replaces the existing speed-test entry. Keep the repository in place; rerun the installer after moving it. System files remain untouched.

Esc or clicking the background stops testing. Enter reruns a completed test. With a proxy, the provider shown is the public exit network.

## Remove

```bash
python install.py --uninstall
```

Restores the previous entry and preserves source code and the CLI. Add `--purge` to remove plugin settings. Keep `~/.local/state/speedtest-map/install.json` until uninstalling.

## Settings

Optional: `~/.config/speedtest-map/config.json` (XDG paths supported).

```json
{"cliPath":"speedtest","reducedMotion":false}
```

## Diagnose connection failures

If testing fails after disabling FlClash TUN, collect two reports from the same
terminal. Keep TUN enabled for the first command:

```bash
python tools/diagnose.py --label tun-on --output /tmp/speedtest-tun-on.json
```

Disable TUN manually, then run:

```bash
python tools/diagnose.py --label tun-off --output /tmp/speedtest-tun-off.json
```

Enable TUN again to restore connectivity, then compare or share both JSON files.
Compare `test.phases`, `test.errors`, exit codes, proxy-variable presence,
default routes and DNS status. `serverSelection` contains extra diagnostics when
the test fails or reports a recoverable error. These observations do not automatically identify a root cause.
The terminal environment may differ from the desktop panel's inherited environment.

The tool uses your configured CLI and runs one real upload/download test (up to
120 seconds), consuming network traffic. On failure it queries the server list
with detailed logging (up to 30 seconds). Local probes have separate short
timeouts. Ctrl+C stops the active subprocess and saves a partial report. Missing
utilities or restricted system access are recorded without stopping other checks.
It never changes proxy, routing, DNS or desktop settings, or accepts Ookla terms.
Run the official CLI interactively first if its terms have not been reviewed.

Reports omit raw speed results and redact IP/MAC addresses, URLs, proxy values
and credentials; interface names and diagnostic messages remain. Review reports
before sharing. A saved report returns exit code 0 even if the network test
fails; interruption returns 130, and failure to save returns 1. Reports under
`/tmp` are temporary, so copy them elsewhere if you need to retain them.

## Development

```bash
python install.py --demo    # Install without requiring the CLI
python dev.py --demo        # Offline preview and source watcher
python dev.py               # Real testing and source watcher
```

Reloading recreates the bar/services and closes open plugin panels. Ctrl+C closes the preview.

```bash
python -m unittest discover -s tests -p 'test_*.py'
node tests/model.test.cjs
omarchy plugin validate .
python tools/qml_smoke.py   # Optional on-screen integration tests
python tools/preview.py     # Generate preview.png with synthetic data
```

[Validation results](VALIDATION.md) · [GPL-3.0-only license](LICENSE.md) · [Credits](THIRD_PARTY_NOTICES.md)
