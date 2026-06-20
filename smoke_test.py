"""Quick end-to-end smoke test (no real phone needed).

Validates basic auth, /send enqueue, /status, and the message lifecycle.
Run: python smoke_test.py
"""

import os
import tempfile

# Configure before importing the app so get_settings() picks these up.
tmp = tempfile.mkdtemp()
os.environ.update(
    GATEWAY_HOST="127.0.0.1",
    GATEWAY_PORT="9",  # unreachable -> sends fail, queue logic still exercised
    GATEWAY_USERNAME="g",
    GATEWAY_PASSWORD="g",
    SERVER_USERNAME="admin",
    SERVER_PASSWORD="secret",
    RATE_LIMIT_PER_DAY="100",
    RATE_LIMIT_MIN_INTERVAL_SECONDS="5",
    DB_PATH=os.path.join(tmp, "test.db"),
    LOG_FILE=os.path.join(tmp, "test.log"),
)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

GOOD = ("admin", "secret")
BAD = ("admin", "wrong")

with TestClient(app) as c:
    assert c.get("/health").json() == {"ok": True}

    # Auth is enforced.
    assert c.get("/status").status_code == 401
    assert c.get("/status", auth=BAD).status_code == 401

    # Empty status.
    s = c.get("/status", auth=GOOD).json()
    assert s["queue_length"] == 0 and s["sent_today"] == 0
    assert s["remaining_daily_quota"] == 100

    # Enqueue a couple of messages.
    r1 = c.post("/send", auth=GOOD,
                json={"recipient": "+15551234567", "message": "hi"})
    assert r1.status_code == 200, r1.text
    mid = r1.json()["id"]
    assert r1.json()["status"] == "queued"

    c.post("/send", auth=GOOD,
           json={"recipient": "+15559876543", "message": "yo"})

    s = c.get("/status", auth=GOOD).json()
    assert s["queue_length"] >= 1, s

    # Message record is retrievable.
    m = c.get(f"/messages/{mid}", auth=GOOD).json()
    assert m["recipient"] == "+15551234567"
    assert m["status"] in ("queued", "failed")

    # Validation: missing message rejected.
    assert c.post("/send", auth=GOOD,
                  json={"recipient": "+1"}).status_code == 422

print("SMOKE TEST PASSED")
