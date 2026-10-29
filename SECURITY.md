# Security Policy

This is a personal, independent open-source project. Each deployment owner is responsible for
protecting the credentials and account configured for that deployment.

## Report issues without secrets

- Never include a real NetEase Cookie, MCP Bearer token, OAuth password, access/refresh token,
  private playlist data, personal account ID, or raw operation log in a public GitHub issue.
- Security problems that can be described without sensitive data may be reported through a GitHub
  issue. Redact account-specific values and use synthetic reproduction data.
- This repository does not publish a private security email or response-time SLA. Do not post a
  secret publicly in order to request private contact.

## If a credential was exposed

Treat it as compromised. Replace the deployment's `MCP_ACCESS_TOKEN` and `MCP_OAUTH_PASSWORD`,
invalidate or renew the exposed NetEase account session/Cookie through account controls, and remove
the secret from logs, screenshots, issue text, and deployment history where possible.

## Deployment boundary

Current architecture is **one deployment → one private owner**. Normal music and account tools use
one primary NetEase session. When native iPhone control is enabled, the same process and SQLite file
may hold one additional controller session whose only purpose is to join or host Listen Together rooms; it
must be a different NetEase account from the daily account on the iPhone. This bounded second
session is not per-user tenancy. OAuth and Bearer authentication control access to the deployment;
they do not provide separate NetEase logins for different MCP users. Share the repository, not a
private deployment's credentials. Other users should deploy their own instance with their own
secrets.

The mobile join tool accepts only `https://st.music.163.com/listen-together/share...` invitations
or fixed-format `https://163cn.tv/...` NetEase short links. Short-link resolution disables inherited
proxy settings, permits one official redirect target, and rejects arbitrary hosts before any fetch.

The SQLite file, WAL/SHM files, and backups may contain allowlisted `MUSIC_U` and `__csrf` fields for
the primary session and optional controller session. Protect persistent-volume and backup access as
credential access. Neither session is printed to logs or returned through MCP tools. This personal
single-instance deployment does not add a second database-encryption key; service or platform
administrators who can read both the volume and process environment are inside the deployment's
trusted administrative boundary.

The temporary browser QR page loads only NetEase-operated resources needed for an official
interactive security challenge: the Yidun loader from `cstaticdun.126.net` and the device
fingerprint script from `st.music.163.com`, with a narrowly scoped page-specific CSP. The challenge
proof and device token stay in the in-memory QR attempt request path; they are not logged, returned
through MCP, or written to SQLite. This integration does not automate or bypass the challenge.
