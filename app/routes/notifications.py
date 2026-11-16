"""Notification centre (database backed) and the small JSON API the top-bar bell polls."""
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app import constants as C
from app.models import Notification
from app.services import notifications
from app.utils.permissions import login_required

bp = Blueprint("notifications", __name__, url_prefix="/notifications")


def _wants_json():
    """True for requests made by our JavaScript (fetch / XHR)."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in request.headers.get(
        "Accept", "")


@bp.route("/")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    show = request.args.get("filter", "all")
    category = request.args.get("category", "")
    query = Notification.query.filter_by(user_id=current_user.id)
    if show == "unread":
        query = query.filter_by(is_read=False)
    if category in C.NOTIFICATION_CATEGORIES:
        query = query.filter_by(category=category)
    pagination = query.order_by(Notification.created_at.desc(), Notification.id.desc()).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("notifications/index.html", pagination=pagination, show=show, category=category,
                           unread=notifications.unread_count(current_user.id))


@bp.route("/api/count")
@login_required
def api_count():
    return jsonify(count=notifications.unread_count(current_user.id))


@bp.route("/api/recent")
@login_required
def api_recent():
    items = [notifications.serialize(item) for item in notifications.recent(current_user.id)]
    return jsonify(count=notifications.unread_count(current_user.id), items=items)


@bp.route("/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_read(notification_id):
    found = notifications.mark_read(current_user.id, notification_id)
    if _wants_json():
        return jsonify(ok=bool(found)), (200 if found else 404)
    target = None
    if found:
        item = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first()
        link = item.link_url if item is not None else None
        # only follow links that stay on this site
        if link and link.startswith("/") and not link.startswith("//"):
            target = link
    return redirect(target or url_for("notifications.index"))


@bp.route("/read-all", methods=["POST"])
@login_required
def mark_all_read():
    count = notifications.mark_all_read(current_user.id)
    if _wants_json():
        return jsonify(ok=True, count=count)
    return redirect(url_for("notifications.index"))
