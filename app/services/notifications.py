"""Database-backed in-app notifications.

``notify*`` functions only *queue* rows in the current session; the calling
service commits them together with the change that caused them, so a
notification is never sent for something that failed.
"""
from app import constants as C
from app.extensions import db
from app.models import Notification, User
from app.utils.timeutil import utcnow


def _user_id(user):
    return user.id if hasattr(user, "id") else int(user)


def notify(user, title, message, category=C.NOTIFY_SYSTEM, link=None):
    """Queue one notification for ``user`` (a ``User`` or a user id)."""
    notification = Notification(
        user_id=_user_id(user),
        title=(title or "Notification")[:150],
        message=message or "",
        category=category if category in C.NOTIFICATION_CATEGORIES else C.NOTIFY_SYSTEM,
        link_url=(link or None),
    )
    db.session.add(notification)
    return notification


def notify_many(users, title, message, category=C.NOTIFY_SYSTEM, link=None):
    """Notify several users once each (duplicates are ignored)."""
    seen = set()
    created = []
    for user in users:
        if user is None:
            continue
        uid = _user_id(user)
        if uid in seen:
            continue
        seen.add(uid)
        created.append(notify(uid, title, message, category, link))
    return created


def notify_admins(title, message, category=C.NOTIFY_SYSTEM, link=None):
    admins = User.query.filter_by(role=C.ROLE_ADMIN, status=C.ACCOUNT_ACTIVE).all()
    return notify_many(admins, title, message, category, link)


def notify_role(role, title, message, category=C.NOTIFY_SYSTEM, link=None, verified_only=True, limit=500):
    """Notify active users of one role (verified ones only by default)."""
    query = User.query.filter_by(role=role, status=C.ACCOUNT_ACTIVE)
    users = query.limit(limit).all()
    if verified_only:
        users = [u for u in users if u.is_verified]
    return notify_many(users, title, message, category, link)


# --------------------------------------------------------------- reading side
def unread_count(user_id):
    return Notification.query.filter_by(user_id=_user_id(user_id), is_read=False).count()


def recent(user_id, limit=8):
    return (
        Notification.query.filter_by(user_id=_user_id(user_id))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )


def mark_read(user_id, notification_id):
    """Mark one notification as read. Returns ``False`` if it isn't the user's."""
    notification = Notification.query.filter_by(id=notification_id, user_id=_user_id(user_id)).first()
    if notification is None:
        return False
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = utcnow()
        db.session.commit()
    return True


def mark_all_read(user_id):
    """Mark every unread notification of the user as read; returns how many."""
    now = utcnow()
    count = Notification.query.filter_by(user_id=_user_id(user_id), is_read=False).update(
        {"is_read": True, "read_at": now}, synchronize_session=False
    )
    db.session.commit()
    return count


def serialize(notification):
    """JSON-friendly dict used by the polling API."""
    return {
        "id": notification.id,
        "title": notification.title,
        "message": notification.message,
        "category": notification.category,
        "icon": notification.icon,
        "link": notification.link_url,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat() + "Z" if notification.created_at else None,
    }
