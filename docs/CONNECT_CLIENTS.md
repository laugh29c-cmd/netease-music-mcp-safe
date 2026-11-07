# Connect MCP clients

This document describes the portable connection contract for clients other than the repository's already documented ChatGPT and Codex paths.

The server remains the authority for authentication, NetEase session persistence, tool schemas, validation, idempotency, audit data, and post-write verification. A client or Agent Skill should orchestrate those capabilities; it should not duplicate them.

## Connection contract

The MCP endpoint is:

```text
<deployment-origin>/mcp
```

The server uses Streamable HTTP.

There are two normal client classes:

| Client class | Recommended endpoint | Authentication |
| --- | --- | --- |
| Hosted/cloud agent | Public HTTPS `/mcp` | OAuth discovery / OAuth 2.1 + PKCE |
| Trusted local agent | Loopback or otherwise private `/mcp` | Bearer authentication supplied from a protected local helper or environment |

Do not put a NetEase cookie, MCP access token, OAuth password, or refresh token into a public skill, repository file, screenshot, or prompt template.

## Hosted agents

A hosted agent cannot safely read a local header helper or a local environment variable. For hosted clients, configure the server with its public HTTPS origin and OAuth password, then let the client use OAuth discovery.

The authorization boundary is the MCP server's OAuth flow:

- `netease.read` for music reads;
- `netease.session` for NetEase QR-session management;
- `netease.write` only when account writes are enabled;
- optional playback scopes only when those capabilities are enabled.

Changing from read-only to write mode does not silently upgrade an old refresh token. Refresh the tool definitions, disconnect/reconnect the client, and authorize the new scope.

## Trusted local agents

A local agent may connect to a loopback endpoint and supply the Bearer token through a protected local mechanism.

The repository's verified Codex path is documented in [CONNECT_CODEX.md](CONNECT_CODEX.md). Its helper reads the token at request time instead of copying the literal secret into Codex configuration.

Other local clients should follow the same principle when they support custom MCP headers: reference a protected secret source rather than committing the token to a project file.

## First connection

After the MCP client shows the tools:

1. Call `get_netease_login_status`.
2. If no valid NetEase session exists, call `start_netease_qr_login`.
3. Open the returned short-lived `login_url` when possible, or use the returned QR image/URL fallback.
4. Scan and confirm with the official NetEase Music app.
5. Continue the same attempt with `check_netease_qr_login` when the client is using the tool-based fallback.
6. Confirm at least one harmless read such as `list_my_playlists` or `daily_recommend`.

The QR flow persists the NetEase session in the server's SQLite store. A user should not have to paste a Cookie into the agent.

## Tool-catalog refresh

MCP clients can cache schemas.

Refresh/reconnect after any of these changes:

- a new tool is deployed;
- a tool input schema changes;
- `MCP_READ_ONLY` changes from `true` to `false`;
- a playback capability is enabled or disabled;
- OAuth scopes change.

If a client still shows removed fields or is missing newly enabled tools, treat the tool catalog as stale before assuming the server is broken.

## What "confirmed client" means

Do not label a client "confirmed" merely because it supports MCP or can parse `SKILL.md`.

A confirmed client should pass the representative journeys in [SMOKE_TESTS.md](SMOKE_TESTS.md) against a real deployment:

1. session/login and harmless music read;
2. recent/long-term listening analysis with correct data semantics;
3. one bounded playlist write with post-write verification when write mode is intentionally enabled.

The repository currently has established ChatGPT and Codex connection paths. Additional clients should remain "compatible in principle" until that real smoke test has been performed.

## Portable Agent Skill

The portable skill lives at:

```text
skills/netease-music-companion/SKILL.md
```

It intentionally uses only the portable `name` and `description` frontmatter plus plain Markdown instructions. The skill assumes the MCP server is already connected; it never embeds credentials or pretends that a marketplace is hosting the server.

For Agensi or another skill marketplace, package the skill as an orchestration layer and declare this MCP server as a prerequisite. The buyer should deploy or connect their own private instance rather than receive access to someone else's NetEase account.
