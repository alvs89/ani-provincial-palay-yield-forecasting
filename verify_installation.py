from datetime import date
import math

from fastapi.testclient import TestClient

from backend.main import app, classify_environmental_freshness, classify_target_period
from ml.features import normalize_province_name

client = TestClient(app)

# Backend service and metadata
health = client.get('/health')
assert health.status_code == 200, health.text
meta = client.get('/meta')
assert meta.status_code == 200, meta.text
assert 'model' in meta.json()
print('PASS Backend: /health and /meta return 200.')

# Model prediction and existing lag-availability withholding check
prediction = client.post(
    '/predict',
    json={
        'province': 'Nueva Ecija',
        'ecosystem': 'Irrigated',
        'target_year': 2026,
        'target_quarter': 1,
    },
)
assert prediction.status_code == 200, prediction.text
prediction_payload = prediction.json()
assert prediction_payload['eligible'] is True, prediction_payload
predicted_yield = prediction_payload.get('predictedYield')
assert isinstance(predicted_yield, (int, float)) and not isinstance(predicted_yield, bool)
assert math.isfinite(predicted_yield), predicted_yield
for field in (
    'temporalStatus',
    'resultType',
    'targetPeriodStart',
    'targetPeriodEnd',
    'referenceDate',
    'referenceTimezone',
):
    assert field in prediction_payload, f'Missing prediction field: {field}'
    assert isinstance(prediction_payload[field], str), (field, prediction_payload[field])
assert prediction_payload['referenceTimezone'] == 'Asia/Manila'
# Do not assert temporalStatus here: the live result is intentionally date-dependent.
assert date.fromisoformat(prediction_payload['referenceDate'])

unsupported = client.post(
    '/predict',
    json={
        'province': 'Nueva Ecija',
        'ecosystem': 'Irrigated',
        'target_year': 2026,
        'target_quarter': 2,
    },
)
assert unsupported.status_code == 200, unsupported.text
unsupported_payload = unsupported.json()
assert unsupported_payload['eligible'] is False, unsupported_payload
assert 'Required historical agricultural record for lag 1 (2026 Q1) is missing' in unsupported_payload['reason']
print('PASS Model prediction: Q1 2026 is numeric and eligible; Q2 is withheld because its required Q1 lag is missing.')

# Deterministic Manila quarterly temporal classification
reference_date = date(2026, 10, 13)
expected_temporal = {
    (2026, 1): ('RETROSPECTIVE_ESTIMATE', 'Retrospective Estimate'),
    (2026, 3): ('RETROSPECTIVE_ESTIMATE', 'Retrospective Estimate'),
    (2026, 4): ('CURRENT_QUARTER_ESTIMATE', 'Current-Quarter Estimate'),
    (2027, 1): ('PROSPECTIVE_FORECAST', 'Prospective Forecast'),
}
for (year, quarter), (status, result_type) in expected_temporal.items():
    classified = classify_target_period(year, quarter, reference_date)
    assert classified['temporalStatus'] == status, classified
    assert classified['resultType'] == result_type, classified
    assert classified['referenceTimezone'] == 'Asia/Manila', classified
print('PASS Temporal classification: explicit 2026-10-13 quarter cases and Asia/Manila timezone match.')

# Deterministic freshness classification for an in-memory report
report = {
    'context': {
        'forecast_window': {
            'start': '2026-10-14',
            'end': '2026-10-23',
        }
    }
}
for check_date, expected_status in (
    (date(2026, 10, 13), 'UPCOMING'),
    (date(2026, 10, 18), 'CURRENT'),
    (date(2026, 10, 24), 'EXPIRED'),
):
    freshness = classify_environmental_freshness(report, check_date)
    assert freshness['status'] == expected_status, freshness
    current_for_decision_support = freshness['status'] in {'UPCOMING', 'CURRENT'}
    assert current_for_decision_support is (expected_status != 'EXPIRED')
for invalid_report in (
    {},
    {'context': {'forecast_window': {'start': 'not-a-date', 'end': '2026-10-23'}}},
):
    assert classify_environmental_freshness(invalid_report, reference_date)['status'] == 'UNKNOWN'
print('PASS Environmental freshness: upcoming, current, expired, and unknown windows match.')

# Province aliases normalize while canonical identifiers pass through unchanged
province_names = {
    'Cotabato': 'Cotabato (North Cotabato)',
    'Davao de Oro': 'Davao de Oro (Compostela Valley)',
    'Tawi-Tawi': 'Tawi-tawi',
}
for supplied, canonical in province_names.items():
    assert normalize_province_name(supplied) == canonical
    assert normalize_province_name(canonical) == canonical
print('PASS Province normalization: aliases and canonical names match.')

# Public availability endpoint confirms the intended Q1 2026 eligibility
for province in ('Cotabato (North Cotabato)', 'Davao de Oro (Compostela Valley)'):
    response = client.get(
        '/forecast-availability',
        params={'province': province, 'ecosystem': 'Irrigated'},
    )
    assert response.status_code == 200, response.text
    targets = response.json()['availableTargets']
    assert any(target['year'] == 2026 and target['quarter'] == 1 for target in targets), (province, targets)

tawi = client.get(
    '/forecast-availability',
    params={'province': 'Tawi-tawi', 'ecosystem': 'Irrigated'},
)
assert tawi.status_code == 200, tawi.text
assert not any(
    target['year'] == 2026 and target['quarter'] == 1
    for target in tawi.json()['availableTargets']
)
print('PASS Forecast eligibility: Cotabato and Davao de Oro Q1 2026 available; Tawi-tawi remains unavailable.')

print('ANI integration verification passed.')
