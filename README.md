# Tracker backend

FastAPI backend running on a Raspberry Pi. GPIO button/LED state, MongoDB sessions,
and dashboard WebSocket updates share the backend as their source of truth.
The companion [frontend README](../tracker-frontend/README.md) covers the browser and Cloudflare route.

## Environment

From this directory, run `cp -n .env.example .env`, then edit `.env` with your existing
values. Keep real database credentials private. The template contains placeholders,
not a copy of your existing environment.

```dotenv
# Backend only. Keep database credentials out of the frontend.
# Replace with your existing MongoDB connection string.
MONGO_URI=mongodb://127.0.0.1:27017
# Database containing your existing user, categories, and sessions.
DB_NAME=tracker
# Existing category ObjectId or alias: GYRUS, TOYCON, CREATING, PIANISO.
# Aliases reference IDs in app/services/session_service.py.
SESSION_CATEGORY=PIANISO

# Optional application settings (defaults shown).
APP_NAME=Tracker
DEBUG=true

```

Pydantic loads `.env` relative to the working directory, so run commands from
`tracker-backend`. Restart the backend after changes. `MONGO_URI`, `DB_NAME`, and
`SESSION_CATEGORY` are required. `APP_NAME` and `DEBUG` are optional.
Host and port are Uvicorn command options, not application `.env` settings.

Startup expects a MongoDB user with email `test@test.com` and access to the Pi's GPIO.
Use your existing database and an existing category; the example does not seed data.
The current `create_user` script updates an existing user rather than creating one.

## Install and run

On the Raspberry Pi, from this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 4004
```

This binds port 4004 to all interfaces so a frontend on another computer can connect.
Use `http://<PI_LAN_IP>:4004` as that frontend's `API_PROXY_TARGET`. Run `hostname -I`
on the Pi to find its LAN address. Allow TCP 4004 from the frontend machine if a firewall blocks it.
If the frontend runs on this same Pi, you can bind to `127.0.0.1` instead and use
`API_PROXY_TARGET=http://127.0.0.1:4004`.

## Matching frontend and Cloudflare configuration

The frontend `.env` uses these server-side settings:

```dotenv
# Same machine as the backend; otherwise replace with http://<PI_LAN_IP>:4004.
API_PROXY_TARGET=http://127.0.0.1:4004
# Replace with your actual public frontend hostname; leave empty for LAN only.
DEV_ALLOWED_HOSTS=tracker.example.com
```

The frontend runs with `npm run dev -- --host 0.0.0.0` on port 5173. Its Vite proxy
forwards HTTP and WebSocket paths under `/api` unchanged to this backend on port 4004.
Do not append `/api/v1` to `API_PROXY_TARGET`.

Cloudflare's Service URL is `http://localhost:5173` if its connector runs on the
frontend machine, or `http://<FRONTEND_LAN_IP>:5173` otherwise. Leave the Path field
blank. Public visitors use `https://<YOUR_PUBLIC_HOSTNAME>`, and the frontend uses
that same origin for API requests and `wss` updates. No separate backend route is
needed. See [Cloudflare's Service URL instructions](https://developers.cloudflare.com/tunnel/setup/).

## Verify

```bash
curl http://127.0.0.1:4004/api/v1/health
```

Expected response: `{"status":"healthy"}`. API docs are at `http://<PI_LAN_IP>:4004/docs`.
From the frontend machine, also check `http://localhost:5173/api/v1/health` to verify
the proxy. The live dashboard WebSocket endpoint is `/api/v1/ws/dashboard/`.

WebSocket clients receive `status_update` on connection and `state_update` after
activity button presses. Sending `{"type":"ping"}` receives `{"type":"pong"}`
only on that connection. Failed or slow clients are removed without preventing
healthy clients from receiving updates. Restart the backend after changing the
WebSocket handler; refreshing the frontend alone does not load Python changes.

Run one Uvicorn worker: GPIO state and the WebSocket connection list live in that
process. Multiple workers would need shared messaging to broadcast to every client.

Run the backend connection checks without accessing GPIO or MongoDB:

```bash
python -m unittest discover -s tests -p 'test_dashboard_websocket.py' -v
```
