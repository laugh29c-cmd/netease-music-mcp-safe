import json
import unittest

import mobile_playback


def status_response(
    *,
    in_room=True,
    status="CONNECTED",
    users=2,
    song_id=None,
    another_device=False,
    room_id="room-123",
):
    room = {
        "roomId": room_id,
        "roomUsers": [{"userId": index + 1} for index in range(users)],
    }
    if song_id is not None:
        room["matchPlayInfo"] = {"songId": song_id}
    return {
        "code": 200,
        "data": {
            "inRoom": in_room,
            "status": status,
            "roomInfo": room if in_room else None,
            "anotherDeviceInfo": {"device": "iphone"} if another_device else None,
        },
    }


class FakeRequest:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, data):
        self.calls.append((url, data))
        if not self.responses:
            raise AssertionError(f"Unexpected request: {url}")
        return self.responses.pop(0)


class MobilePlaybackTests(unittest.TestCase):
    def test_status_does_not_treat_room_creation_as_phone_connection(self):
        result = mobile_playback.normalize_status_response(
            status_response(status="NOT_CONNECTED", users=1)
        )
        self.assertTrue(result["in_room"])
        self.assertFalse(result["connected"])
        self.assertEqual(result["connection_state"], "waiting_for_iphone")
        self.assertFalse(result["current_song_id_verified"])

    def test_start_creates_native_room_and_builds_fixed_official_invite(self):
        request = FakeRequest(
            [
                status_response(in_room=False, status="", users=0),
                {
                    "code": 200,
                    "data": {"roomInfo": {"roomId": "room with spaces"}},
                },
                {
                    "code": 200,
                    "data": {"joinable": True, "status": "AVAILABLE"},
                },
                status_response(status="NOT_CONNECTED", users=1),
            ]
        )
        result = mobile_playback.start_mobile_player(request, 29816860, 12345)
        self.assertTrue(result["accepted"])
        self.assertFalse(result["room_reused"])
        self.assertEqual(result["requested_song_id"], 29816860)
        self.assertEqual(
            result["invite_url"],
            "https://st.music.163.com/listen-together/share/?songId=29816860&roomId=room+with+spaces&inviterId=12345",
        )
        self.assertTrue(request.calls[1][0].endswith("/room/create"))
        self.assertEqual(request.calls[1][1], {"refer": "songplay_more"})

    def test_join_accepts_only_official_invite_and_replaces_old_room(self):
        request = FakeRequest(
            [
                status_response(status="NOT_CONNECTED", users=1, room_id="old-room"),
                {"code": 200, "data": {"success": True}},
                {
                    "code": 200,
                    "data": {"roomInfo": {"roomId": "new-room"}},
                },
                status_response(room_id="new-room"),
            ]
        )
        result = mobile_playback.join_mobile_player(
            request,
            "https://st.music.163.com/listen-together/share/index.html?"
            "songId=29816860&roomId=new-room&inviterId=12345",
        )
        self.assertTrue(result["accepted"])
        self.assertTrue(result["ended_previous_room"])
        self.assertTrue(result["status"]["connected"])
        self.assertEqual(request.calls[1][1], {"roomId": "old-room"})
        self.assertEqual(
            request.calls[2][1],
            {
                "refer": "inbox_invite",
                "roomId": "new-room",
                "inviterId": 12345,
            },
        )

    def test_invite_parser_rejects_non_netease_urls(self):
        for invalid in (
            "http://st.music.163.com/listen-together/share/?roomId=x&inviterId=1",
            "https://example.com/listen-together/share/?roomId=x&inviterId=1",
            "https://st.music.163.com/song?id=1",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                mobile_playback.parse_mobile_invite_url(invalid)

    def test_play_requires_real_phone_connection_before_sending_command(self):
        request = FakeRequest([status_response(status="NOT_CONNECTED", users=1)])
        with self.assertRaisesRegex(
            mobile_playback.MobilePlaybackError, "MOBILE_IPHONE_NOT_CONNECTED"
        ):
            mobile_playback.play_song_on_mobile(request, 29816860, 12345)
        self.assertEqual(len(request.calls), 1)

    def test_play_sends_only_fixed_goto_payload_and_reports_truthful_readback(self):
        request = FakeRequest(
            [
                status_response(song_id=186016),
                {"code": 200, "data": {"result": True}},
                {"code": 200, "data": {"result": True}},
                {"code": 200, "data": {"success": True}},
                status_response(song_id=29816860),
            ]
        )
        result = mobile_playback.play_song_on_mobile(request, 29816860, 12345)
        playlist = json.loads(request.calls[1][1]["playlistParam"])
        self.assertEqual(playlist["displayList"], ["29816860"])
        self.assertEqual(playlist["version"][0]["userId"], 12345)
        command_call = request.calls[2]
        payload = json.loads(command_call[1]["commandInfo"])
        self.assertEqual(
            {key: payload[key] for key in ("commandType", "playStatus", "formerSongId", "targetSongId", "progress")},
            {
                "commandType": "GOTO",
                "playStatus": "PLAY",
                "formerSongId": 186016,
                "targetSongId": 29816860,
                "progress": 0,
            },
        )
        self.assertTrue(result["accepted"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["requested_song_id"], 29816860)
        self.assertEqual(result["status"]["current_song_id"], 29816860)

    def test_accepted_command_is_not_reported_verified_without_song_readback(self):
        request = FakeRequest(
            [
                status_response(song_id=None),
                {"code": 200, "data": {"result": True}},
                {"code": 200, "data": {"result": True}},
                {"code": 200, "data": {"success": True}},
                status_response(song_id=None),
            ]
        )
        result = mobile_playback.play_song_on_mobile(request, 29816860, 12345)
        self.assertTrue(result["accepted"])
        self.assertTrue(result["playlist_sync_accepted"])
        self.assertFalse(result["verified"])
        self.assertIn("not_exposed", result["verification"])

    def test_control_actions_are_allowlisted_and_seek_requires_progress(self):
        with self.assertRaises(ValueError):
            mobile_playback.control_mobile_player(lambda *_: {}, "next")
        with self.assertRaises(ValueError):
            mobile_playback.control_mobile_player(lambda *_: {}, "seek")

        request = FakeRequest(
            [
                status_response(song_id=29816860),
                {"code": 200, "data": {"result": True}},
                {"code": 200, "data": {"success": True}},
                status_response(song_id=29816860),
            ]
        )
        result = mobile_playback.control_mobile_player(request, "seek", 42_000)
        payload = json.loads(request.calls[1][1]["commandInfo"])
        self.assertEqual(payload["commandType"], "seek")
        self.assertEqual(payload["progress"], 42_000)
        self.assertEqual(result["action"], "seek")

    def test_positive_integer_validation_rejects_strings_and_booleans(self):
        for invalid in (0, -1, True, "29816860", 2.5):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                mobile_playback.build_invite_url(invalid, "room", 1)

    def test_end_is_idempotent_and_uses_current_room_only(self):
        absent = FakeRequest([status_response(in_room=False, status="", users=0)])
        result = mobile_playback.end_mobile_player(absent)
        self.assertTrue(result["already_ended"])

        request = FakeRequest(
            [
                status_response(),
                {"code": 200, "data": {"success": True}},
                status_response(in_room=False, status="", users=0),
            ]
        )
        result = mobile_playback.end_mobile_player(request)
        self.assertTrue(result["ended"])
        self.assertEqual(request.calls[1][1], {"roomId": "room-123"})


if __name__ == "__main__":
    unittest.main()
