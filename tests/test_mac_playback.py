import json
import shutil
import subprocess
import unittest
from unittest import mock

import mac_playback


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class MacPlaybackTests(unittest.TestCase):
    def setUp(self):
        self.platform = mock.patch.object(mac_playback, "PLATFORM", "darwin")
        self.platform.start()

    def tearDown(self):
        self.platform.stop()

    def test_status_is_bounded_and_does_not_read_player_content(self):
        calls = [
            completed(["pgrep"], stdout="123\n"),
            completed(["osascript"], stdout="37\n"),
        ]
        fake_path = mock.Mock()
        fake_path.is_dir.return_value = True
        with mock.patch.object(mac_playback, "APP_PATH", fake_path), mock.patch.object(
            mac_playback, "_app_version", return_value="3.1.12"
        ), mock.patch.object(mac_playback, "_run", side_effect=calls):
            result = mac_playback.player_status()
        self.assertEqual(result["bundle_id"], "com.netease.163music")
        self.assertTrue(result["installed"])
        self.assertTrue(result["running"])
        self.assertEqual(result["running_check"], "verified")
        self.assertEqual(result["output_volume"], 37)
        self.assertNotIn("title", result)

    def test_playback_control_uses_targeted_menu_without_coordinates(self):
        calls = [
            completed(["pgrep"], stdout="123\n"),
            completed(["osascript"], stdout='{"clicked":true,"menuItem":"播放/暂停"}'),
        ]
        fake_path = mock.Mock()
        fake_path.is_dir.return_value = True
        with mock.patch.object(mac_playback, "APP_PATH", fake_path), mock.patch.object(
            mac_playback, "_run", side_effect=calls
        ) as run:
            result = mac_playback.control_player("play_pause")
        command = run.call_args_list[1].args[0]
        script = command[-1]
        self.assertEqual(command[:4], ["/usr/bin/osascript", "-l", "JavaScript", "-e"])
        self.assertIn("NeteaseMusic", script)
        self.assertIn("menuItems", script)
        self.assertNotIn("click at", script.casefold())
        self.assertTrue(result["accepted"])
        self.assertEqual(result["detail"]["menuItem"], "播放/暂停")

    def test_play_song_uses_allowlisted_numeric_deep_link_and_reads_state(self):
        fake_path = mock.Mock()
        fake_path.is_dir.return_value = True
        readback = {
            "state": "playing",
            "verified": True,
            "evidence": "accessible_playback_menu_action",
            "observedMenuAction": "暂停",
        }
        with mock.patch.object(mac_playback, "APP_PATH", fake_path), mock.patch.object(
            mac_playback, "_run", return_value=completed(["open"])
        ) as run, mock.patch.object(
            mac_playback, "playback_state", return_value=readback
        ) as state:
            result = mac_playback.play_song(29816860)
        run.assert_called_once_with(
            [
                "/usr/bin/open",
                "-g",
                "-b",
                "com.netease.163music",
                "orpheus://eyJ0eXBlIjoic29uZyIsImlkIjoyOTgxNjg2MCwiY21kIjoicGxheSJ9",
            ]
        )
        state.assert_called_once_with()
        self.assertEqual(result["requested_song_id"], 29816860)
        self.assertEqual(result["playback_state"], readback)
        self.assertIsNone(result["current_song_id"])
        self.assertEqual(
            result["current_song_id_verification"],
            "unavailable_from_official_mac_client",
        )

    def test_play_song_rejects_non_positive_or_non_integer_ids(self):
        for invalid in (0, -1, True, "186016", 186016.0):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                mac_playback.play_song(invalid)

    def test_playback_state_reads_the_official_clients_menu_action(self):
        fake_path = mock.Mock()
        fake_path.is_dir.return_value = True
        payload = json.dumps(
            {
                "state": "playing",
                "verified": True,
                "evidence": "accessible_playback_menu_action",
                "observedMenuAction": "暂停",
            },
            ensure_ascii=False,
        )
        with mock.patch.object(mac_playback, "APP_PATH", fake_path), mock.patch.object(
            mac_playback, "_running_state", return_value=True
        ), mock.patch.object(
            mac_playback, "_run", return_value=completed(["osascript"], stdout=payload)
        ) as run:
            result = mac_playback.playback_state()
        command = run.call_args.args[0]
        self.assertEqual(
            command[:4], ["/usr/bin/osascript", "-l", "JavaScript", "-e"]
        )
        self.assertIn("NeteaseMusic", command[-1])
        self.assertIn("observedMenuAction", command[-1])
        self.assertEqual(result["state"], "playing")
        self.assertTrue(result["verified"])

    def test_playback_state_failure_is_unknown_instead_of_false_success(self):
        fake_path = mock.Mock()
        fake_path.is_dir.return_value = True
        with mock.patch.object(mac_playback, "APP_PATH", fake_path), mock.patch.object(
            mac_playback, "_running_state", return_value=True
        ), mock.patch.object(
            mac_playback,
            "_run",
            side_effect=mac_playback.MacPlaybackError("not authorized"),
        ):
            result = mac_playback.playback_state()
        self.assertEqual(result["state"], "unknown")
        self.assertFalse(result["verified"])

    @unittest.skipUnless(shutil.which("osascript"), "requires macOS osascript")
    def test_generated_jxa_has_valid_system_syntax(self):
        scripts = [
            mac_playback._menu_control_script(["播放/暂停"]),
            mac_playback._playback_state_script(),
        ]
        for script in scripts:
            with self.subTest(script=script[:40]):
                result = subprocess.run(
                    ["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                combined = f"{result.stdout}\n{result.stderr}"
                self.assertNotIn("syntax error", combined.casefold())
                self.assertNotIn("SyntaxError", combined)

    def test_launch_targets_bundle_identifier(self):
        fake_path = mock.Mock()
        fake_path.is_dir.return_value = True
        with mock.patch.object(mac_playback, "APP_PATH", fake_path), mock.patch.object(
            mac_playback, "_run", return_value=completed(["open"])
        ) as run:
            result = mac_playback.control_player("launch")
        run.assert_called_once_with(["/usr/bin/open", "-b", "com.netease.163music"])
        self.assertTrue(result["accepted"])

    def test_set_volume_validates_exact_range(self):
        with mock.patch.object(
            mac_playback, "_run", return_value=completed(["osascript"])
        ) as run:
            result = mac_playback.set_output_volume(42)
        run.assert_called_once_with(
            ["/usr/bin/osascript", "-e", "set volume output volume 42"]
        )
        self.assertEqual(result["output_volume"], 42)
        for invalid in (-1, 101, True, 42.5):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                mac_playback.set_output_volume(invalid)

    def test_subprocess_environment_removes_proxy_variables(self):
        fake_env = {
            "HOME": "/Users/test",
            "HTTP_PROXY": "http://127.0.0.1:7890",
            "HTTPS_PROXY": "http://127.0.0.1:7890",
            "ALL_PROXY": "socks5://127.0.0.1:7890",
        }
        with mock.patch.dict(mac_playback.os.environ, fake_env, clear=True), mock.patch.object(
            mac_playback.subprocess,
            "run",
            return_value=completed(["helper"], stdout="ok"),
        ) as run:
            mac_playback._run(["helper"])
        child_env = run.call_args.kwargs["env"]
        self.assertEqual(child_env["HOME"], "/Users/test")
        self.assertTrue(
            {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}.isdisjoint(child_env)
        )

    def test_accessibility_error_is_actionable_and_bounded(self):
        failure = completed(
            ["osascript"], returncode=1, stderr="System Events not authorized"
        )
        with mock.patch.object(mac_playback.subprocess, "run", return_value=failure):
            with self.assertRaises(mac_playback.MacPlaybackError) as context:
                mac_playback._run(["/usr/bin/osascript"])
        self.assertIn("Accessibility", str(context.exception))
        self.assertNotIn("System Events not authorized", str(context.exception))


if __name__ == "__main__":
    unittest.main()
