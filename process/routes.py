import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from models import Complaint, Assignment, StatusHistory, Resolution, ComplaintStatus
from schemas import StatusUpdateRequest, CloseComplaintRequest, StandardAPIResponse
# Assume get_db and get_current_user are provided by Core Auth Module
from deps import get_db, get_current_user

router = APIRouter(prefix="/api/v1", tags=["Processing & Status Module"])

# Valid state transitions
ALLOWED_TRANSITIONS = {
    ComplaintStatus.ASSIGNED: [ComplaintStatus.IN_PROGRESS],
    ComplaintStatus.IN_PROGRESS: [ComplaintStatus.RESOLVED],
}

@router.get("/staff/complaints/assigned")
def get_assigned_complaints(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != "maintenance_staff":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a maintenance staff member.")

    query = (
        db.query(Complaint)
        .join(Assignment, Complaint.complaint_id == Assignment.complaint_id)
        .filter(Assignment.staff_id == current_user["user_id"], Assignment.is_current == True)
    )

    if status_filter:
        try:
            target_status = ComplaintStatus(status_filter.lower())
            query = query.filter(Complaint.status == target_status)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status filter: {status_filter}")

    complaints = query.all()
    data = [
        {
            "complaint_id": c.complaint_id,
            "title": c.title,
            "category_id": c.category_id,
            "location": c.location,
            "status": c.status.value,
            "created_at": c.created_at.isoformat()
        }
        for c in complaints
    ]
    return {"status": "success", "data": data}


@router.patch("/staff/complaints/{complaint_id}/status")
def update_complaint_status(
    complaint_id: str,
    payload: StatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != "maintenance_staff":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a maintenance staff member.")

    complaint = db.query(Complaint).filter(Complaint.complaint_id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint ID does not exist.")

    # Access control: Verify this staff member is currently assigned to the complaint
    current_assignment = (
        db.query(Assignment)
        .filter(Assignment.complaint_id == complaint_id, Assignment.is_current == True)
        .first()
    )
    if not current_assignment or current_assignment.staff_id != current_user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff member not assigned to this complaint.")

    try:
        new_status = ComplaintStatus(payload.status.lower())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid target status: {payload.status}")

    # Validate lifecycle transition
    allowed = ALLOWED_TRANSITIONS.get(complaint.status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state transition sequence from '{complaint.status.value}' to '{new_status.value}'."
        )

    # Resolution details check
    if new_status == ComplaintStatus.RESOLVED:
        if not payload.resolution_details or not payload.resolution_details.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing mandatory resolution details for status 'resolved'."
            )
        
        # Insert into resolutions table
        resolution = Resolution(
            resolution_id=str(uuid.uuid4()),
            complaint_id=complaint_id,
            resolved_by=current_user["user_id"],
            details=payload.resolution_details.strip(),
            resolved_at=datetime.utcnow()
        )
        db.add(resolution)

    # Append to status_history table
    history = StatusHistory(
        history_id=str(uuid.uuid4()),
        complaint_id=complaint_id,
        old_status=complaint.status,
        new_status=new_status,
        changed_by=current_user["user_id"],
        remarks=payload.remarks,
        changed_at=datetime.utcnow()
    )
    db.add(history)

    # Update complaint current state
    old_status_val = complaint.status.value
    complaint.status = new_status
    complaint.updated_at = datetime.utcnow()

    db.commit()

    return {
        "status": "success",
        "message": f"Complaint status updated successfully from {old_status_val} to {new_status.value}.",
        "data": {
            "complaint_id": complaint.complaint_id,
            "status": complaint.status.value,
            "updated_at": complaint.updated_at.isoformat()
        }
    }


@router.patch("/complaints/{complaint_id}/close")
def close_complaint(
    complaint_id: str,
    payload: CloseComplaintRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    complaint = db.query(Complaint).filter(Complaint.complaint_id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint ID does not exist.")

    # Authorization Check (Only original resident or admin can close)
    if current_user["role"] == "resident" and complaint.resident_id != current_user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized user attempting closure.")
    elif current_user["role"] not in ["resident", "administrator"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized user attempting closure.")

    if complaint.status != ComplaintStatus.RESOLVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Attempting to close a complaint that is in '{complaint.status.value}' state instead of 'resolved'."
        )

    if not payload.confirmation:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation is required to close the complaint.")

    # Append to status_history table
    history = StatusHistory(
        history_id=str(uuid.uuid4()),
        complaint_id=complaint_id,
        old_status=complaint.status,
        new_status=ComplaintStatus.CLOSED,
        changed_by=current_user["user_id"],
        remarks=payload.closure_notes,
        changed_at=datetime.utcnow()
    )
    db.add(history)

    complaint.status = ComplaintStatus.CLOSED
    complaint.updated_at = datetime.utcnow()

    db.commit()

    return {
        "status": "success",
        "message": "Complaint has been officially closed.",
        "data": {
            "complaint_id": complaint.complaint_id,
            "status": complaint.status.value,
            "closed_at": complaint.updated_at.isoformat()
        }
    }