"""SQLAlchemy models — dumb persistence containers, no business logic."""

import uuid
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.extensions import db

VALID_ROLES = {"customer", "admin"}
VALID_STATUSES = {"received", "in_progress", "complete"}


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer")
    company_name = db.Column(db.String(200))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    submissions = db.relationship("Submission", back_populates="user", foreign_keys="Submission.user_id")

    def get_id(self):
        return str(self.id)


class Submission(db.Model):
    __tablename__ = "submissions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(20), nullable=False, default="received")

    customer_name = db.Column(db.String(200), nullable=False)
    street_address = db.Column(db.String(200), nullable=False)
    city = db.Column(db.String(200), nullable=False)
    state = db.Column(db.String(200), nullable=False)
    country = db.Column(db.String(200), nullable=False)
    customer_contact = db.Column(db.String(200), nullable=False)
    customer_phone = db.Column(db.String(200), nullable=False)

    payment_method = db.Column(db.String(10), nullable=False)
    po_number = db.Column(db.String(100), default="")
    cc_number = db.Column(db.String(100), default="")

    results_list = db.Column(ARRAY(db.String), nullable=False, default=list)
    results_cc_list = db.Column(ARRAY(db.String), nullable=False, default=list)
    invoice_list = db.Column(ARRAY(db.String), nullable=False, default=list)
    invoice_cc_list = db.Column(ARRAY(db.String), nullable=False, default=list)

    user = db.relationship("User", back_populates="submissions", foreign_keys=[user_id])
    samples = db.relationship("Sample", back_populates="submission", cascade="all, delete-orphan")
    audit_entries = db.relationship("AuditLog", back_populates="submission", cascade="all, delete-orphan")


class Sample(db.Model):
    __tablename__ = "samples"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = db.Column(UUID(as_uuid=True), db.ForeignKey("submissions.id"), nullable=False)

    sample_id = db.Column(db.String(100), nullable=False)
    chemical_matrix = db.Column(db.String(200), nullable=False)
    sample_type = db.Column(db.String(20), nullable=False)
    processing_time = db.Column(db.String(20), nullable=False)
    analyses = db.Column(ARRAY(db.String), nullable=False, default=list)

    submission = db.relationship("Submission", back_populates="samples")


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = db.Column(UUID(as_uuid=True), db.ForeignKey("submissions.id"), nullable=False)
    changed_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    changed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    field_name = db.Column(db.String(100), nullable=False)
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)

    submission = db.relationship("Submission", back_populates="audit_entries")
    user = db.relationship("User", foreign_keys=[changed_by])
