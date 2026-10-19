# SPDX-License-Identifier: GPL-3.0-only
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import diagnose


FAKE = '''#!/usr/bin/env python3
import json, os, sys, time
if '--version' in sys.argv:
    print('Speedtest by Ookla 1.2.0.84'); sys.exit()
if '--help' in sys.argv:
    print('--progress-update-interval'); sys.exit()
if '--servers' in sys.argv:
    print('Server selection: https://user:password@example.test 203.0.113.10')
    sys.exit(1)
assert sys.argv[1:] == ['--format=json', '--progress=yes', '--progress-update-interval=250']
scenario = os.environ.get('DIAGNOSE_SCENARIO', 'success')
if scenario == 'timeout':
    print(os.getpid(), flush=True); time.sleep(60)
if scenario == 'connect':
    print('Error: [0] Timeout occured in connect.', file=sys.stderr); sys.exit(1)
if scenario == 'dns':
    print(json.dumps({'type':'log', 'level':'error', 'message':'Could not resolve host: https://example.test'}))
    sys.exit(1)
print(json.dumps({'type':'testStart', 'interface':{'externalIp':'203.0.113.10', 'macAddr':'aa:bb:cc:dd:ee:ff'}, 'isp':'PRIVATE ISP'}))
print(json.dumps({'type':'download', 'download':{'bandwidth':12500000}}))
sys.stdout.write(json.dumps({'type':'result', 'download':{'bandwidth':12500000}, 'upload':{'bandwidth':6250000}, 'result':{'url':'https://example.test/private-result'}}))
'''


class DiagnoseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.cli = base / "fake speedtest"
        self.cli.write_text(FAKE)
        self.cli.chmod(0o755)
        config = base / "speedtest-map"
        config.mkdir()
        (config / "config.json").write_text(json.dumps({"cliPath": str(self.cli)}))
        self.env = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(base), "DIAGNOSE_SCENARIO": "success"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def collect(self):
        real_run = diagnose.run

        def probe(command, timeout):
            if command[0] in ("ip", "resolvectl"):
                return {"exitCode": None, "timedOut": False, "interrupted": False,
                        "elapsedSeconds": 0, "error": "utility unavailable", "stdout": "", "stderr": ""}
            return real_run(command, timeout)

        with patch.object(diagnose, "run", side_effect=probe), contextlib.redirect_stderr(io.StringIO()):
            return diagnose.collect("tun-on")

    def test_success_real_cli_with_spaces_and_no_raw_results(self):
        report = self.collect()
        self.assertTrue(report["test"]["success"])
        self.assertEqual(report["test"]["phases"], ["testStart", "download", "result"])
        self.assertNotIn("serverSelection", report)
        self.assertIn("Ookla", report["cliVersion"]["stdout"])
        self.assertIn("utility unavailable", report["network"]["dns"]["error"])
        for secret in ("PRIVATE ISP", "203.0.113.10", "aa:bb:cc:dd:ee:ff", "private-result"):
            self.assertNotIn(secret, json.dumps(report))

    def test_network_errors_preserved_and_selection_added(self):
        for scenario, message in (("connect", "Timeout occured in connect."), ("dns", "Could not resolve host:")):
            with self.subTest(scenario=scenario), patch.dict(os.environ, {"DIAGNOSE_SCENARIO": scenario}):
                report = self.collect()
                self.assertFalse(report["test"]["success"])
                self.assertIn(message, report["test"]["errors"][0])
                self.assertIn("serverSelection", report)
                for secret in ("password", "203.0.113.10", "example.test"):
                    self.assertNotIn(secret, json.dumps(report))

    def test_recovered_error_keeps_success_and_server_diagnostics(self):
        event = {'type': 'result', 'download': {'bandwidth': 1}, 'upload': {'bandwidth': 1}}
        result = {'exitCode': 0, 'stdout': json.dumps(event), 'stderr': 'Error: [0] Timeout occurred in connect.',
                  'timedOut': False, 'interrupted': False}
        summary = diagnose.summarize_test(result)
        self.assertTrue(summary['success'])
        self.assertEqual(summary['errors'], ['Error: [0] Timeout occurred in connect.'])

    def test_server_selection_omits_verbose_configuration(self):
        result = {'exitCode': 0, 'stdout': 'Closest servers:\n 3633 China Telecom Shanghai China',
                  'stderr': '[info] HTTP request completed with response code 200\n'
                            '[info] configuration content:\n{"licenseKey":"private-secret"}',
                  'timedOut': False, 'interrupted': False}
        summary = diagnose.summarize_server_selection(result)
        self.assertEqual(len(summary['servers']), 1)
        self.assertIn('HTTP request', summary['log'][0])
        self.assertNotIn('private-secret', json.dumps(summary))

    def test_missing_cli_still_produces_report(self):
        with patch.object(diagnose.support, "settings", side_effect=RuntimeError("Ookla Speedtest CLI is missing")):
            report = self.collect()
        self.assertIn("missing", report["settingsError"])
        self.assertNotIn("test", report)

    def test_timeout_kills_and_reaps_cli(self):
        with patch.dict(os.environ, {"DIAGNOSE_SCENARIO": "timeout"}):
            result = diagnose.run([str(self.cli), *diagnose.TEST_ARGS], .2)
        self.assertTrue(result["timedOut"])
        self.assertLess(result["elapsedSeconds"], 3)
        self.assertIsNotNone(result["exitCode"])
        pid = int(result["stdout"].strip())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_interrupt_kills_real_cli_and_skips_selection(self):
        original = subprocess.Popen.communicate
        first = True

        def interrupt(process, *args, **kwargs):
            nonlocal first
            if first:
                first = False
                try:
                    original(process, timeout=.2)
                except subprocess.TimeoutExpired:
                    raise KeyboardInterrupt
            return original(process, *args, **kwargs)

        with patch.dict(os.environ, {"DIAGNOSE_SCENARIO": "timeout"}), patch.object(subprocess.Popen, "communicate", interrupt):
            result = diagnose.run([str(self.cli), *diagnose.TEST_ARGS], 120)
        self.assertTrue(result["interrupted"])
        with self.assertRaises(ProcessLookupError):
            os.kill(int(result["stdout"].strip()), 0)
        interrupted = {**result, "stdout": "", "stderr": ""}
        with patch.object(diagnose, "run", return_value=interrupted):
            report = diagnose.collect("tun-off")
        self.assertTrue(report["interrupted"])
        self.assertNotIn("serverSelection", report)

    def test_missing_system_command_is_data(self):
        result = diagnose.run(["/nonexistent-speedtest-map-command"], 1)
        self.assertIn("error", result)
        self.assertIsNone(result["exitCode"])

    def test_probe_deadlines_and_no_followup_after_test_interrupt(self):
        for interrupted in (False, True):
            calls = []

            def run(command, timeout):
                calls.append((command, timeout))
                is_test = '--format=json' in command
                return {"exitCode": -9 if is_test else 0, "timedOut": is_test and not interrupted,
                        "interrupted": is_test and interrupted, "elapsedSeconds": 0,
                        "stdout": "", "stderr": ""}

            with patch.object(diagnose, 'run', side_effect=run), \
                    patch.object(diagnose.support, 'settings', return_value={'cliPath': str(self.cli)}), \
                    contextlib.redirect_stderr(io.StringIO()):
                report = diagnose.collect('tun-off')
            self.assertEqual([limit for _, limit in calls], [5, 5, 5, 3, 120] + ([] if interrupted else [30]))
            self.assertEqual('serverSelection' in report, not interrupted)

    def test_incomplete_result_is_not_success(self):
        for bandwidth in (None, -1, True, float('inf')):
            event = {'type': 'result', 'download': {'bandwidth': bandwidth}, 'upload': {'bandwidth': 1}}
            summary = diagnose.summarize_test({'exitCode': 0, 'stdout': json.dumps(event),
                                              'stderr': '', 'timedOut': False, 'interrupted': False})
            self.assertFalse(summary['success'])

    def test_redaction(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "proxy.example.test:7890"}):
            text = diagnose.redact('203.0.113.10 192.168.1.1 fe80::abcd%eth0 [2001:db8::1] ::1 aa:bb:cc:dd:ee:ff '
                                   'https://user:secret@example.test/a user:secret@example.test '
                                   'token=private password:private Authorization: Bearer private proxy.example.test:7890 ' + str(Path.home()))
        for secret in ('203.0.113.10', '192.168.1.1', 'fe80::abcd', '2001:db8::1', '::1',
                       'aa:bb:cc:dd:ee:ff', 'secret', 'private', 'proxy.example.test', str(Path.home())):
            self.assertNotIn(secret, text)
        self.assertEqual(diagnose.redact('Error: [0] Timeout occured in connect.'),
                         'Error: [0] Timeout occured in connect.')

    def test_report_written_even_on_failure_and_interrupt(self):
        output = Path(self.temp.name) / "report.json"
        for report, expected in (({"settingsError": "missing"}, 0), ({"interrupted": True}, 130)):
            with patch.object(sys, "argv", ["diagnose.py", "--label", "tun-off", "--output", str(output)]), \
                    patch.object(diagnose, "collect", return_value=report), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(diagnose.main(), expected)
            self.assertEqual(json.loads(output.read_text()), report)


if __name__ == "__main__":
    unittest.main()
