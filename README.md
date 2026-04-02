# SYNTH

A real-time voice channel web application inspired by Discord, built with a cyberpunk aesthetic. Create servers, join voice channels, and talk with others — all in the browser.

![Python](https://img.shields.io/badge/Python-3.13-blue)
![Flask](https://img.shields.io/badge/Flask-3.1-green)
![React](https://img.shields.io/badge/React-19-61dafb)
![LiveKit](https://img.shields.io/badge/LiveKit-WebRTC-purple)
![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-brightgreen)

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

A `render.yaml` blueprint is included for one-click deploy.

### Desktop Releases (Tauri)

Desktop installers are built and published from Git tags via GitHub Actions.

#### One-time setup

1. Generate updater signing keys (from `frontend/`):

```bash
npm run tauri signer generate -- -w ~/.tauri/synth.key
```

2. Add these repository secrets in GitHub:
  - `TAURI_SIGNING_PRIVATE_KEY` (or legacy `TAURI_PRIVATE_KEY`)
  - `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` (or legacy `TAURI_KEY_PASSWORD`)

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

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `FLASK_ENV` | `development` or `production` | Yes |
| `SECRET_KEY` | Flask secret key | Yes |
| `JWT_SECRET_KEY` | JWT signing key | Yes |
| `MONGO_URI` | MongoDB connection string | Yes |
| `LIVEKIT_API_KEY` | LiveKit API key | Yes |
| `LIVEKIT_API_SECRET` | LiveKit API secret | Yes |
| `LIVEKIT_URL` | LiveKit WebSocket URL | Yes |
| `LIVEKIT_HTTP_URL` | LiveKit HTTP API URL | Yes |

## License

This project is unlicensed — all rights reserved.
