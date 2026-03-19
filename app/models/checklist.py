from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UUIDMixin


class RepairChecklist(UUIDMixin, TimestampMixin, db.Model):
    """Pre-repair or post-repair checklist instance for a ticket."""

    __tablename__ = "repair_checklists"

    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    checklist_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # pre_repair, post_repair
    device_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    intake_submission_id: Mapped[str | None] = mapped_column(ForeignKey("intake_submissions.id"), nullable=True, index=True)

    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    intake_submission = relationship("IntakeSubmission", foreign_keys=[intake_submission_id])
    completed_by = relationship("User", foreign_keys=[completed_by_user_id])
    items = relationship("ChecklistItem", back_populates="checklist", cascade="all, delete-orphan", lazy="selectin",
                         order_by="ChecklistItem.position")

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None

    @property
    def checked_count(self) -> int:
        return sum(1 for item in self.items if item.is_checked)

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def all_checked(self) -> bool:
        return all(item.is_checked for item in self.items) if self.items else False


class ChecklistItem(UUIDMixin, TimestampMixin, db.Model):
    """Individual check item within a repair checklist."""

    __tablename__ = "checklist_items"

    checklist_id: Mapped[str] = mapped_column(ForeignKey("repair_checklists.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    checked_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    checklist = relationship("RepairChecklist", back_populates="items")
    checked_by = relationship("User", foreign_keys=[checked_by_user_id])


# Default checklist templates by device category
DEFAULT_CHECKLISTS = {
    "phones": {
        "pre_repair": [
            "Verify device powers on",
            "Document current screen condition (cracks, dead pixels)",
            "Test touch screen responsiveness",
            "Check charging port functionality",
            "Test all buttons (power, volume, mute)",
            "Verify SIM tray present",
            "Note any existing water damage indicators",
            "Confirm customer data backup status",
        ],
        "post_repair": [
            "Verify device powers on and boots correctly",
            "Test touch screen across all areas",
            "Test all buttons (power, volume, mute)",
            "Test charging port with cable",
            "Test speakers and microphone",
            "Test front and rear cameras",
            "Test WiFi and cellular connectivity",
            "Verify no new cosmetic damage",
            "Clean device exterior",
        ],
    },
    "tablets": {
        "pre_repair": [
            "Verify device powers on",
            "Document screen condition",
            "Test touch screen responsiveness",
            "Check charging port",
            "Test all buttons",
            "Confirm customer data backup status",
        ],
        "post_repair": [
            "Verify device powers on and boots correctly",
            "Test touch screen across all areas",
            "Test charging port",
            "Test speakers and microphone",
            "Test cameras",
            "Test WiFi connectivity",
            "Clean device exterior",
        ],
    },
    "laptops": {
        "pre_repair": [
            "Verify device powers on",
            "Document screen condition and hinge",
            "Test keyboard and trackpad",
            "Check all ports (USB, HDMI, charging)",
            "Note battery health/charge level",
            "Check for physical damage (case, screen, keyboard)",
            "Confirm customer data backup status",
        ],
        "post_repair": [
            "Verify device powers on and boots to OS",
            "Test keyboard (all keys)",
            "Test trackpad (click, scroll, gestures)",
            "Test display (no dead pixels, backlight even)",
            "Test WiFi connectivity",
            "Test all USB ports",
            "Test charging and battery",
            "Test speakers and audio",
            "Test webcam and microphone",
            "Verify fan operation",
            "Clean device exterior",
        ],
    },
    "desktops": {
        "pre_repair": [
            "Verify device powers on",
            "Check all ports (USB, HDMI, audio, ethernet)",
            "Note any unusual sounds (fans, drives)",
            "Document visible hardware condition",
        ],
        "post_repair": [
            "Verify device powers on and boots to OS",
            "Test all USB ports",
            "Test display output (HDMI/DP)",
            "Test audio output",
            "Test network connectivity",
            "Verify fan operation and temperatures",
            "Clean device exterior",
        ],
    },
    "game_consoles": {
        "pre_repair": [
            "Verify device powers on",
            "Test disc drive (if applicable)",
            "Check controller ports",
            "Check HDMI output",
            "Note any overheating signs",
        ],
        "post_repair": [
            "Verify device powers on and boots",
            "Test disc drive (if applicable)",
            "Test HDMI output",
            "Test controller connectivity",
            "Test WiFi/ethernet",
            "Verify fan operation",
            "Clean device exterior",
        ],
    },
    "other": {
        "pre_repair": [
            "Verify device powers on",
            "Document current condition",
            "Note any visible damage",
            "Confirm customer expectations",
        ],
        "post_repair": [
            "Verify device powers on",
            "Test primary functionality",
            "Verify repair completed as quoted",
            "Clean device exterior",
        ],
    },
}
