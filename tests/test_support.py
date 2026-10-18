# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import support


class SettingsTests(unittest.TestCase):
    def test_config_read_only_and_type_validation(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_CONFIG_HOME":temp}):
            self.assertFalse(support.settings(False)["reducedMotion"])
            self.assertEqual(list(Path(temp).iterdir()),[])
            folder = Path(temp)/"speedtest-map"
            folder.mkdir()
            for value in [{"reducedMotion":"false"}, {"cliPath":[]}, []]:
                (folder/"config.json").write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    support.settings(False)

    def test_official_cli_path_with_spaces_is_an_argument(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_CONFIG_HOME":temp}):
            folder = Path(temp)/"speedtest-map"
            folder.mkdir()
            (folder/"config.json").write_text('{"cliPath":"/tmp/my speedtest","reducedMotion":true}')
            calls=[]
            def run(args, **kwargs):
                calls.append(args)
                output='Speedtest by Ookla 1.2.0' if '--version' in args else '--progress-update-interval'
                return subprocess.CompletedProcess(args,0,output,"")
            with patch.object(support.shutil,'which',return_value='/tmp/my speedtest'), patch.object(support.subprocess,'run',side_effect=run):
                value=support.settings()
            self.assertTrue(value['reducedMotion'])
            self.assertEqual(value['cliPath'],'/tmp/my speedtest')
            self.assertEqual(calls[0],['/tmp/my speedtest','--version'])

    def test_python_speedtest_cli_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_CONFIG_HOME":temp}):
            result=subprocess.CompletedProcess([],0,'speedtest-cli 2.1.3',"")
            with patch.object(support.shutil,'which',return_value='/tmp/speedtest'), patch.object(support.subprocess,'run',return_value=result):
                with self.assertRaisesRegex(RuntimeError,'official Ookla'):
                    support.settings()


if __name__ == '__main__':
    unittest.main()
