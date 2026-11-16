"""Role dashboards. Every number comes from ``app.services.stats`` (counted from the database)."""
from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

from app import constants as C
from app.services import notifications, stats
from app.utils.permissions import login_required, roles_required

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


def _rail():
    """Data for the live-notifications box that every dashboard shows in its side panel."""
    return {"notes": notifications.recent(current_user.id, 5), "unread": notifications.unread_count(current_user.id)}


@bp.route("/")
@login_required
def index():
    """Send the user to the dashboard of their role (or to the verification page)."""
    if not current_user.is_verified:
        return redirect(url_for("account.pending"))
    return redirect(url_for(C.ROLE_DASHBOARD_ENDPOINT[current_user.role]))


@bp.route("/admin")
@roles_required(C.ROLE_ADMIN)
def admin():
    return render_template("dashboard/admin.html", d=stats.admin_dashboard(), **_rail())


@bp.route("/rescuer")
@roles_required(C.ROLE_RESCUER)
def rescuer():
    return render_template("dashboard/rescuer.html", d=stats.rescuer_dashboard(current_user), **_rail())


@bp.route("/volunteer")
@roles_required(C.ROLE_VOLUNTEER)
def volunteer():
    return render_template("dashboard/volunteer.html", d=stats.volunteer_dashboard(current_user), **_rail())


@bp.route("/veterinarian")
@roles_required(C.ROLE_VETERINARIAN)
def veterinarian():
    return render_template("dashboard/veterinarian.html", d=stats.veterinarian_dashboard(current_user), **_rail())


@bp.route("/shelter")
@roles_required(C.ROLE_SHELTER)
def shelter():
    return render_template("dashboard/shelter.html", d=stats.shelter_dashboard(current_user), **_rail())


@bp.route("/adopter")
@roles_required(C.ROLE_ADOPTER)
def adopter():
    return render_template("dashboard/adopter.html", d=stats.adopter_dashboard(current_user), **_rail())
