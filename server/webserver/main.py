import os
import json
import uuid
import bcrypt
import threading
import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    Response,
    Cookie,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict, Field

import db
import models
from db import engine, Base, get_db, SessionLocal
from models import Device, Reading, User, UserSession

import paho.mqtt.client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER", "broker.emqx.io")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "thermal-presence/demo")
MQTT_ENABLED = os.getenv("MQTT_ENABLED", "true").lower() in {"1", "true", "yes"}
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.main_loop = asyncio.get_running_loop()
    if MQTT_ENABLED:
        thread = threading.Thread(target=_mqtt_thread, daemon=True)
        thread.start()
    yield


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

Base.metadata.create_all(bind=engine)

READINGS_TOPIC = f"{MQTT_TOPIC}/readings"
COMMAND_TOPIC = f"{MQTT_TOPIC}/command"


# ---------------- WebSocket Manager ----------------
class WSManager:
    def __init__(self):
        self.clients: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.clients:
            self.clients.remove(ws)

    async def broadcast(self, payload: Dict[str, Any]):
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

ws_manager = WSManager()


# ---------------- Pydantic Models ----------------
class CommandIn(BaseModel):
    command: str

class ReadingIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mac_address: str
    pixels: List[float] = Field(..., min_length=64, max_length=64)
    thermistor_temp: float = Field(..., alias="thermistor")
    prediction: str
    confidence: float

class AuthIn(BaseModel):
    username: str
    password: str


# ---------------- Auth Helpers ----------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

def create_session(db: Session, user_id: int) -> str:
    token = str(uuid.uuid4())
    session = UserSession(user_id=user_id, session_token=token)
    db.add(session)
    db.commit()
    db.refresh(session)
    return token

def get_current_user(
    session_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not session_token:
        raise HTTPException(status_code=401, detail="Authentication required")

    stmt = (
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.session_token == session_token)
    )
    user = db.scalar(stmt)

    if user is None:
        raise HTTPException(status_code=401, detail="Invalid session")

    return user

def get_optional_user(
    session_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not session_token:
        return None

    stmt = (
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.session_token == session_token)
    )
    return db.scalar(stmt)


# ---------------- Reading Helpers ----------------
def _normalize_prediction(pred: str) -> str:
    p = pred.strip().upper()
    if p not in ["PRESENT", "EMPTY"]:
        raise HTTPException(status_code=422, detail="prediction must be PRESENT or EMPTY")
    return p

def _insert_reading(db: Session, payload: ReadingIn) -> Reading:
    if len(payload.pixels) != 64:
        raise HTTPException(status_code=422, detail="pixels must have exactly 64 floats")

    pred = _normalize_prediction(payload.prediction)

    device = db.scalar(select(Device).where(Device.mac_address == payload.mac_address))
    if device is None:
        device = Device(mac_address=payload.mac_address)
        db.add(device)
        db.flush()

    r = Reading(
        mac_address=payload.mac_address,
        device_id=device.id,
        thermistor_temp=float(payload.thermistor_temp),
        prediction=pred,
        confidence=float(payload.confidence),
        pixels=[float(x) for x in payload.pixels],
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ---------------- Frontend Pages ----------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html")

@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "username": user.username,
        },
    )


# ---------------- Auth API ----------------
@app.post("/api/register")
def api_register(body: AuthIn, db: Session = Depends(get_db)):
    username = body.username.strip()
    password = body.password

    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")

    existing = db.scalar(select(User).where(User.username == username))
    if existing is not None:
        raise HTTPException(status_code=409, detail="username already exists")

    user = User(
        username=username,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {"ok": True, "id": user.id, "username": user.username}

@app.post("/api/login")
def api_login(body: AuthIn, response: Response, db: Session = Depends(get_db)):
    username = body.username.strip()
    password = body.password

    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")

    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_session(db, user.id)

    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )

    return {"ok": True, "username": user.username}

@app.post("/api/logout")
def api_logout(
    response: Response,
    session_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if session_token:
        session = db.scalar(
            select(UserSession).where(UserSession.session_token == session_token)
        )
        if session is not None:
            db.delete(session)
            db.commit()

    response.delete_cookie(key="session_token", path="/")
    return {"ok": True}


# ---------------- Protected WebSocket ----------------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    token = ws.cookies.get("session_token")
    if not token:
        await ws.close(code=1008)
        return

    db_session = SessionLocal()
    try:
        session = db_session.scalar(
            select(UserSession).where(UserSession.session_token == token)
        )
        if session is None:
            await ws.close(code=1008)
            return
    finally:
        db_session.close()

    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception:
        ws_manager.disconnect(ws)


# ---------------- Protected API ----------------
_mqtt_pub_lock = threading.Lock()
_mqtt_pub_client: Optional[mqtt.Client] = None

def _get_pub_client() -> mqtt.Client:
    global _mqtt_pub_client
    with _mqtt_pub_lock:
        if _mqtt_pub_client is None:
            c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            c.connect(MQTT_BROKER, 1883, 60)
            c.loop_start()
            _mqtt_pub_client = c
        return _mqtt_pub_client

@app.post("/api/command")
def api_command(body: CommandIn, user: User = Depends(get_current_user)):
    cmd = body.command.strip().lower()
    if cmd not in ["get_one", "start_continuous", "stop"]:
        raise HTTPException(status_code=400, detail="Unknown command")

    try:
        c = _get_pub_client()
        print(f"[MQTT] Publishing '{cmd}' to {COMMAND_TOPIC}")
        c.publish(COMMAND_TOPIC, cmd, qos=0, retain=False)
    except Exception as e:
        print(f"[MQTT] Publish Error: {e}")

    return {"ok": True, "command": cmd}

@app.post("/api/readings")
async def create_reading(
    payload: ReadingIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = _insert_reading(db, payload)

    await ws_manager.broadcast({
        "type": "reading",
        "id": r.id,
        "mac_address": r.mac_address,
        "thermistor_temp": r.thermistor_temp,
        "prediction": r.prediction,
        "confidence": r.confidence,
        "pixels": r.pixels,
    })

    return {"id": r.id}

@app.get("/api/readings")
def list_readings(
    device_mac: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Reading).order_by(Reading.id.desc())
    if device_mac:
        stmt = stmt.where(Reading.mac_address == device_mac)
    rows = db.scalars(stmt).all()

    return [
        {
            "id": r.id,
            "mac_address": r.mac_address,
            "thermistor_temp": r.thermistor_temp,
            "prediction": r.prediction,
            "confidence": r.confidence,
            "pixels": r.pixels,
        }
        for r in rows
    ]

@app.delete("/api/readings/{reading_id}")
def delete_reading(
    reading_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = db.get(Reading, reading_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(r)
    db.commit()
    return {"ok": True}

@app.get("/api/devices")
def list_devices(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    devices = db.scalars(select(Device).order_by(Device.id.desc())).all()
    return [{"id": d.id, "mac_address": d.mac_address} for d in devices]


# ---------------- MQTT Subscriber ----------------
def _on_mqtt_connect(client, userdata, flags, reason_code, properties):
    print(f"[MQTT] Subscribed to {READINGS_TOPIC}")
    client.subscribe(READINGS_TOPIC, qos=0)

def _on_mqtt_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        payload = ReadingIn(**data)
    except Exception as e:
        print(f"[MQTT] Parse Error: {e}")
        return

    db_session = SessionLocal()
    try:
        r = _insert_reading(db_session, payload)
    except Exception as e:
        print(f"[DB] Insert Error: {e}")
        db_session.rollback()
        return
    finally:
        db_session.close()

    try:
        if hasattr(app.state, "main_loop"):
            coro = ws_manager.broadcast({
                "type": "reading",
                "id": r.id,
                "mac_address": r.mac_address,
                "thermistor_temp": r.thermistor_temp,
                "prediction": r.prediction,
                "confidence": r.confidence,
                "pixels": r.pixels,
            })
            asyncio.run_coroutine_threadsafe(coro, app.state.main_loop)
    except Exception as e:
        print(f"[WS] Broadcast Error: {e}")

def _mqtt_thread():
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.on_connect = _on_mqtt_connect
    c.on_message = _on_mqtt_message
    c.connect(MQTT_BROKER, 1883, 60)
    c.loop_forever()
