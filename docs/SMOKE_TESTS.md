# Cross-client smoke tests

These tests define the minimum evidence required before describing a client as confirmed for the portable NetEase Music Companion skill.

They are intentionally representative rather than exhaustive. The server's full Python test suite remains the source-level regression suite; this document verifies the real client → MCP → NetEase user journey.

## Acceptance rule

A client is **confirmed** only when all applicable steps below have been exercised against the intended MCP transport and authentication path.

Format compatibility, successful tool discovery, or a mocked server is not enough.

## Test-data discipline

- Use one private owner deployment.
- Keep secrets outside prompts and repository files.
- Start in read-only mode for discovery and analysis tests.
- Enable write mode only for the bounded write journey.
- Do not create repeated disposable playlists. The server has no verified playlist-delete operation.

For cross-client write verification, prefer one intentional private playlist creation and reuse the same `idempotency_key` with the exact same arguments when another client repeats that same semantic write. The first successful call may create the playlist; later exact retries should return the recorded result without creating duplicates.

Never reuse that key for a different playlist or changed arguments.

## Journey A — first run and harmless read

Goal: prove tool discovery, session recovery, and a normal read.

1. Connect the client to the intended `/mcp` endpoint.
2. Confirm the expected NetEase tools are visible.
3. Call `get_netease_login_status`.
4. If unauthenticated, run the QR flow:
   - `start_netease_qr_login`;
   - complete the real official NetEase scan/verification;
   - continue with `check_netease_qr_login` when using the tool fallback.
5. Call `daily_recommend` or `list_my_playlists`.
6. PASS only if the client receives real account-scoped data and no credential is exposed to the client.

Evidence to retain: client/version, transport, authentication mode, tool names discovered, final login state, and one redacted read result.

## Journey B — listening-context analysis

Goal: prove the agent uses the data with the correct semantics rather than merely calling tools.

Prompt the agent to analyze recent listening in the context of longer-term taste.

Expected minimum calls:

- `get_play_history`;
- `get_recent_plays`;
- optional `get_song_details` only when needed.

PASS requires all of the following:

- aggregated play counts are not described as timestamped events;
- missing timestamps remain unknown;
- recent context and long-term preference are distinguished;
- the answer summarizes patterns instead of dumping unnecessary raw history.

No account write is required for this journey.

## Journey C — curated playlist write and verification

Goal: prove one real high-level write path.

Preconditions:

- the deployment has persistent SQLite storage;
- `MCP_READ_ONLY=false`;
- the client has refreshed/reconnected and obtained `netease.write`;
- the user has intentionally authorized this one playlist creation.

Procedure:

1. Read `daily_recommend`, long-term play history, and recent plays.
2. Curate a small coherent playlist from the agreed candidate pool.
3. Freeze the exact:
   - name;
   - description;
   - privacy;
   - ordered song IDs;
   - one 8–100 character idempotency key.
4. Call `create_curated_playlist` once.
5. Read the returned post-write verification.
6. If another client is validating the same exact semantic write, repeat the call with exactly the same arguments and idempotency key. It should resolve to the recorded operation rather than create a second playlist.
7. Use `get_playlist_songs` only if an additional readback is needed to resolve uncertainty.

PASS requires:

- one intended playlist exists, not a duplicate swarm;
- final metadata and ordered songs are verified by the server or an explicit readback;
- a partial/unknown result is not reported as success.

## Current receipt — 2026-11-07 ChatGPT connector

A fresh read-path smoke was performed from the current ChatGPT surface against the live private deployment.

- **Journey A: PASS for the read path.** `get_netease_login_status` returned an authenticated QR-login session with persistent storage configured, and `daily_recommend` returned real account-scoped recommendations.
- **Journey B: PASS.** `get_play_history` returned explicitly aggregated all-time play counts, while `get_recent_plays` returned a separate recent event stream with `played_at_local`, timezone, and bounded limitations. The two semantics were kept distinct.
- **Journey C: NOT VERIFIED on this ChatGPT connector.** The current tool catalog does not expose `create_curated_playlist` or the other playlist account-write tools. No write was attempted and no playlist was created for this smoke.

This is a surface-level result, not a product-capability downgrade: the server repository still contains its write capability contract. The current connector must expose the write tools and appropriate scope before Journey C can be promoted to PASS.

## Client matrix

The matrix records evidence, not marketing claims.

| Client | Intended path | Current status before skill-specific smoke | Promotion condition |
| --- | --- | --- | --- |
| ChatGPT Work/Web | public HTTPS + OAuth | **Fresh 2026-11-07 read-path receipt:** Journeys A–B PASS; Journey C NOT VERIFIED because write tools are not exposed on the current connector | Expose/authorize the bounded write path, then Journey C PASS |
| Codex app / CLI / IDE | loopback + protected Bearer helper | Existing project connection path; skill-specific smoke still needs a fresh receipt | Journeys A–C PASS on current deployment |
| Claude Code | Streamable HTTP MCP using its supported auth path | Candidate third client; **not verified** | Journeys A–C PASS without vendor-specific changes to the skill |

If Claude Code cannot complete the current server authentication path cleanly, record the exact first real failure. Do not add a compatibility wrapper to the server merely to make a marketing matrix green unless the failure proves a real interoperability defect in the server contract.

## Skill portability check

Before packaging:

- parent folder is `netease-music-companion`;
- `SKILL.md` frontmatter `name` matches that folder;
- frontmatter uses only `name` and `description`;
- the description contains clear trigger language;
- the body uses plain Markdown;
- no vendor-specific hooks, tool allowlists, absolute local paths, credentials, or private account data are embedded;
- tool names are canonical MCP tool names, not a single client's generated prefix.

Structural portability PASS is necessary but does not replace the real-client smoke tests above.

## Marketplace claim rule

Until the fresh matrix is complete, use conservative wording such as:

> Portable SKILL.md orchestration for a connected NetEase Music MCP deployment. Current repository paths cover ChatGPT and Codex; additional clients require their own MCP compatibility smoke test.

After all three clients pass, the listing may name those exact client/version combinations as confirmed.
