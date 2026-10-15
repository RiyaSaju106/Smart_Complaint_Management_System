import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Enum as SQLEnum,
    ForeignKey, Integer, CheckConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class ComplaintStatus(str, Enum):
    SUBMITTED = "submitted"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

class Complaint(Base):
    __tablename__ = "complaints"

    complaint_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resident_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    title = Column(String(150), nullable=False)
    category_id = Column(String(36), ForeignKey("categories.category_id"), nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String(200), nullable=False)
    status = Column(SQLEnum(ComplaintStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=ComplaintStatus.SUBMITTED)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    assignments = relationship("Assignment", back_populates="complaint")
    status_history = relationship("StatusHistory", back_populates="complaint")
    resolution = relationship("Resolution", back_populates="complaint", uselist=False)

class Assignment(Base):
    __tablename__ = "assignments"

    assignment_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_id = Column(String(36), ForeignKey("complaints.complaint_id"), nullable=False)
    assigned_by = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.department_id"), nullable=False)
    staff_id = Column(String(36), ForeignKey("users.user_id"), nullable=True)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_current = Column(Boolean, default=True, nullable=False)

    complaint = relationship("Complaint", back_populates="assignments")

class StatusHistory(Base):
    __tablename__ = "status_history"

    history_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_id = Column(String(36), ForeignKey("complaints.complaint_id"), nullable=False)
    old_status = Column(SQLEnum(ComplaintStatus, values_callable=lambda x: [e.value for e in x]), nullable=True)
    new_status = Column(SQLEnum(ComplaintStatus, values_callable=lambda x: [e.value for e in x]), nullable=False)
    changed_by = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    remarks = Column(String(500), nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    complaint = relationship("Complaint", back_populates="status_history")

class Resolution(Base):
    __tablename__ = "resolutions"

    resolution_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_id = Column(String(36), ForeignKey("complaints.complaint_id"), nullable=False, unique=True)
    resolved_by = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    details = Column(Text, nullable=False)
    resolved_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    complaint = relationship("Complaint", back_populates="resolution")