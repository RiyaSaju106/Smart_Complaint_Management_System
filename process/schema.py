from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class AssignedComplaintResponse(BaseModel):
    complaint_id: str
    title: str
    category_id: str
    location: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class StatusUpdateRequest(BaseModel):
    status: str = Field(..., description="Target status: 'in_progress' or 'resolved'")
    remarks: Optional[str] = Field(None, max_length=500)
    resolution_details: Optional[str] = Field(None, description="Mandatory when status is 'resolved'")

class CloseComplaintRequest(BaseModel):
    confirmation: bool
    closure_notes: Optional[str] = Field(None, max_length=500)

class StandardAPIResponse(BaseModel):
    status: str
    message: str
    data: Optional[dict] = None