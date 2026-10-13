# STREET E

Flask + Flask-SocketIO browser fighting-game prototype.

## Local run

1. Install Python 3.11 or newer.
2. Run `py -m venv .venv`
3. Run ` .venv\\Scripts\\python.exe -m pip install -r requirements.txt` (remove the leading space).
4. Set environment variables before launch:
   - `ADMIN_USERNAME=admin`
   - `ADMIN_PASSWORD` to a new private password
   - `SECRET_KEY` to a long random secret
5. Run `.venv\\Scripts\\python.exe app.py` and open `http://127.0.0.1:5000`.

## Render

The `render.yaml` blueprint creates a free web service and generates a secret key and admin password. After deployment, open the service's Environment settings to retrieve the generated `ADMIN_PASSWORD`; keep it private. The admin username is `admin`.

## Important limitations

- This is a prototype with turn-based attack/guard combat, not a full real-time animated fighting game.
- Live spectators see the match status and health/logs, not camera video.
- Free Render instances use ephemeral storage by default. SQLite accounts, coins, and wins can be lost on redeploy/restart. Use a persistent database before treating this as a permanent public game.
- Match queues live in server memory and are intended for a single running instance.
