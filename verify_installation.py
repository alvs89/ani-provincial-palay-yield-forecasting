from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

health = client.get("/health")
assert health.status_code == 200, health.text
print("Health:", health.json())

meta = client.get("/meta")
assert meta.status_code == 200, meta.text
print("Suggested next target:", meta.json()["suggested_next_target"])

prediction = client.post(
    "/predict",
    json={
        "province": "Nueva Ecija",
        "ecosystem": "Irrigated",
        "target_year": 2026,
        "target_quarter": 1,
    },
)
assert prediction.status_code == 200, prediction.text
payload = prediction.json()
assert payload["eligible"] is True, payload
print("Sample 2026 Q1 prediction:", payload["predictedYield"], payload["unit"])
print("Historical status:", payload["historicalStatus"])

unsupported = client.post(
    "/predict",
    json={
        "province": "Nueva Ecija",
        "ecosystem": "Irrigated",
        "target_year": 2026,
        "target_quarter": 2,
    },
)
assert unsupported.status_code == 200, unsupported.text
assert unsupported.json()["eligible"] is False
print("Q2 withholding check:", unsupported.json()["reason"])

print("ANI backend verification passed.")
