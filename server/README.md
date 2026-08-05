# Web service

The service combines a FastAPI application, MySQL persistence, MQTT messaging,
authenticated sessions, and a WebSocket-powered thermal dashboard.

## Run with Docker

1. Copy `.env.example` to `.env` and replace every placeholder.
2. Run `docker compose up --build` from this directory.
3. Open `http://localhost:8000`, register a local account, and sign in.

For HTTPS deployment, set `COOKIE_SECURE=true`.
