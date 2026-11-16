"""Messages sent through the public contact form (they land in the administrators' inbox)."""
from app import constants as C
from app.extensions import db
from app.models import ContactMessage
from app.services import audit, notifications
from app.services.common import link_for, require, transaction
from app.utils import validators as V


def submit_message(name, email, subject, message):
    """Store a contact message and tell the administrators about it."""
    name = V.clean_text(name, 100)
    email = V.normalize_email(email)
    subject = V.clean_text(subject, 150)
    message = V.clean_text(message, 3000)
    require(name and len(name) >= 2, "Please enter your name.")
    require(email and V.is_valid_email(email), "Please enter a valid e-mail address.")
    require(subject and len(subject) >= 3, "Please enter a subject.")
    require(message and len(message) >= 10, "Please write a message of at least 10 characters.")
    with transaction():
        item = ContactMessage(name=name, email=email, subject=subject, message=message, status=C.CONTACT_NEW)
        db.session.add(item)
        db.session.flush()
        notifications.notify_admins("New contact message", f"{name}: {subject}", C.NOTIFY_SYSTEM,
                                    link_for("admin.messages"))
        audit.log_action("contact_message_received", "ContactMessage", item.id, subject)
    return item
