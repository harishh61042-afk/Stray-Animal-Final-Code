"""System activity log (audit trail)."""
from flask import has_request_context, request
from flask_login import current_user

from app.extensions import db
from app.models import AuditLog


def log_action(action, entity_type=None, entity_id=None, description=None, user=None):
    """Queue an audit-log row; the caller's commit saves it.

    ``user`` defaults to the signed-in user (if any).
    """
    actor = user
    ip_address = None
    if has_request_context():
        ip_address = request.remote_addr
        if actor is None and current_user.is_authenticated:
            actor = current_user
    entry = AuditLog(
        user_id=getattr(actor, "id", None),
        action=action[:60],
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        ip_address=(ip_address or None),
    )
    db.session.add(entry)
    return entry
