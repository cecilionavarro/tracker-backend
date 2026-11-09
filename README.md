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
activity button presses and session edits. Sending `{"type":"ping"}` receives `{"type":"pong"}`
only on that connection. Failed or slow clients are removed without preventing
healthy clients from receiving updates. Restart the backend after changing the
WebSocket handler; refreshing the frontend alone does not load Python changes.

Run one Uvicorn worker: GPIO state and the WebSocket connection list live in that
process. Multiple workers would need shared messaging to broadcast to every client.

## Editing sessions

The dashboard's session menu edits start time, end time, and category through
`PATCH /api/v1/sessions/{id}`; `GET /api/v1/categories` lists the choices, with the
tags already used for each category. Omitted fields stay unchanged. Times must not
be in the future, and the end must follow the start. Giving the running session an
end time clocks it out. After every edit the backend reloads the running session, so
the LED and the next button press match the edit.

## Counter buttons

Two buttons count instead of clocking in or out. Wire each like the activity buttons:
one leg to the GPIO pin, the other to any ground pin. No resistor is needed, because
the backend turns on the Pi's internal pull-up.

| Button | GPIO | Physical pin | Nearest ground |
| --- | --- | --- | --- |
| Pull-ups | 22 | 15 | 14 |
| Distractions | 23 | 16 | 20 |

Each pull-up press flashes the LED once, inverting it so the flash shows whether
the LED is on or off. Tap a set's reps right after doing them: taps less than 3 seconds
apart form one set, and 3 seconds after the last tap a double flash confirms it. A
distraction press double-flashes when it's saved. Each pull-up press stores one record in
the `pullups` collection, counted by day in Los Angeles time. A distraction press adds
one to the running session's `distractions` field. With no session running, the
press is ignored and the LED does not blink.

The dashboard shows both counts and has buttons to add or undo one. The same actions
are available without the hardware:

```bash
curl -X POST http://127.0.0.1:4004/api/v1/pullups
curl -X DELETE http://127.0.0.1:4004/api/v1/pullups/last
curl -X POST http://127.0.0.1:4004/api/v1/sessions/active/distractions
curl -X DELETE http://127.0.0.1:4004/api/v1/sessions/active/distractions
```

`GET /api/v1/pullups/stats` returns today's sets, the week's comparison with the
same point last week, the current streak, and all-time records. A set is presses
less than 3 seconds apart. Undo only removes today's most recent pull-up. Fix a past session's distractions from the
session's Edit dialog, which sends `distractions` through `PATCH /api/v1/sessions/{id}`.

## Calendar

`GET /api/v1/calendar?start=2026-10-26&days=7` returns each day's sessions as blocks,
split at midnight, with wall-clock minutes for placing them. It also returns markers:
distractions from the event log, one per pull-up set at its first tap, and notes.
Removing a distraction undoes its latest press; a count lowered in the Edit dialog,
which logs no event, keeps only the latest presses.

## Activity button assignments

Which category and tag each activity button on GPIO 2, 3, 4, and 27 clocks into is
stored in the `buttons` collection and changed from the dashboard's Buttons tab. The
first start copies the assignments from `app/hardware/pins.py`; after that, editing
the category or tags there has no effect, though the pin list still defines the wiring.
A change applies on the button's next press, without a restart, and an unassigned
button does nothing.

```bash
curl http://127.0.0.1:4004/api/v1/buttons
curl -X PATCH http://127.0.0.1:4004/api/v1/buttons/27 -H 'content-type: application/json' -d '{"category_id":null}'
```

## Categories, notes, and work log

Categories are managed through these endpoints; every change refreshes open dashboards:

```bash
curl http://127.0.0.1:4004/api/v1/categories?include_archived=true
curl -X POST http://127.0.0.1:4004/api/v1/categories -H 'content-type: application/json' \
  -d '{"label":"Reading","color":"#3987e5","tags":["fiction"],"tag_colors":{}}'
curl -X PATCH http://127.0.0.1:4004/api/v1/categories/<id> -H 'content-type: application/json' -d '{"active":false}'
curl -X DELETE http://127.0.0.1:4004/api/v1/categories/<id>
```

Names are unique regardless of case. Tags are stored lowercase with underscores.
Setting `active` to false archives a category: hidden from pickers, history kept.
Deleting is refused while any session uses the category, and both deleting and
archiving are refused for a category assigned to a Pi button; reassign the button first.

Notes live in the `notes` collection, one per entry, with the time it happened:

```bash
curl -X POST http://127.0.0.1:4004/api/v1/notes -H 'content-type: application/json' -d '{"text":"Fixed the login bug"}'
curl http://127.0.0.1:4004/api/v1/sessions/<id>/notes
curl "http://127.0.0.1:4004/api/v1/worklog?days=7"
```

A note joins the session running at its `at` time, or stands alone. With
`session_id`, the time must fall during that session. Notes can't be in the future.
Deleting a session keeps its notes as standalone entries. The work log lists each
day's sessions, with their notes, on the day they started; day totals split sessions
at midnight like the overview.

Run the backend connection checks without accessing GPIO or MongoDB:

```bash
python -m unittest discover -s tests -p 'test_dashboard_websocket.py' -v
```

The counter checks also run without the Pi's pins or MongoDB:

```bash
python -m unittest discover -s tests -p 'test_counters.py' -v
```

The category and note checks run the same way:

```bash
python -m unittest discover -s tests -p 'test_categories_notes.py' -v
```
