import pytest
from fastapi.testclient import TestClient
from main import app  # Import your FastAPI instance

client = TestClient(app)

def test_valid_status_transition_assigned_to_in_progress(staff_auth_header, sample_assigned_complaint_id):
    response = client.patch(
        f"/api/v1/staff/complaints/{sample_assigned_complaint_id}/status",
        headers=staff_auth_header,
        json={"status": "in_progress", "remarks": "Started inspection"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "in_progress"

def test_invalid_status_transition_assigned_to_resolved_directly(staff_auth_header, sample_assigned_complaint_id):
    # Direct jump from assigned -> resolved is invalid
    response = client.patch(
        f"/api/v1/staff/complaints/{sample_assigned_complaint_id}/status",
        headers=staff_auth_header,
        json={
            "status": "resolved",
            "remarks": "Skipped progress",
            "resolution_details": "Fixed sink"
        }
    )
    assert response.status_code == 400
    assert "Invalid state transition" in response.json()["detail"]

def test_unauthorized_access_updating_unassigned_complaint(other_staff_auth_header, sample_assigned_complaint_id):
    response = client.patch(
        f"/api/v1/staff/complaints/{sample_assigned_complaint_id}/status",
        headers=other_staff_auth_header,
        json={"status": "in_progress"}
    )
    assert response.status_code == 403
    assert "Staff member not assigned" in response.json()["detail"]

def test_non_existent_complaint_id(staff_auth_header):
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.patch(
        f"/api/v1/staff/complaints/{fake_uuid}/status",
        headers=staff_auth_header,
        json={"status": "in_progress"}
    )
    assert response.status_code == 404