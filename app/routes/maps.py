"""Rescue map: where the open reports are (administrators and verified rescuers)."""
from flask import Blueprint, jsonify, render_template, request

from app import constants as C
from app.services import rescue_service
from app.utils.permissions import roles_required

bp = Blueprint("maps", __name__, url_prefix="/map")

MAP_LIMIT = 300  # a map with more pins than this is unreadable; the filters narrow it down


def _filters():
    status = request.args.get("status") or "open"
    if status not in ("open", "all") + C.REPORT_STATUSES:
        status = "open"
    emergency = request.args.get("emergency", "")
    if emergency not in C.EMERGENCY_LEVELS:
        emergency = ""
    animal_type = request.args.get("type", "")
    if animal_type not in C.ANIMAL_TYPES:
        animal_type = ""
    return status, emergency, animal_type


def _reports(status, emergency, animal_type):
    query = rescue_service.search_reports(
        status=None if status == "all" else status, emergency=emergency, animal_type=animal_type, priority_first=True)
    return query.limit(MAP_LIMIT).all()


@bp.route("/")
@roles_required(C.ROLE_ADMIN, C.ROLE_RESCUER)
def overview():
    status, emergency, animal_type = _filters()
    reports = _reports(status, emergency, animal_type)
    markers = rescue_service.map_markers(reports)
    return render_template(
        "maps/overview.html", reports=reports, markers=markers, status=status, emergency=emergency,
        animal_type=animal_type, limit=MAP_LIMIT, unmapped=[r for r in reports if not r.has_location],
    )


@bp.route("/api/reports")
@roles_required(C.ROLE_ADMIN, C.ROLE_RESCUER)
def api_reports():
    """JSON for the live map: pins for the reports that match the filters (no contact details)."""
    status, emergency, animal_type = _filters()
    reports = _reports(status, emergency, animal_type)
    markers = rescue_service.map_markers(reports)
    return jsonify(markers=markers, total=len(reports), mapped=len(markers))
