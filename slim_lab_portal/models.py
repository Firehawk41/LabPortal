"""SQLAlchemy models for portal-owned tables — persistence only, no business logic."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from slim_lab_portal.db import Base

ROLE_CUSTOMER = "customer"
ROLE_STAFF = "staff"
VALID_ROLES = (ROLE_CUSTOMER, ROLE_STAFF)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """A portal login. Customer users belong to one SLIM customer; staff users have initials."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('customer', 'staff')", name="role_valid"),
        CheckConstraint("role <> 'customer' OR customer_id IS NOT NULL", name="customer_has_customer_id"),
        CheckConstraint("role <> 'staff' OR (initials IS NOT NULL AND initials <> '')", name="staff_has_initials"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)  # stored lower-cased
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))
    customer_id: Mapped[int | None] = mapped_column(Integer, index=True)  # SLIM customers."ID"
    initials: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    @property
    def is_staff(self) -> bool:
        return self.role == ROLE_STAFF
