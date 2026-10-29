#!/usr/bin/env python3
"""Exercise the installed local MCP without printing credentials or QR payloads."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


LABEL = "com.example.netease-music-mcp-safe"


def _load_config(path: Path) -> dict[str, Any]:
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SystemExit("Runtime config is not private.")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _post(base: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base}/mcp",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def _call(
    base: str, token: str, request_id: int, name: str, arguments: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    body = _post(
        base,
        token,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    result = body.get("result") or {}
    content = result.get("content") or []
    text = content[0].get("text", "") if content else ""
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = {"message": text[:500]}
    return value, bool(result.get("isError"))


def _launchd_pid() -> int | None:
    result = subprocess.run(
        ["/bin/launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
        capture_output=True,
        text=True,
        check=True,
    )
    match = re.search(r"^\s*pid = (\d+)\s*$", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else None


def _restart_and_wait(base: str) -> dict[str, Any]:
    before = _launchd_pid()
    subprocess.run(
        ["/bin/launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LABEL}"],
        check=True,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2) as response:
                if response.status == 200:
                    break
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    else:
        raise SystemExit("The MCP did not become healthy after launchd restart.")
    after = _launchd_pid()
    return {
        "after_pid": after,
        "before_pid": before,
        "pid_changed": before is not None and after is not None and before != after,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.home()
        / "Library"
        / "Application Support"
        / "NetEaseMusicMCP"
        / "config"
        / "runtime.json",
    )
    parser.add_argument("--exercise-playback", action="store_true")
    parser.add_argument("--play-song-id", type=int)
    parser.add_argument("--restart", action="store_true")
    arguments = parser.parse_args()
    config = _load_config(arguments.config.expanduser().absolute())
    environment = config["environment"]
    secrets = config["secrets"]
    port = int(environment["MCP_PORT"])
    base = f"http://127.0.0.1:{port}"
    token = secrets["MCP_ACCESS_TOKEN"]

    restart = _restart_and_wait(base) if arguments.restart else {"exercised": False}

    with urllib.request.urlopen(f"{base}/health", timeout=5) as response:
        health = json.load(response)
    initialized = _post(
        base,
        token,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "local-acceptance", "version": "1"},
            },
        },
    )
    listed = _post(
        base,
        token,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    tools = listed["result"]["tools"]
    tool_names = {tool["name"] for tool in tools}
    required = {
        "get_netease_login_status",
        "search_song",
        "play_song",
        "start_netease_qr_login",
        "get_mac_netease_player_status",
        "control_mac_netease_player",
        "set_mac_output_volume",
        "start_mobile_controller_qr_login",
        "check_mobile_controller_qr_login",
        "logout_mobile_controller",
        "get_mobile_netease_player_status",
        "start_mobile_netease_player",
        "join_mobile_netease_player",
        "play_song_on_mobile",
        "control_mobile_netease_player",
        "end_mobile_netease_player",
    }
    if not required.issubset(tool_names):
        raise SystemExit(f"Required installed tools are missing: {sorted(required - tool_names)}")

    player, player_error = _call(
        base, token, 3, "get_mac_netease_player_status", {}
    )
    if player_error:
        raise SystemExit(f"Installed player status failed: {player}")
    volume, volume_error = _call(
        base,
        token,
        4,
        "set_mac_output_volume",
        {"volume": player["output_volume"]},
    )
    if volume_error:
        raise SystemExit(f"Installed volume no-op failed: {volume}")

    playback: dict[str, Any] = {"exercised": False}
    if arguments.exercise_playback:
        first, first_error = _call(
            base, token, 5, "control_mac_netease_player", {"action": "play_pause"}
        )
        if first_error:
            raise SystemExit(f"Installed playback first toggle failed: {first}")
        second, second_error = _call(
            base, token, 6, "control_mac_netease_player", {"action": "play_pause"}
        )
        if second_error:
            raise SystemExit(f"Installed playback restore toggle failed: {second}")
        playback = {
            "exercised": True,
            "first_accepted": first.get("accepted") is True,
            "second_accepted": second.get("accepted") is True,
        }

    specified_playback: dict[str, Any] = {"exercised": False}
    if arguments.play_song_id is not None:
        if arguments.play_song_id <= 0:
            raise SystemExit("--play-song-id must be a positive integer.")
        specified, specified_error = _call(
            base,
            token,
            9,
            "play_song",
            {"song_id": arguments.play_song_id},
        )
        if specified_error:
            raise SystemExit(f"Installed specified-song playback failed: {specified}")
        specified_playback = {
            "accepted": specified.get("accepted") is True,
            "exercised": True,
            "requested_song_id": specified.get("requested_song_id"),
            "state": (specified.get("playback_state") or {}).get("state"),
            "state_verified": (specified.get("playback_state") or {}).get("verified"),
        }

    login_status, login_status_error = _call(
        base, token, 7, "get_netease_login_status", {}
    )
    if login_status_error:
        raise SystemExit(f"NetEase login status failed: {login_status}")
    mobile_status, mobile_status_error = _call(
        base, token, 10, "get_mobile_netease_player_status", {}
    )
    if mobile_status_error:
        raise SystemExit(f"Installed mobile player status failed: {mobile_status}")
    qr_started, qr_error = _call(base, token, 8, "start_netease_qr_login", {})
    if qr_error:
        raise SystemExit(f"Direct NetEase QR startup failed: {qr_started}")
    login_id = qr_started.get("login_id")
    if not isinstance(login_id, str) or not login_id:
        raise SystemExit("Direct NetEase QR startup returned no login_id.")
    cancel_request = urllib.request.Request(
        f"{base}/netease/login/{login_id}/status",
        data=b'{"cancel":true}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(cancel_request, timeout=5) as response:
        qr_cancelled = json.load(response)

    summary = {
        "health": health,
        "login": {
            "authenticated": login_status.get("authenticated"),
            "source": login_status.get("source"),
        },
        "mac_player": {
            "installed": player.get("installed"),
            "output_volume": player.get("output_volume"),
            "running": player.get("running"),
            "running_check": player.get("running_check"),
            "version": player.get("version"),
        },
        "mobile_player": {
            "connected": mobile_status.get("connected"),
            "connection_state": mobile_status.get("connection_state"),
            "in_room": mobile_status.get("in_room"),
            "transport": mobile_status.get("transport"),
            "controller_authenticated": (
                mobile_status.get("controller_account") or {}
            ).get("authenticated"),
            "controller_distinct_from_daily_account": (
                mobile_status.get("controller_account") or {}
            ).get("distinct_from_daily_account"),
        },
        "playback": playback,
        "protocol_version": initialized["result"]["protocolVersion"],
        "qr_direct_https": {
            "cancelled": qr_cancelled.get("status") == "cancelled",
            "started": qr_started.get("status") == "waiting",
        },
        "restart": restart,
        "specified_playback": specified_playback,
        "server": initialized["result"]["serverInfo"],
        "tool_count": len(tools),
        "volume_noop_accepted": volume.get("accepted") is True,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
