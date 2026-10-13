# SYNTH

A real-time voice channel web application inspired by Discord, built with a cyberpunk aesthetic. Create servers, join voice channels, and talk with others — all in the browser.

![Python](https://img.shields.io/badge/Python-3.13-blue)
![Flask](https://img.shields.io/badge/Flask-3.1-green)
![React](https://img.shields.io/badge/React-19-61dafb)
![LiveKit](https://img.shields.io/badge/LiveKit-WebRTC-purple)
![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-brightgreen)

## Try this on

https://synthapp.io/

## Features

- **Voice Channels** — Real-time voice chat powered by LiveKit (WebRTC)
- **Servers & Channels** — Create and manage servers with multiple voice channels
- **Role-Based Access Control** — Server-scoped roles with granular permissions
- **User Presence** — Live online/offline status tracking
- **JWT Authentication** — Secure token-based auth with bcrypt password hashing
- **Swagger API Docs** — Interactive API documentation at `/docs`
- **Cyberpunk UI** — Animated neon theme with glassmorphism, waveform visualizations, and glow effects

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, React Router 7, Tailwind CSS 4, Vite 7 |
| Backend | Flask 3.1, flask-smorest, Marshmallow 4 |
| Database | MongoDB (pymongo 4 / flask-pymongo) |
| Auth | flask-jwt-extended, bcrypt |
| Voice | LiveKit (livekit-api + @livekit/components-react) |
| Deployment | Docker, Gunicorn, Render |

## Architecture

```
frontend/          React SPA (Vite)
backend/
  app/
    adapters/      LiveKit adapter (port/adapter pattern)
    middleware/     JWT auth middleware
    models/        MongoDB document models
    ports/         Media server interface
    routes/        REST API blueprints
    services/      Business logic layer
```

The backend uses a **port/adapter pattern** for the media server integration, making it possible to swap LiveKit for another WebRTC provider without changing business logic.

## Getting Started

### Prerequisites

- Python 3.13+
- Node.js 20+
- MongoDB (local or [Atlas](https://www.mongodb.com/atlas))
- [LiveKit Server](https://docs.livekit.io/home/self-hosting/local/) (local dev) or [LiveKit Cloud](https://cloud.livekit.io) (production)

### Backend Setup

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file in `backend/`:

```env
FLASK_ENV=development
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret
MONGO_URI=mongodb://localhost:27017/synth
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=devsecret
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_HTTP_URL=http://localhost:7880
```

Run the backend:

```bash
python run.py
```

The API will be available at `http://localhost:5000` with Swagger docs at `http://localhost:5000/docs`.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:5173` and proxies API requests to the backend.

### LiveKit (Local Development)

Start a local LiveKit server with Docker:

```bash
docker run --rm -p 7880:7880 -p 7881:7881 -p 7882:7882/udp \
  -e LIVEKIT_KEYS="devkey: devsecret" \
  livekit/livekit-server
```

## Running Tests

```bash
cd backend
python -m pytest test_auth.py test_servers.py test_roles.py test_channels.py test_voice.py test_presence.py -v
```

107 tests covering auth, servers, roles, channels, voice, and presence.

The isolated role, member privacy, realtime, password, and voice regression suites use an
in-memory MongoDB mock and do not connect to the configured database:

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

Chat reconnect, snapshot ordering, and session revocation tests use Node's built-in test runner:

```bash
cd frontend
node --test tests/*.test.mjs
npm run build
```

Member lists and presence streams require current server membership and expose
only ID, username, avatar, online status, and last-seen time. Streams recheck
access before sending subsequent updates and close when access is revoked.

Channel and DM streams share a MongoDB `realtime_streams` journal across workers.
Each worker polls its subscribed topics every 0.5 seconds. Atomic appends retain
the last 128 notifications per topic, with SSE IDs supporting reconnect replay.
Message notifications store IDs and resolve current content when delivered;
deleted or superseded text is not retained in the journal. Clients reload chat
history after connecting or when the replay window or subscriber queue overflows,
and buffer incoming updates while loading. The journal's revision documents must
persist for stable reconnect cursors; do not apply a TTL index to this collection.
Upgrade all backend workers and the frontend together to enable shared delivery
and history recovery.

Channel history uses creation timestamp plus message ID ordering so pagination
does not skip messages created in the same millisecond. A history cursor must
belong to the requested channel: malformed cursors return 400, and missing,
deleted, or foreign-channel cursors return 404. Pages remain capped at 50
messages and are returned in chronological order. The frontend merges older
pages and live messages without duplicate IDs or replacing newer edits with
stale page content.

Switching text channels mounts a fresh panel for the current user/channel.
History, pagination, sends, edits, and deletes from an earlier panel cannot
alter the selected channel's messages, input, errors, or loading state. Deleted
message IDs stay excluded from delayed pages and HTTP echoes, and messages
changed while a history reload is pending survive its older snapshot.

Authenticated resource URLs validate and normalize ObjectIds before database
lookups and permission checks. Malformed resource IDs return JSON 404 responses;
valid uppercase IDs share the same resources and realtime topics as lowercase
IDs. Invite codes, voice participant identities, and track IDs remain opaque
strings. DM validation and pagination retain their existing error contracts.

Presence runs for the authenticated application session. Logout stops heartbeat
timers and dispatches offline with the outgoing token before clearing local
credentials, without waiting for the network. Every presence mount has a fresh
UUID lease scoped to its JWT; closing a lease prevents delayed heartbeats from
bringing it back online. Concurrent worker updates use an account revision and
session-version check. Other active tabs or logins keep the user online, and
their leases cannot be closed by cleanup from an earlier session. Expired and
password-revoked leases are pruned during updates; storage is capped at 256
leases per account. Older clients without a lease ID retain their existing
heartbeat/offline behavior. If offline delivery fails, the existing 60-second
heartbeat timeout still applies.

DM message mutations verify the conversation and sender during the database
write. History cursors belong to the requested conversation and use timestamp
plus message ID ordering to preserve messages created in the same millisecond.
Conversation pages accept nonnegative offsets and limits from 1 to 50. Read
receipts identify the messages actually marked read; batches over 500 messages
trigger a history reload. Internal receipt markers are not included in responses.
Switching DM conversations creates a fresh panel so pending requests from the
previous conversation cannot change the selected chat's messages or input.

Password resets consume the exact, unexpired reset token in the same atomic
database update that changes the password and increments the account's session
version. Login tokens carry the version checked with the password; every
authenticated request and open SSE stream checks it against the current account.
Resetting a password invalidates earlier logins and voice grants. Accounts and
tokens created before this upgrade are treated as version zero until their next
reset. The frontend returns to sign-in when the current session receives a 401,
and ignores delayed rejections belonging to an earlier login.

Voice joins create a fresh opaque participant identity and a 60-second initial
join token. The latest grant for each user/channel is stored in `voice_sessions`.
Leaving a server or voice channel, a voice kick, a password reset, or deleting a
server/channel revokes the relevant grants and removes participants through the
media API. Failed removals stay in `voice_revocations` for retry. Each worker runs
an independent access check every two seconds, including rooms with no presence
subscribers; it checks current membership, account version, channel type, and
join permission, and removes unrecognized or revoked identities. One failed room
operation does not stop checks in other rooms. Disconnected grants that lose
access are also revoked; restoring access requires a fresh join. Provider calls have a five-second
timeout, so an outage or a long sweep can delay enforcement.

LiveKit Cloud removals pass an explicit token revocation cutoff to also reject
recently refreshed cached tokens. Self-hosted LiveKit does not revoke cached
tokens on removal: a cached token can briefly reconnect until the access check
removes it. The initial token's short expiry does not terminate active sessions
or prevent reconnects using provider-refreshed tokens. See [LiveKit token
revocation](https://docs.livekit.io/frontends/reference/tokens-grants/#token-revocation).
Upgrade all backend workers and the frontend together, install the updated
LiveKit dependencies, and have existing voice users rejoin: legacy participants
whose identity is an account ID are removed by the new access check.

Invite acceptance reserves a use with one atomic database update that checks
the exact invite, current expiry, and use limit. Membership insertion is also
conditional, so duplicate joins refund their extra reservation. Exhaustion
cleanup waits for pending acceptances to finish. An uncertain database failure
keeps the reserved use spent to protect the limit; an interrupted worker can
also leave a reservation pending. Limits and expiry values must be nonnegative
integers (`0` means unlimited uses or no expiry). Private reservation counters
are not included in invite responses.

Server deletion marks the server inaccessible before cascading through channels,
messages, invites, scoped roles and assignments, voice grants, and channel event
histories. It evicts cached presence, revokes voice tokens, and deletes media
rooms. Deletion can be retried by the original owner. Worker sweeps run at
startup and every 30 seconds to retry database/media failures and remove late
writes; old orphan records are recovered from their server and channel IDs.
Other servers, accounts, friendships, and DMs are preserved. Cleanup failures
can delay physical removal after the API returns success; access remains denied.
Names remain reserved until the parent document is physically removed.

The `server_deletions` collection retains only deleted server/owner IDs and
channel IDs so delayed writes and recreated media rooms can be cleaned on later
passes. Do not expire these records. New channel messages retain an internal
server ID for cleanup; it is excluded from the API response. Legacy messages
whose server and channel references are both missing cannot be attributed to a
specific server automatically. Upgrade all backend workers together to enforce
invite limits and deletion boundaries consistently.

Role definitions and default roles belong to individual servers. On the first
startup after upgrading from global roles, the backend replaces the global name
index with a unique `(server_id, name)` index and creates each server's built-in
roles from the code defaults. It remaps existing member assignments to these
local roles and copies assigned custom roles into the servers that use them.
Shared default-role settings are reset to `member`; later local settings persist
across restarts. Role IDs change during migration, so API clients must fetch
their server's role list again. The migration is safe to retry after interruption.

Legacy definitions with no server scope are retained for inspection and cannot
grant permissions or be accessed through the roles API. Unassigned custom roles
cannot be attributed to a server and must be recreated locally. Existing custom
permissions and elevated assignments are preserved, so prior unauthorized grants
cannot be distinguished automatically from legitimate ones. Deploy this version
to all backend workers together; old workers do not enforce these boundaries.

## Deployment

The project deploys as a **single Docker container** — the frontend is built at image build time and served by Flask alongside the API.

### Docker

```bash
docker build -t synth .
docker run -p 5000:5000 --env-file backend/.env synth
```

### Render

1. Push to GitHub
2. Create a new **Web Service** on [Render](https://render.com), connect the repo
3. Render auto-detects the Dockerfile
4. Set environment variables:
   - `MONGO_URI` — your MongoDB Atlas connection string
   - `LIVEKIT_API_KEY` — from [LiveKit Cloud](https://cloud.livekit.io)
   - `LIVEKIT_API_SECRET` — from LiveKit Cloud
   - `LIVEKIT_URL` — `wss://your-project.livekit.cloud`
   - `LIVEKIT_HTTP_URL` — `https://your-project.livekit.cloud`
   - `FRONTEND_URL` — `https://synthapp.io` for password-reset email links

A `render.yaml` blueprint is included for one-click deploy.

The public app is hosted at `https://synthapp.io`. Production frontend builds
use `https://synthapp.io/api` for API requests and SSE streams and
`https://synthapp.io` for invite links. Production backend configuration defaults
password-reset email links to the same website; `FRONTEND_URL` can override it.
For an existing Render service, set `FRONTEND_URL=https://synthapp.io` in its
environment and redeploy. Rebuild and release the desktop app so installed
clients receive the new API and invite URLs.

### Desktop Releases (Tauri)

Desktop installers are built and published from Git tags via GitHub Actions.

#### One-time setup

1. Generate updater signing keys (from `frontend/`):

```bash
npm run tauri signer generate -- -w ~/.tauri/synth.key
```

2. Add these repository secrets in GitHub:
  - `TAURI_SIGNING_PRIVATE_KEY` (paste the raw base64 content from `~/.tauri/synth.key`; do not decode it)
  - `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` (password used when generating the key)

3. Copy the generated public key into `frontend/src-tauri/tauri.conf.json`:
  - `plugins.updater.pubkey`

#### Releasing a new desktop version

From `frontend/`:

```bash
npm run release:patch   # or release:minor / release:major
```

This synchronizes versions across:
- `frontend/package.json`
- `frontend/src-tauri/tauri.conf.json`
- `frontend/src-tauri/Cargo.toml`

Then commit and tag manually:

```bash
git add frontend/package.json frontend/package-lock.json frontend/src-tauri/tauri.conf.json frontend/src-tauri/Cargo.toml
git commit -m "chore: release vX.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

Pushing the `v*` tag triggers `.github/workflows/release.yml`, which builds for Windows, macOS (Intel + ARM), and Linux, then publishes artifacts and updater metadata (`latest.json`) to GitHub Releases.

#### Download page

The app exposes a public desktop download page at `/download`.
It reads latest assets from `https://api.github.com/repos/furkannehir/synth/releases/latest`.

Desktop invite links use the public website configured by `VITE_WEB_URL`, rather
than the desktop WebView's local origin. The production frontend environment
sets it to `https://synthapp.io`. Set it to your frontend's public URL
before building for another deployment, then rebuild the frontend and desktop
installer. Browsers fall back to their current origin when the setting is absent;
desktop builds require an explicit website URL. For local desktop development,
set `VITE_WEB_URL` to the web frontend connected to the same API/database.
Displayed and copied links use the same URL, including when reusing cached invite
codes. Existing cached codes do not need to be regenerated for this fix.

Desktop sessions use native credential storage and automatic renewal, so closing
or updating the app preserves login while the session remains valid. Website
invites can open the installed app through `synthapp://invite/<code>`, and channel
messages and DMs render clickable web URLs. The app uses its own saved login for
invite handoff. Automatic browser handoff stays disabled until the new desktop
installer is released.

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `FLASK_ENV` | `development` or `production` | Yes |
| `SECRET_KEY` | Flask secret key | Yes |
| `JWT_SECRET_KEY` | JWT signing key | Yes |
| `FRONTEND_URL` | Backend website URL for password-reset emails; defaults to `https://synthapp.io` in production and localhost in development | No |
| `INVITE_DEFAULT_EXPIRES_HOURS` | Backend default invite TTL in hours when `expires_in_hours` is null (set `0` to disable default expiry) | No |
| `MONGO_URI` | MongoDB connection string | Yes |
| `LIVEKIT_API_KEY` | LiveKit API key | Yes |
| `LIVEKIT_API_SECRET` | LiveKit API secret | Yes |
| `LIVEKIT_URL` | LiveKit WebSocket URL | Yes |
| `LIVEKIT_HTTP_URL` | LiveKit HTTP API URL | Yes |
| `VITE_INVITE_CACHE_TTL_HOURS` | Frontend invite cache lifetime in hours (defaults to `24`) | No |
| `VITE_WEB_URL` | Public web frontend URL used for shared invite links; supplied in `.env.production`, required for desktop builds | Desktop |
| `VITE_API_URL` | Frontend API/SSE base URL; production uses `https://synthapp.io/api`, development uses the local backend | No |
| `VITE_DESKTOP_HANDOFF_ENABLED` | Build-time flag: `true` attempts opening Synth once on a valid browser invite preview; enable after releasing the protocol-capable desktop installer | No |

## License

This project is unlicensed — all rights reserved.
