import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class IntakeSubmission(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "intake_submissions"

    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), default="internal", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pre_check_in", nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)

    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id"), nullable=True, index=True)

    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    converted_ticket_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    device_brand: Mapped[str] = mapped_column(String(80), nullable=False)
    device_model: Mapped[str] = mapped_column(String(120), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    imei: Mapped[str | None] = mapped_column(String(60), nullable=True)

    reported_fault: Mapped[str] = mapped_column(Text, nullable=False)
    accessories: Mapped[str | None] = mapped_column(Text, nullable=True)
    intake_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    preferred_language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    preferred_contact_method: Mapped[str | None] = mapped_column(String(20), nullable=True)

    branch = relationship("Branch")
    customer = relationship("Customer")
    device = relationship("Device")
    submitted_by_user = relationship("User", foreign_keys=[submitted_by_user_id])
    converted_ticket = relationship("Ticket", foreign_keys=[converted_ticket_id])


class IntakeDisclaimerAcceptance(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "intake_disclaimer_acceptances"

    intake_submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intake_submissions.id"), nullable=False, index=True)
    disclaimer_key: Mapped[str] = mapped_column(String(80), nullable=False)
    disclaimer_text: Mapped[str] = mapped_column(Text, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    intake_submission = relationship("IntakeSubmission")


class IntakeSignature(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "intake_signatures"

    intake_submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intake_submissions.id"), nullable=False, index=True)
    signer_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    signature_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    intake_submission = relationship("IntakeSubmission")


class Attachment(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "attachments"

    intake_submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("intake_submissions.id"), nullable=True, index=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(nullable=True)
    is_public_upload: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    intake_submission = relationship("IntakeSubmission")
    ticket = relationship("Ticket")
    uploaded_by_user = relationship("User")


class PortalToken(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "portal_tokens"

    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    token_type: Mapped[str] = mapped_column(String(50), nullable=False)
    intake_submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("intake_submissions.id"), nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    intake_submission = relationship("IntakeSubmission")
