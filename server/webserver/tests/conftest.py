import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


WEB_ROOT = Path(__file__).resolve().parents[1]
os.chdir(WEB_ROOT)
sys.path.insert(0, str(WEB_ROOT))
os.environ["DATABASE_URL"] = "sqlite:///./thermal_presence_test.db"
os.environ["MQTT_ENABLED"] = "false"

from db import Base, engine  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def authenticated_client(client):
    credentials = {"username": "portfolio-user", "password": "strong-test-password"}
    assert client.post("/api/register", json=credentials).status_code == 200
    assert client.post("/api/login", json=credentials).status_code == 200
    return client
