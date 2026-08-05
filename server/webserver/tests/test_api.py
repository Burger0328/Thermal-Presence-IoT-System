def sample_reading(mac_address="AA:BB:CC:DD:EE:FF"):
    return {
        "mac_address": mac_address,
        "pixels": [24.5 + index / 100 for index in range(64)],
        "thermistor": 24.2,
        "prediction": "PRESENT",
        "confidence": 0.91,
    }


def test_dashboard_requires_login(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_register_login_and_logout(client):
    credentials = {"username": "zhibo", "password": "not-a-real-password"}

    assert client.post("/api/register", json=credentials).status_code == 200
    duplicate = client.post("/api/register", json=credentials)
    assert duplicate.status_code == 409

    login = client.post("/api/login", json=credentials)
    assert login.status_code == 200
    assert login.cookies.get("session_token")
    assert client.get("/").status_code == 200

    assert client.post("/api/logout").status_code == 200
    assert client.get("/", follow_redirects=False).status_code == 302


def test_reading_crud_and_device_discovery(authenticated_client):
    client = authenticated_client
    created = client.post("/api/readings", json=sample_reading())
    assert created.status_code == 200
    reading_id = created.json()["id"]

    readings = client.get("/api/readings").json()
    assert len(readings) == 1
    assert readings[0]["pixels"] == sample_reading()["pixels"]
    assert readings[0]["prediction"] == "PRESENT"

    devices = client.get("/api/devices").json()
    assert devices == [{"id": devices[0]["id"], "mac_address": "AA:BB:CC:DD:EE:FF"}]

    assert client.delete(f"/api/readings/{reading_id}").status_code == 200
    assert client.get("/api/readings").json() == []


def test_reading_validation(authenticated_client):
    invalid_pixels = sample_reading()
    invalid_pixels["pixels"] = [25.0] * 63
    assert authenticated_client.post("/api/readings", json=invalid_pixels).status_code == 422

    invalid_prediction = sample_reading()
    invalid_prediction["prediction"] = "MAYBE"
    response = authenticated_client.post("/api/readings", json=invalid_prediction)
    assert response.status_code == 422


def test_command_validation(authenticated_client, monkeypatch):
    class Publisher:
        def publish(self, *args, **kwargs):
            return None

    monkeypatch.setattr("main._get_pub_client", lambda: Publisher())
    accepted = authenticated_client.post("/api/command", json={"command": "get_one"})
    assert accepted.status_code == 200
    assert accepted.json()["command"] == "get_one"

    rejected = authenticated_client.post("/api/command", json={"command": "reboot"})
    assert rejected.status_code == 400
