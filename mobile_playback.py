"""Bounded control of the official NetEase Music iPhone app via Listen Together.

The protocol shape is adapted from the MIT-licensed
NeteaseCloudMusicApiEnhanced/api-enhanced Listen Together modules. Network and
account-session ownership stay in server.py; this module only constructs fixed,
allowlisted requests and sanitizes their responses.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from typing import Any, Callable


Request = Callable[[str, dict[str, Any]], dict[str, Any]]

API_ORIGIN = "https://music.163.com"
SHARE_ORIGIN = "https://st.music.163.com/listen-together/share/"
STATUS_PATH = "/api/listen/together/status/get"
CREATE_PATH = "/api/listen/together/room/create"
CHECK_PATH = "/api/listen/together/room/check"
ACCEPT_PATH = "/api/listen/together/play/invitation/accept"
COMMAND_PATH = "/api/listen/together/play/command/report"
SYNC_LIST_PATH = "/api/listen/together/sync/list/command/report"
HEARTBEAT_PATH = "/api/listen/together/heartbeat"
END_PATH = "/api/listen/together/end/v2"

NON_CONNECTED_STATES = {"", "NOT_CONNECTED", "DISCONNECTED", "ENDED", "CLOSED"}
ALLOWED_ACTIONS = {"play", "pause", "seek"}
OFFICIAL_SHARE_HOST = "st.music.163.com"


class MobilePlaybackError(RuntimeError):
    """A bounded mobile-control failure that is safe to expose as a tool error."""


def _url(path: str) -> str:
    return API_ORIGIN + path


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer.")
    return value


def _response_data(response: dict[str, Any], operation: str) -> dict[str, Any]:
    if not isinstance(response, dict) or response.get("code") != 200:
        raise MobilePlaybackError(f"NetEase rejected the mobile {operation} request.")
    data = response.get("data")
    if not isinstance(data, dict):
        raise MobilePlaybackError(
            f"NetEase returned an unexpected mobile {operation} response."
        )
    return data


def _optional_song_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return None


def _first_song_id(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, dict):
            for key in (
                "songId",
                "songID",
                "trackId",
                "targetSongId",
                "currentSongId",
                "resourceId",
            ):
                song_id = _optional_song_id(value.get(key))
                if song_id is not None:
                    return song_id
    return None


def normalize_status_response(response: dict[str, Any]) -> dict[str, Any]:
    data = _response_data(response, "status")
    room = data.get("roomInfo") if isinstance(data.get("roomInfo"), dict) else {}
    another_device = (
        data.get("anotherDeviceInfo")
        if isinstance(data.get("anotherDeviceInfo"), dict)
        else {}
    )
    users = room.get("roomUsers") if isinstance(room.get("roomUsers"), list) else []
    upstream_status = str(data.get("status") or "").strip().upper()
    in_room = bool(data.get("inRoom"))
    room_id = room.get("roomId")
    if room_id is not None:
        room_id = str(room_id).strip() or None
    connected = bool(
        in_room
        and room_id
        and (
            bool(another_device)
            or len(users) > 1
            or upstream_status not in NON_CONNECTED_STATES
        )
    )
    current_song_id = _first_song_id(
        another_device,
        room.get("matchPlayInfo") if isinstance(room, dict) else None,
        room.get("playingInfo") if isinstance(room, dict) else None,
        data.get("playInfo") if isinstance(data.get("playInfo"), dict) else None,
    )
    if connected:
        connection_state = "connected"
    elif in_room:
        connection_state = "waiting_for_iphone"
    else:
        connection_state = "not_in_room"
    return {
        "platform": "iphone_official_netease_app",
        "transport": "netease_listen_together",
        "in_room": in_room,
        "room_id": room_id,
        "connection_state": connection_state,
        "connected": connected,
        "upstream_status": upstream_status or None,
        "participant_count": len(users),
        "another_device_present": bool(another_device),
        "current_song_id": current_song_id,
        "current_song_id_verified": current_song_id is not None,
    }


def get_mobile_player_status(request: Request) -> dict[str, Any]:
    return normalize_status_response(request(_url(STATUS_PATH), {}))


def build_invite_url(song_id: int, room_id: str, inviter_id: int) -> str:
    song_id = _positive_int(song_id, "song_id")
    inviter_id = _positive_int(inviter_id, "inviter_id")
    room_id = str(room_id or "").strip()
    if not room_id or len(room_id) > 200:
        raise ValueError("room_id is missing or invalid.")
    return SHARE_ORIGIN + "?" + urllib.parse.urlencode(
        {"songId": song_id, "roomId": room_id, "inviterId": inviter_id}
    )


def parse_mobile_invite_url(invite_url: Any) -> dict[str, Any]:
    if not isinstance(invite_url, str):
        raise ValueError("invite_url must be an official NetEase Listen Together URL.")
    invite_url = invite_url.strip()
    if not invite_url or len(invite_url) > 2048:
        raise ValueError("invite_url must be an official NetEase Listen Together URL.")
    parsed = urllib.parse.urlsplit(invite_url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != OFFICIAL_SHARE_HOST:
        raise ValueError("invite_url must use the official st.music.163.com HTTPS host.")
    if not parsed.path.startswith("/listen-together/share"):
        raise ValueError("invite_url is not a NetEase Listen Together invitation.")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
    room_id = str((query.get("roomId") or [""])[0]).strip()
    if not room_id or len(room_id) > 200:
        raise ValueError("invite_url has a missing or invalid roomId.")
    inviter_raw = str((query.get("inviterId") or [""])[0]).strip()
    if not inviter_raw.isdigit() or int(inviter_raw) < 1:
        raise ValueError("invite_url has a missing or invalid inviterId.")
    song_id = _optional_song_id((query.get("songId") or [None])[0])
    return {
        "room_id": room_id,
        "inviter_id": int(inviter_raw),
        "song_id": song_id,
    }


def join_mobile_player(request: Request, invite_url: Any) -> dict[str, Any]:
    invitation = parse_mobile_invite_url(invite_url)
    before = get_mobile_player_status(request)
    room_id = invitation["room_id"]
    reused = bool(before["in_room"] and before["room_id"] == room_id)
    ended_previous_room = False
    if before["in_room"] and before["room_id"] != room_id:
        ended = _response_data(
            request(_url(END_PATH), {"roomId": before["room_id"]}),
            "previous room end",
        )
        if ended.get("success") is False:
            raise MobilePlaybackError("NetEase did not end the previous mobile room.")
        ended_previous_room = True
    if not reused:
        accepted = _response_data(
            request(
                _url(ACCEPT_PATH),
                {
                    "refer": "inbox_invite",
                    "roomId": room_id,
                    "inviterId": invitation["inviter_id"],
                },
            ),
            "room invitation",
        )
        accepted_room = accepted.get("roomInfo")
        accepted_room_id = (
            str(accepted_room.get("roomId") or "").strip()
            if isinstance(accepted_room, dict)
            else ""
        )
        if accepted_room_id and accepted_room_id != room_id:
            raise MobilePlaybackError("NetEase joined an unexpected mobile room.")
    status = get_mobile_player_status(request)
    joined = bool(status["in_room"] and status["room_id"] == room_id)
    if not joined:
        raise MobilePlaybackError("NetEase did not join the requested mobile room.")
    return {
        "accepted": True,
        "room_reused": reused,
        "ended_previous_room": ended_previous_room,
        "invited_song_id": invitation["song_id"],
        "status": status,
        "next_tool": "play_song_on_mobile" if status["connected"] else "get_mobile_netease_player_status",
    }


def start_mobile_player(request: Request, song_id: Any, inviter_id: Any) -> dict[str, Any]:
    song_id = _positive_int(song_id, "song_id")
    inviter_id = _positive_int(inviter_id, "inviter_id")
    before = get_mobile_player_status(request)
    reused = bool(before["in_room"] and before["room_id"])
    if reused:
        room_id = str(before["room_id"])
    else:
        created = _response_data(
            request(_url(CREATE_PATH), {"refer": "songplay_more"}), "room creation"
        )
        room = created.get("roomInfo")
        room_id = str(room.get("roomId") or "").strip() if isinstance(room, dict) else ""
        if not room_id:
            raise MobilePlaybackError("NetEase did not return a mobile room ID.")
        checked = _response_data(
            request(_url(CHECK_PATH), {"roomId": room_id}), "room check"
        )
        if checked.get("joinable") is False:
            raise MobilePlaybackError("The new NetEase mobile room is not joinable.")
    status = get_mobile_player_status(request)
    return {
        "accepted": True,
        "room_reused": reused,
        "requested_song_id": song_id,
        "invite_url": build_invite_url(song_id, room_id, inviter_id),
        "status": status,
        "next_step": (
            "Open invite_url on the iPhone with the official NetEase Music app, "
            "then call get_mobile_netease_player_status until connected is true."
        ),
    }


def _require_connected(request: Request) -> dict[str, Any]:
    status = get_mobile_player_status(request)
    if not status["in_room"]:
        raise MobilePlaybackError(
            "MOBILE_ROOM_REQUIRED: Call start_mobile_netease_player first."
        )
    if not status["connected"]:
        raise MobilePlaybackError(
            "MOBILE_IPHONE_NOT_CONNECTED: Open the current invite URL in the official "
            "NetEase Music app on the iPhone, then check status again."
        )
    return status


def _send_command(
    request: Request,
    status: dict[str, Any],
    *,
    command_type: str,
    play_status: str,
    target_song_id: int,
    progress_ms: int,
) -> dict[str, Any]:
    room_id = status.get("room_id")
    if not room_id:
        raise MobilePlaybackError("The connected mobile room has no room ID.")
    current_song_id = status.get("current_song_id")
    command = {
        "commandType": command_type,
        "progress": progress_ms,
        "playStatus": play_status,
        "formerSongId": current_song_id if current_song_id is not None else -1,
        "targetSongId": target_song_id,
        "clientSeq": int(time.time_ns() // 1_000_000),
    }
    data = _response_data(
        request(
            _url(COMMAND_PATH),
            {
                "roomId": room_id,
                "commandInfo": json.dumps(command, separators=(",", ":")),
            },
        ),
        "playback command",
    )
    if data.get("result") is not True:
        raise MobilePlaybackError("NetEase did not accept the mobile playback command.")
    heartbeat_accepted = False
    try:
        heartbeat = _response_data(
            request(
                _url(HEARTBEAT_PATH),
                {
                    "roomId": room_id,
                    "songId": target_song_id,
                    "playStatus": play_status,
                    "progress": progress_ms,
                },
            ),
            "heartbeat",
        )
        heartbeat_accepted = heartbeat.get("success", heartbeat.get("result", True)) is not False
    except MobilePlaybackError:
        heartbeat_accepted = False
    return {
        "accepted": True,
        "room_id": room_id,
        "command_type": command_type,
        "play_status": play_status,
        "target_song_id": target_song_id,
        "progress_ms": progress_ms,
        "heartbeat_accepted": heartbeat_accepted,
    }


def _sync_single_song_playlist(
    request: Request,
    status: dict[str, Any],
    *,
    song_id: int,
    controller_user_id: int,
) -> bool:
    room_id = status.get("room_id")
    if not room_id:
        raise MobilePlaybackError("The connected mobile room has no room ID.")
    controller_user_id = _positive_int(controller_user_id, "controller_user_id")
    version = int(time.time_ns() // 1_000_000)
    playlist = {
        "commandType": "REPLACE",
        "version": [{"userId": controller_user_id, "version": version}],
        "anchorSongId": "",
        "anchorPosition": -1,
        "randomList": [str(song_id)],
        "displayList": [str(song_id)],
    }
    data = _response_data(
        request(
            _url(SYNC_LIST_PATH),
            {
                "roomId": room_id,
                "playlistParam": json.dumps(playlist, separators=(",", ":")),
            },
        ),
        "playlist sync",
    )
    if data.get("result") is not True:
        raise MobilePlaybackError("NetEase did not accept the mobile playlist sync.")
    return True


def play_song_on_mobile(
    request: Request, song_id: Any, controller_user_id: Any
) -> dict[str, Any]:
    song_id = _positive_int(song_id, "song_id")
    before = _require_connected(request)
    playlist_sync_accepted = _sync_single_song_playlist(
        request,
        before,
        song_id=song_id,
        controller_user_id=controller_user_id,
    )
    command = _send_command(
        request,
        before,
        command_type="GOTO",
        play_status="PLAY",
        target_song_id=song_id,
        progress_ms=0,
    )
    after = get_mobile_player_status(request)
    verified = bool(after["connected"] and after["current_song_id"] == song_id)
    return {
        **command,
        "playlist_sync_accepted": playlist_sync_accepted,
        "requested_song_id": song_id,
        "status": after,
        "verified": verified,
        "verification": (
            "connected_status_reports_requested_song"
            if verified
            else "command_accepted_but_current_song_not_exposed_or_not_yet_updated"
        ),
    }


def control_mobile_player(
    request: Request, action: Any, progress_ms: Any = None
) -> dict[str, Any]:
    if not isinstance(action, str) or action not in ALLOWED_ACTIONS:
        raise ValueError("action must be one of: play, pause, seek.")
    if action == "seek":
        if progress_ms is None:
            raise ValueError("progress_ms is required for seek.")
        progress = _non_negative_int(progress_ms, "progress_ms")
        command_type = "seek"
        play_status = "PLAY"
    else:
        if progress_ms is not None:
            raise ValueError("progress_ms is only valid for seek.")
        progress = 0
        command_type = "PLAY" if action == "play" else "PAUSE"
        play_status = command_type
    status = _require_connected(request)
    current_song_id = status.get("current_song_id") or 0
    command = _send_command(
        request,
        status,
        command_type=command_type,
        play_status=play_status,
        target_song_id=current_song_id,
        progress_ms=progress,
    )
    return {**command, "action": action, "status": get_mobile_player_status(request)}


def end_mobile_player(request: Request) -> dict[str, Any]:
    status = get_mobile_player_status(request)
    if not status["in_room"] or not status["room_id"]:
        return {"accepted": True, "ended": False, "already_ended": True, "status": status}
    data = _response_data(
        request(_url(END_PATH), {"roomId": status["room_id"]}), "room end"
    )
    ended = data.get("success") is True
    if not ended:
        raise MobilePlaybackError("NetEase did not confirm that the mobile room ended.")
    return {
        "accepted": True,
        "ended": True,
        "already_ended": False,
        "status": get_mobile_player_status(request),
    }
