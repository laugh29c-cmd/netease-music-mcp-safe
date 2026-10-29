"""Targeted macOS playback controls for the official NetEase Music client."""

from __future__ import annotations

import base64
import json
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


APP_PATH = Path("/Applications/NeteaseMusic.app")
BUNDLE_ID = "com.netease.163music"
PROCESS_NAME = "NeteaseMusic"
PLATFORM = sys.platform
COMMAND_TIMEOUT_SECONDS = 8
PLAYBACK_READBACK_DELAYS_SECONDS = (0.25, 0.5, 0.75)


class MacPlaybackError(RuntimeError):
    """A bounded macOS player operation could not be completed."""


def _clean_environment() -> dict[str, str]:
    env = dict(os.environ)
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        env.pop(name, None)
    return env


def _run(
    command: list[str], *, allowed_returncodes: tuple[int, ...] = (0,)
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            env=_clean_environment(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MacPlaybackError(f"macOS playback helper failed: {type(exc).__name__}") from None
    if result.returncode not in allowed_returncodes:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        if any(
            marker in detail.casefold()
            for marker in ("not authorized", "assistive", "accessibility", "不允许", "辅助")
        ):
            raise MacPlaybackError(
                "macOS has not authorized playback automation. Enable Accessibility and "
                "Automation access for the installed NetEase Music MCP runtime."
            )
        raise MacPlaybackError(f"macOS playback command failed: {detail[:500]}")
    return result


def _require_macos() -> None:
    if PLATFORM != "darwin":
        raise MacPlaybackError("Mac playback tools are available only on macOS.")


def _running_state() -> bool | None:
    try:
        result = _run(
            ["/usr/bin/pgrep", "-x", PROCESS_NAME], allowed_returncodes=(0, 1)
        )
    except MacPlaybackError:
        return None
    return result.returncode == 0 and bool(result.stdout.strip())


def _app_version() -> str | None:
    info_path = APP_PATH / "Contents" / "Info.plist"
    try:
        with info_path.open("rb") as handle:
            info = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return None
    value = info.get("CFBundleShortVersionString")
    return value if isinstance(value, str) and value else None


def _output_volume() -> int | None:
    try:
        result = _run(
            [
                "/usr/bin/osascript",
                "-e",
                "output volume of (get volume settings)",
            ]
        )
        return int(result.stdout.strip())
    except (MacPlaybackError, ValueError):
        return None


def player_status() -> dict[str, Any]:
    """Return bounded local readiness without reading private player data."""
    _require_macos()
    installed = APP_PATH.is_dir()
    running = _running_state() if installed else False
    return {
        "platform": "macOS",
        "application": "NeteaseMusic",
        "bundle_id": BUNDLE_ID,
        "installed": installed,
        "running": running,
        "running_check": "verified" if running is not None else "unavailable",
        "version": _app_version() if installed else None,
        "output_volume": _output_volume(),
        "control_method": "targeted_accessibility_menu",
    }


_PLAYBACK_STATE_MENU_NAMES = {
    "playing": ["暂停", "Pause"],
    "paused": ["播放", "Play"],
}


def _playback_state_script() -> str:
    menu_states = json.dumps(_PLAYBACK_STATE_MENU_NAMES, ensure_ascii=False)
    return f"""
(() => {{
const systemEvents = Application('System Events');
const process = systemEvents.processes.byName('{PROCESS_NAME}');
if (!process.exists()) return JSON.stringify({{state: 'stopped', verified: true, evidence: 'process_state'}});
const menuStates = {menu_states};
const menuBar = process.menuBars[0];
const menuBarItems = menuBar.menuBarItems();
for (const menuBarItem of menuBarItems) {{
  const menus = menuBarItem.menus();
  for (const menu of menus) {{
    const items = menu.menuItems();
    for (const item of items) {{
      const name = item.name();
      for (const state of Object.keys(menuStates)) {{
        if (menuStates[state].includes(name)) {{
          return JSON.stringify({{
            state: state,
            verified: true,
            evidence: 'accessible_playback_menu_action',
            observedMenuAction: name
          }});
        }}
      }}
    }}
  }}
}}
return JSON.stringify({{state: 'unknown', verified: false, evidence: 'playback_menu_action_unavailable'}});
}})();
""".strip()


def playback_state() -> dict[str, Any]:
    """Read a bounded playing/paused state without claiming current track metadata."""
    _require_macos()
    if not APP_PATH.is_dir():
        return {
            "state": "unavailable",
            "verified": True,
            "evidence": "application_not_installed",
        }
    running = _running_state()
    if running is False:
        return {"state": "stopped", "verified": True, "evidence": "process_state"}
    if running is None:
        return {
            "state": "unknown",
            "verified": False,
            "evidence": "process_state_unavailable",
        }
    try:
        result = _run(
            [
                "/usr/bin/osascript",
                "-l",
                "JavaScript",
                "-e",
                _playback_state_script(),
            ]
        )
        value = json.loads(result.stdout.strip())
    except (MacPlaybackError, json.JSONDecodeError):
        return {
            "state": "unknown",
            "verified": False,
            "evidence": "playback_state_readback_failed",
        }
    if not isinstance(value, dict) or value.get("state") not in {
        "playing",
        "paused",
        "stopped",
        "unknown",
    }:
        return {
            "state": "unknown",
            "verified": False,
            "evidence": "playback_state_readback_invalid",
        }
    return value


def play_song(song_id: int) -> dict[str, Any]:
    """Open one validated song ID in the official client and read back player state."""
    _require_macos()
    if isinstance(song_id, bool) or not isinstance(song_id, int) or song_id <= 0:
        raise ValueError("song_id must be a positive integer")
    if not APP_PATH.is_dir():
        raise MacPlaybackError("NeteaseMusic.app is not installed in /Applications.")
    payload = json.dumps(
        {"type": "song", "id": song_id, "cmd": "play"},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    deep_link = "orpheus://" + base64.b64encode(payload).decode("ascii")
    _run(["/usr/bin/open", "-g", "-b", BUNDLE_ID, deep_link])

    readback = playback_state()
    for delay in PLAYBACK_READBACK_DELAYS_SECONDS:
        if readback.get("state") == "playing":
            break
        time.sleep(delay)
        readback = playback_state()
    return {
        "accepted": True,
        "application": "NeteaseMusic",
        "bundle_id": BUNDLE_ID,
        "requested_song_id": song_id,
        "dispatch": "accepted_by_launch_services",
        "method": "allowlisted_orpheus_base64_song_command",
        "playback_state": readback,
        "current_song_id": None,
        "current_song_id_verification": "unavailable_from_official_mac_client",
    }


_CONTROL_MENU_NAMES = {
    "play_pause": ["播放/暂停", "播放", "暂停", "Play/Pause", "Play", "Pause"],
    "previous": ["上一个", "上一首", "Previous"],
    "next": ["下一个", "下一首", "Next"],
}


def _menu_control_script(menu_names: list[str]) -> str:
    wanted = json.dumps(menu_names, ensure_ascii=False)
    return f"""
(() => {{
const systemEvents = Application('System Events');
const process = systemEvents.processes.byName('{PROCESS_NAME}');
if (!process.exists()) throw new Error('NeteaseMusic is not running');
const wanted = {wanted};
const menuBar = process.menuBars[0];
const menuBarItems = menuBar.menuBarItems();
for (const menuBarItem of menuBarItems) {{
  const menus = menuBarItem.menus();
  for (const menu of menus) {{
    const items = menu.menuItems();
    for (const item of items) {{
      const name = item.name();
      if (wanted.includes(name)) {{
        item.click();
        return JSON.stringify({{clicked: true, menuItem: name}});
      }}
    }}
  }}
}}
throw new Error('NetEase playback menu item not found');
}})();
""".strip()


def control_player(action: str) -> dict[str, Any]:
    """Launch or control the official NetEase client without coordinate clicks."""
    _require_macos()
    if action == "launch":
        if not APP_PATH.is_dir():
            raise MacPlaybackError("NeteaseMusic.app is not installed in /Applications.")
        _run(["/usr/bin/open", "-b", BUNDLE_ID])
        return {
            "action": action,
            "accepted": True,
            "application": "NeteaseMusic",
            "bundle_id": BUNDLE_ID,
        }
    menu_names = _CONTROL_MENU_NAMES.get(action)
    if menu_names is None:
        raise ValueError("action must be one of: launch, play_pause, previous, next")
    if not APP_PATH.is_dir():
        raise MacPlaybackError("NeteaseMusic.app is not installed in /Applications.")
    running = _running_state()
    if running is False:
        raise MacPlaybackError("NeteaseMusic is not running. Use action=launch first.")
    result = _run(
        [
            "/usr/bin/osascript",
            "-l",
            "JavaScript",
            "-e",
            _menu_control_script(menu_names),
        ]
    )
    detail: dict[str, Any] | None = None
    try:
        parsed = json.loads(result.stdout.strip())
        if isinstance(parsed, dict):
            detail = parsed
    except json.JSONDecodeError:
        pass
    return {
        "action": action,
        "accepted": True,
        "application": "NeteaseMusic",
        "bundle_id": BUNDLE_ID,
        "method": "targeted_accessibility_menu",
        "detail": detail,
    }


def set_output_volume(volume: int) -> dict[str, Any]:
    """Set the Mac output volume through the built-in AppleScript command."""
    _require_macos()
    if isinstance(volume, bool) or not isinstance(volume, int) or not 0 <= volume <= 100:
        raise ValueError("volume must be an integer from 0 to 100")
    _run(["/usr/bin/osascript", "-e", f"set volume output volume {volume}"])
    return {"accepted": True, "output_volume": volume}
