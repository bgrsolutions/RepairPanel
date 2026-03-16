import uuid
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from app.extensions import db
from app.models import RepairChecklist, Ticket
from app.models.checklist import ChecklistItem, DEFAULT_CHECKLISTS
from app.services.permission_service import can_manage_checklists
from app.utils.permissions import permission_required

checklists_bp = Blueprint("checklists", __name__)


@checklists_bp.post("/tickets/<uuid:ticket_id>/checklists/create")
@login_required
@permission_required(can_manage_checklists)
def create_checklist(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    checklist_type = (request.form.get("checklist_type") or "").strip()
    if checklist_type not in ("pre_repair", "post_repair"):
        flash(_("Invalid checklist type"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    # Check if an active (non-completed) checklist of this type already exists
    existing = RepairChecklist.query.filter_by(
        ticket_id=ticket.id, checklist_type=checklist_type
    ).first()
    if existing and not existing.is_complete:
        flash(_("A %(type)s checklist already exists for this ticket", type=checklist_type.replace("_", " ")), "info")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    # Determine device category for default items
    device_category = (ticket.device.category or "other").lower().strip() if ticket.device else "other"
    if device_category not in DEFAULT_CHECKLISTS:
        device_category = "other"

    default_items = DEFAULT_CHECKLISTS.get(device_category, DEFAULT_CHECKLISTS["other"]).get(checklist_type, [])

    checklist = RepairChecklist(
        ticket_id=ticket.id,
        checklist_type=checklist_type,
        device_category=device_category,
    )
    db.session.add(checklist)
    db.session.flush()

    for position, label in enumerate(default_items):
        item = ChecklistItem(
            checklist_id=checklist.id,
            position=position,
            label=label,
        )
        db.session.add(item)

    db.session.commit()
    flash(_("%(type)s checklist created with %(count)d items", type=checklist_type.replace("_", " ").title(), count=len(default_items)), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@checklists_bp.post("/checklists/<uuid:checklist_id>/update")
@login_required
@permission_required(can_manage_checklists)
def update_checklist(checklist_id):
    checklist = db.session.get(RepairChecklist, checklist_id)
    if not checklist:
        flash(_("Checklist not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    if checklist.is_complete:
        flash(_("This checklist is already completed and cannot be modified"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=checklist.ticket_id))

    now = datetime.utcnow()

    for item in checklist.items:
        item_key = f"item_{item.id}"
        was_checked = item.is_checked
        item.is_checked = request.form.get(item_key) == "on"

        if item.is_checked and not was_checked:
            item.checked_at = now
            item.checked_by_user_id = current_user.id

        if not item.is_checked and was_checked:
            item.checked_at = None
            item.checked_by_user_id = None

        notes_key = f"notes_{item.id}"
        if notes_key in request.form:
            item.notes = (request.form.get(notes_key) or "").strip() or None

    db.session.commit()
    flash(_("Checklist updated"), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=checklist.ticket_id))


@checklists_bp.post("/checklists/<uuid:checklist_id>/complete")
@login_required
@permission_required(can_manage_checklists)
def complete_checklist(checklist_id):
    checklist = db.session.get(RepairChecklist, checklist_id)
    if not checklist:
        flash(_("Checklist not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    if checklist.is_complete:
        flash(_("This checklist is already completed"), "info")
        return redirect(url_for("tickets.ticket_detail", ticket_id=checklist.ticket_id))

    if not checklist.all_checked:
        flash(_("All checklist items must be checked before completing"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=checklist.ticket_id))

    checklist.completed_at = datetime.utcnow()
    checklist.completed_by_user_id = current_user.id
    db.session.commit()
    flash(_("Checklist marked as complete"), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=checklist.ticket_id))


@checklists_bp.post("/checklists/item/<uuid:item_id>/toggle")
@login_required
@permission_required(can_manage_checklists)
def toggle_checklist_item(item_id):
    """AJAX endpoint: toggle a single checklist item without full form submit."""
    item = db.session.get(ChecklistItem, item_id)
    if not item:
        return jsonify({"ok": False, "error": "Item not found"}), 404

    checklist = db.session.get(RepairChecklist, item.checklist_id)
    if not checklist or checklist.is_complete:
        return jsonify({"ok": False, "error": "Checklist is completed"}), 400

    data = request.get_json(silent=True) or {}
    is_checked = data.get("is_checked", not item.is_checked)
    now = datetime.utcnow()

    if is_checked and not item.is_checked:
        item.is_checked = True
        item.checked_at = now
        item.checked_by_user_id = current_user.id
    elif not is_checked and item.is_checked:
        item.is_checked = False
        item.checked_at = None
        item.checked_by_user_id = None

    db.session.commit()
    return jsonify({
        "ok": True,
        "is_checked": item.is_checked,
        "checked_count": checklist.checked_count,
        "total_count": checklist.total_count,
        "all_checked": checklist.all_checked,
    })
