---
name: netease-music-companion
description: Uses a connected NetEase Music MCP server to understand a user's own recommendations, recent and long-term listening context, playlists, and podcasts, and to curate or safely change playlists when the user asks. Use for NetEase Cloud Music discovery, daily recommendations, listening analysis, playlist curation or account changes, and optional playback when the corresponding MCP tools are available.
---

# NetEase Music Companion

Use the connected NetEase Music MCP server as the data and execution layer. The agent supplies the interpretation: what to read, what the listening context means, which songs belong together, how the sequence should flow, and whether the user's request actually includes an account change.

Tool names may be namespaced by the client. Match the canonical tool name and schema rather than assuming a vendor-specific prefix.

## 1. Establish the capability before acting

1. Discover the connected MCP tools.
2. If the NetEase Music tools are absent, say that the MCP server is not connected. Do not invent music data or pretend an account action succeeded.
3. If tools are present, call `get_netease_login_status` before account-specific work when login state is not already known in the current conversation.
4. Never ask the user to paste a NetEase cookie, CSRF value, OAuth token, Bearer token, or MCP password into chat.

The current server is designed for one private owner per deployment. Do not treat one deployment as a multi-user NetEase account service.

## 2. Recover login through the server

If the account is not authenticated, or a music call returns `NETEASE_AUTH_EXPIRED`:

1. Call `start_netease_qr_login`.
2. Prefer the returned short-lived `login_url` when the client can open it. Otherwise show the returned QR image or QR URL.
3. Ask the user only for the real human action: scan and confirm in the official NetEase Music app, including any official security verification shown by the login page.
4. Continue the same login attempt with `check_netease_qr_login`.
5. On `confirmed`, resume the original task. The server persists the session; do not request cookies or redeployment.

Handle explicit states literally:

- `waiting` or `scanned`: the login attempt is still in progress.
- `verification_required`: direct the user back to the same login page for the official verification flow.
- `expired`: start one fresh QR login attempt.
- `additional_security_verification_required`: stop the current attempt and explain that the upstream login flow cannot continue automatically.
- `upstream_unknown`: report the unknown upstream state and do not loop indefinitely.

## 3. Read only the context the task needs

For daily curation, a strong default context is:

- `daily_recommend`: today's candidate pool.
- `get_play_history`: longer-term preference signal. Use the all-time view when long-term taste is relevant.
- `get_recent_plays`: recent listening state and, when present, local-time context.
- `get_song_details`: only when richer metadata is needed to decide or explain.

Do not fetch every available tool "just in case." Expand only when the user's request needs more evidence.

Preserve data semantics:

- Aggregated play counts are not individual listening events.
- Missing timestamps, completion state, device data, program numbers, or private listening metrics must remain unknown.
- `played_at_local`, when present, can inform recent context; do not manufacture it when absent.
- A platform recommendation is a candidate, not proof that the user likes the song.

When the user asks for a summary or curation, prefer concise patterns and conclusions over dumping raw listening history back into the chat.

## 4. Curate as an experience, not a shuffled list

For a curation request:

1. Extract the user's explicit constraints: activity, mood, energy, length, exclusions, familiarity, language, public/private intent, and whether they want the playlist saved.
2. Use the requested source pool. If the user says "from today's recommendations," stay inside `daily_recommend` unless they explicitly ask to broaden discovery.
3. Use long-term history as a coordinate and recent listening as context, not as a mechanical popularity score.
4. Choose songs for a coherent arc. Consider entry, transitions, density, vocal/instrumental contrast, emotional peak, release, and ending.
5. If no size is specified, prefer a focused playlist rather than exhausting the source pool.
6. Explain the theme and sequence at the level useful to the user. Do not invent musical properties that are not supported by the available metadata or the model's reliable knowledge.

A good result answers both "why these songs?" and "why this order?"

## 5. Separate curation from account writes

A request to analyze, recommend, compare, or draft a playlist does not automatically authorize writing to the account.

Only use a write tool when the user's request clearly includes the corresponding account change and the tool is actually exposed by the connected server. Follow the client's normal write-confirmation mechanism if it has one.

If the deployment is read-only and the relevant write tool is absent:

- complete the analysis or curation normally;
- state clearly that the result was not written to NetEase;
- do not claim that a playlist was created or modified.

### Preferred write path for a curated playlist

When the user wants the curation saved and `create_curated_playlist` is available:

1. Finalize the name, description, privacy, and exact ordered `song_ids` before calling the tool.
2. Default to a private playlist unless the user explicitly asks for a public one.
3. Generate one stable `idempotency_key` for this exact intended creation. Reuse it only if retrying the same semantic action with the same arguments.
4. Call `create_curated_playlist` once.
5. Read the returned post-write verification. If the server reports success, use its verified result. If the result is partial, unknown, or failed, say so explicitly.
6. Use `get_playlist_songs` only when an additional readback is materially useful; do not add redundant verification calls without a reason.

Do not decompose a high-level curated-playlist creation into multiple lower-level writes when `create_curated_playlist` already covers the requested operation and verification.

### Other playlist changes

Before modifying an existing playlist:

- identify the exact target playlist;
- distinguish playlists the user owns from playlists they merely follow;
- change only what the request includes;
- preserve track order unless the request includes reordering;
- reuse an idempotency key only for a retry of the same intended operation.

Never turn a failed or ambiguous write into an automatic retry loop.

## 6. Failure paths

Use the server's error semantics instead of guessing.

- `NETEASE_AUTH_EXPIRED`: recover through the QR login flow.
- `NETEASE_REQUEST_REJECTED`: the session may still be valid; report the rejected upstream request rather than forcing a relogin unless login status proves authentication failed.
- Missing write tools: treat the deployment as read-only or stale until proven otherwise. Do not simulate success.
- A tool is expected but absent after a server change: refresh/reconnect the MCP client so it reloads tool definitions and scopes.
- Upstream/API failure: explain the bounded failure and stop after a reasonable retry only when the failure is clearly transient.
- Incomplete data: preserve the unknown instead of filling it with a plausible guess.

## 7. Podcasts remain read-oriented

Use podcast tools for discovery, subscriptions, episode/program metadata, and recent podcast context. Keep public statistics separate from personal listening data.

Do not infer subscription writes, likes, comments, downloads, playback progress, or other account actions that the server does not expose.

## 8. Optional playback is capability-gated

Playback tools are optional. Use them only when they are present in the current tool list.

For Mac playback, a safe specified-song sequence is:

1. `search_song` to obtain an exact numeric song ID.
2. `play_song` with that ID.
3. Report only the playback state the tool actually reads back. Do not claim the current track ID was verified when the client cannot expose it.

Mac playback only controls the official NetEase Music app on the same Mac as the MCP runtime. A remote Linux/hosted deployment cannot control an unrelated local Mac.

iPhone "Listen Together" tools use a separate purpose-limited controller account when enabled. Follow the exposed tool schemas and status readbacks; do not treat request acceptance as proof that the phone is already playing.

## 9. Response contract

When a task finishes, make the state unambiguous:

- what evidence was read;
- the musical or listening-context conclusion;
- what was actually written, if anything;
- whether the write was verified;
- any material upstream or capability limitation.

Do not expose credentials, raw secrets, or unnecessary private listening records.

## Core tool map

Session:
`get_netease_login_status`, `start_netease_qr_login`, `check_netease_qr_login`, `logout_netease`.

Music context:
`daily_recommend`, `get_play_history`, `get_recent_plays`, `search_song`, `get_song_details`.

Playlist reads:
`list_my_playlists`, `get_playlist_songs`.

High-level curation write:
`create_curated_playlist`.

Other account writes may include:
`create_playlist`, `update_playlist`, `add_to_playlist`, `remove_from_playlist`, `reorder_playlist_tracks`, `like_song`, cover updates, interaction-note tools, and `undo_operation`.

Podcast and optional playback tools should be discovered from the connected server because their availability is capability-dependent.
