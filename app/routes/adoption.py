"""Adoption workflow: applications by adopters; review, approval and completion by shelters and administrators."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import false

from app import constants as C
from app.extensions import db
from app.forms import first_error, form_data
from app.forms.adoption import AdoptionApplicationForm, CompleteAdoptionForm, RejectApplicationForm, ReviewCommentForm
from app.forms.animals import ConfirmForm
from app.models import AdoptionApplication, AdoptionRecord, Animal, AuditLog, User
from app.services import adoption_service, animal_service, rules
from app.services.common import ServiceError, like_pattern
from app.utils.permissions import redirect_back, roles_required
from app.utils.timeutil import format_datetime, local_today

bp = Blueprint("adoption", __name__, url_prefix="/adoption")

STAFF_ROLES = (C.ROLE_ADMIN, C.ROLE_SHELTER)

# (key, label, statuses) - ``None`` means "every status"
MY_TABS = (
    ("all", "All", None),
    ("active", "In progress", C.ACTIVE_ADOPTION_STATUSES),
    ("completed", "Adopted", (C.ADOPTION_COMPLETED,)),
    ("closed", "Closed", (C.ADOPTION_REJECTED, C.ADOPTION_CANCELLED)),
)
MANAGE_TABS = (
    ("waiting", "Waiting for a decision", (C.ADOPTION_PENDING, C.ADOPTION_UNDER_REVIEW)),
    ("approved", "Approved", (C.ADOPTION_APPROVED,)),
    ("completed", "Completed", (C.ADOPTION_COMPLETED,)),
    ("closed", "Closed", (C.ADOPTION_REJECTED, C.ADOPTION_CANCELLED)),
    ("all", "All", None),
)

# audit action -> (title, icon, tone) for the history of one application
_HISTORY = {
    "adoption_applied": ("Application submitted", "bi-send-check", "blue"),
    "adoption_under_review": ("Review started", "bi-search", "amber"),
    "adoption_approved": ("Application approved", "bi-patch-check", "green"),
    "adoption_rejected": ("Application rejected", "bi-x-circle", "coral"),
    "adoption_cancelled": ("Application cancelled", "bi-slash-circle", "gray"),
    "adoption_completed": ("Adoption completed", "bi-balloon-heart", "green"),
}


def _actor():
    return current_user._get_current_object()


def _status_counts(query):
    """``{status: number of applications}`` for a (possibly joined) application query."""
    rows = query.with_entities(AdoptionApplication.status, db.func.count(AdoptionApplication.id)).group_by(
        AdoptionApplication.status).order_by(None).all()
    return dict(rows)


def _tabs(tabs, counts):
    """``[(key, label, count)]`` for the segmented control above a list."""
    result = []
    for key, label, statuses in tabs:
        total = sum(counts.values()) if statuses is None else sum(counts.get(status, 0) for status in statuses)
        result.append((key, label, total))
    return result


def _scoped_applications(user):
    """Applications the user may review: every one for an administrator, the shelter's own animals for a shelter."""
    query = AdoptionApplication.query.join(Animal, AdoptionApplication.animal_id == Animal.id)
    if user.role == C.ROLE_ADMIN:
        return query
    shelter = user.shelter_profile
    if shelter is None:
        return query.filter(false())
    return query.filter(Animal.shelter_id == shelter.id)


# ------------------------------------------------------------------ applying
def _prefill(form, user):
    """Start the form with what we already know, so a repeat applicant does not type everything again."""
    form.applicant_name.data = user.full_name
    form.applicant_email.data = user.email
    form.applicant_phone.data = user.phone
    last = AdoptionApplication.query.filter_by(adopter_id=user.id).order_by(AdoptionApplication.id.desc()).first()
    if last is not None:
        for name in ("address", "city", "state", "pincode", "occupation", "housing_type", "household_members",
                     "has_other_pets", "other_pets_details", "previous_experience"):
            getattr(form, name).data = getattr(last, name)
    elif user.profile is not None:
        form.address.data = user.profile.address
        form.city.data = user.profile.city
        form.state.data = user.profile.state
        form.pincode.data = user.profile.pincode


@bp.route("/apply/<int:animal_id>", methods=["GET", "POST"])
@roles_required(C.ROLE_ADOPTER)
def apply(animal_id):
    animal = db.get_or_404(Animal, animal_id)
    user = _actor()
    existing = AdoptionApplication.query.filter(
        AdoptionApplication.animal_id == animal.id, AdoptionApplication.adopter_id == user.id,
        AdoptionApplication.status.in_(C.ACTIVE_ADOPTION_STATUSES),
    ).first()
    if existing is not None:
        flash(f"You already have an application for {animal.display_name}.", "info")
        return redirect(url_for("adoption.detail", application_id=existing.id))
    if animal.status != C.ANIMAL_AVAILABLE:
        flash(f"{animal.display_name} is not available for adoption right now.", "warning")
        return redirect(url_for("public.animals"))

    form = AdoptionApplicationForm()
    if request.method == "GET":
        _prefill(form, user)
    if form.validate_on_submit():
        try:
            application = adoption_service.submit_application(animal, user, form_data(form))
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash(f"Your application {application.application_code} was sent. We will tell you as soon as it is reviewed.", "success")
            return redirect(url_for("adoption.detail", application_id=application.id))
    return render_template("adoption/apply.html", form=form, animal=animal)


# ------------------------------------------------------------------ adopter pages
@bp.route("/my")
@roles_required(C.ROLE_ADOPTER)
def my_applications():
    user = _actor()
    show = request.args.get("show", "all")
    page = request.args.get("page", 1, type=int)
    base = AdoptionApplication.query.filter(AdoptionApplication.adopter_id == user.id)
    counts = _status_counts(base)
    statuses = {key: wanted for key, _label, wanted in MY_TABS}.get(show)
    query = base.filter(AdoptionApplication.status.in_(statuses)) if statuses else base
    pagination = query.order_by(AdoptionApplication.created_at.desc(), AdoptionApplication.id.desc()).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template(
        "adoption/my_applications.html", pagination=pagination, tabs=_tabs(MY_TABS, counts),
        show=show if show in {key for key, _l, _s in MY_TABS} else "all", counts=counts,
    )


@bp.route("/history")
@roles_required(C.ROLE_ADOPTER)
def history():
    user = _actor()
    page = request.args.get("page", 1, type=int)
    records = AdoptionRecord.query.filter(AdoptionRecord.adopter_id == user.id).order_by(
        AdoptionRecord.adoption_date.desc(), AdoptionRecord.id.desc()).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    not_adopted = AdoptionApplication.query.filter(
        AdoptionApplication.adopter_id == user.id,
        AdoptionApplication.status.in_((C.ADOPTION_REJECTED, C.ADOPTION_CANCELLED)),
    ).order_by(AdoptionApplication.updated_at.desc(), AdoptionApplication.id.desc()).limit(10).all()
    return render_template("adoption/history.html", pagination=records, not_adopted=not_adopted)


# ------------------------------------------------------------------ one application
def _timeline(application):
    """Who did what to the application and when (from the activity log, plus the closing step if it is missing)."""
    rows = AuditLog.query.filter(
        AuditLog.entity_id == application.id,
        AuditLog.entity_type.in_(("AdoptionApplication", "AdoptionRecord")),
        AuditLog.action.in_(tuple(_HISTORY)),
    ).order_by(AuditLog.created_at, AuditLog.id).all()
    items = []
    for row in rows:
        title, icon, tone = _HISTORY[row.action]
        items.append({
            "title": title, "icon": icon, "tone": tone,
            "text": f"by {row.user.full_name}" if row.user else None, "time": format_datetime(row.created_at),
        })
    if not rows:
        title, icon, tone = _HISTORY["adoption_applied"]
        items.append({"title": title, "icon": icon, "tone": tone, "text": None, "time": format_datetime(application.created_at)})
    # A closed application may have been closed by the system (the animal was adopted by someone else).
    last_action = rows[-1].action if rows else None
    closing = {
        C.ADOPTION_REJECTED: ("adoption_rejected", "Application closed", "bi-x-circle", "coral"),
        C.ADOPTION_CANCELLED: ("adoption_cancelled", "Application cancelled", "bi-slash-circle", "gray"),
    }.get(application.status)
    if closing and last_action != closing[0]:
        items.append({
            "title": closing[1], "icon": closing[2], "tone": closing[3], "text": application.review_comment,
            "time": format_datetime(application.reviewed_at or application.updated_at),
        })
    return items


@bp.route("/application/<int:application_id>")
@roles_required()
def detail(application_id):
    application = db.get_or_404(AdoptionApplication, application_id)
    user = _actor()
    if not adoption_service.can_view(user, application):
        abort(403)
    animal = application.animal
    is_owner = application.adopter_id == user.id
    can_review = adoption_service.can_review(user, application)
    status = application.status
    others, adopter_stats = [], None
    if can_review:
        others = AdoptionApplication.query.filter(
            AdoptionApplication.animal_id == animal.id, AdoptionApplication.id != application.id,
        ).order_by(AdoptionApplication.id.desc()).limit(10).all()
        adopter_stats = {
            "applications": AdoptionApplication.query.filter_by(adopter_id=application.adopter_id).count(),
            "adopted": AdoptionRecord.query.filter_by(adopter_id=application.adopter_id).count(),
        }
    return render_template(
        "adoption/detail.html", application=application, animal=animal, shelter=animal.shelter, record=application.record,
        is_owner=is_owner, can_review=can_review, others=others, adopter_stats=adopter_stats, timeline=_timeline(application),
        can_start_review=can_review and rules.can_transition_adoption(status, C.ADOPTION_UNDER_REVIEW),
        can_approve=can_review and rules.can_transition_adoption(status, C.ADOPTION_APPROVED) and animal.status == C.ANIMAL_AVAILABLE,
        can_reject=can_review and rules.can_transition_adoption(status, C.ADOPTION_REJECTED),
        can_complete=can_review and status == C.ADOPTION_APPROVED and not animal.is_adopted,
        can_cancel=is_owner and application.can_be_cancelled, today=local_today(),
    )


# ------------------------------------------------------------------ staff lists
@bp.route("/manage")
@roles_required(*STAFF_ROLES)
def manage():
    """Applications waiting for the shelter's or administrator's decision. ``?animal_id=`` shows one animal's applications."""
    user = _actor()
    is_admin = user.role == C.ROLE_ADMIN
    q = (request.args.get("q") or "").strip()
    animal_id = request.args.get("animal_id", type=int)
    shelter_id = request.args.get("shelter_id", type=int) if is_admin else None
    page = request.args.get("page", 1, type=int)
    valid_tabs = {key: statuses for key, _label, statuses in MANAGE_TABS}
    show = request.args.get("show") or ("all" if animal_id else "waiting")
    if show not in valid_tabs:
        show = "waiting"

    base = _scoped_applications(user)
    if animal_id:
        base = base.filter(AdoptionApplication.animal_id == animal_id)
    if shelter_id:
        base = base.filter(Animal.shelter_id == shelter_id)
    counts = _status_counts(base)

    query = base
    if valid_tabs[show]:
        query = query.filter(AdoptionApplication.status.in_(valid_tabs[show]))
    if q:
        pattern = like_pattern(q)
        query = query.filter(db.or_(
            AdoptionApplication.application_code.ilike(pattern, escape="\\"),
            AdoptionApplication.applicant_name.ilike(pattern, escape="\\"),
            AdoptionApplication.applicant_email.ilike(pattern, escape="\\"),
            AdoptionApplication.city.ilike(pattern, escape="\\"),
            Animal.name.ilike(pattern, escape="\\"), Animal.animal_code.ilike(pattern, escape="\\"),
        ))
    oldest_first = show == "waiting"  # first come, first served
    order = AdoptionApplication.created_at.asc() if oldest_first else AdoptionApplication.created_at.desc()
    pagination = query.order_by(order, AdoptionApplication.id.asc() if oldest_first else AdoptionApplication.id.desc()).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)

    focus_animal = None
    if animal_id:
        candidate = db.session.get(Animal, animal_id)
        if candidate is not None and animal_service.can_view_animal(user, candidate):
            focus_animal = candidate
    return render_template(
        "adoption/manage.html", pagination=pagination, tabs=_tabs(MANAGE_TABS, counts), show=show, counts=counts, q=q,
        animal_id=animal_id or "", shelter_id=shelter_id or "", focus_animal=focus_animal, is_admin=is_admin,
        shelter_options=[(s.id, s.shelter_name) for s in animal_service.verified_shelters()] if is_admin else [],
    )


@bp.route("/records")
@roles_required(*STAFF_ROLES)
def records():
    """Completed adoptions."""
    user = _actor()
    is_admin = user.role == C.ROLE_ADMIN
    q = (request.args.get("q") or "").strip()
    shelter_id = request.args.get("shelter_id", type=int) if is_admin else None
    page = request.args.get("page", 1, type=int)

    base = AdoptionRecord.query.join(Animal, AdoptionRecord.animal_id == Animal.id).join(
        User, AdoptionRecord.adopter_id == User.id)
    if not is_admin:
        shelter = user.shelter_profile
        base = base.filter(AdoptionRecord.shelter_id == (shelter.id if shelter is not None else -1))
    elif shelter_id:
        base = base.filter(AdoptionRecord.shelter_id == shelter_id)
    today = local_today()
    totals = {
        "all": base.count(),
        "month": base.filter(AdoptionRecord.adoption_date >= today.replace(day=1)).count(),
        "year": base.filter(AdoptionRecord.adoption_date >= today.replace(month=1, day=1)).count(),
    }
    query = base
    if q:
        pattern = like_pattern(q)
        query = query.filter(db.or_(
            Animal.name.ilike(pattern, escape="\\"), Animal.animal_code.ilike(pattern, escape="\\"),
            User.full_name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\"),
        ))
    pagination = query.order_by(AdoptionRecord.adoption_date.desc(), AdoptionRecord.id.desc()).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template(
        "adoption/records.html", pagination=pagination, totals=totals, q=q, shelter_id=shelter_id or "", is_admin=is_admin,
        shelter_options=[(s.id, s.shelter_name) for s in animal_service.verified_shelters()] if is_admin else [],
    )


# ------------------------------------------------------------------ decisions (POST)
def _reviewable_application(application_id):
    application = db.get_or_404(AdoptionApplication, application_id)
    if not adoption_service.can_review(_actor(), application):
        abort(403)
    return application


def _back(application):
    return redirect_back(url_for("adoption.detail", application_id=application.id))


def _perform(application, form, action, message):
    """Validate a small POST form, run ``action`` and flash the outcome; always returns to the application."""
    if not form.validate_on_submit():
        flash(first_error(form), "danger")
        return _back(application)
    try:
        action()
    except ServiceError as error:
        flash(str(error), "danger")
    else:
        flash(message() if callable(message) else message, "success")
    return _back(application)


@bp.route("/application/<int:application_id>/review", methods=["POST"])
@roles_required(*STAFF_ROLES)
def review(application_id):
    application = _reviewable_application(application_id)
    form = ReviewCommentForm()
    return _perform(
        application, form, lambda: adoption_service.mark_under_review(application, _actor(), form.comment.data),
        "The application is now under review. The applicant has been told.")


@bp.route("/application/<int:application_id>/approve", methods=["POST"])
@roles_required(*STAFF_ROLES)
def approve(application_id):
    application = _reviewable_application(application_id)
    form = ReviewCommentForm()
    return _perform(
        application, form, lambda: adoption_service.approve_application(application, _actor(), form.comment.data),
        "Application approved. Complete the adoption when the animal goes home.")


@bp.route("/application/<int:application_id>/reject", methods=["POST"])
@roles_required(*STAFF_ROLES)
def reject(application_id):
    application = _reviewable_application(application_id)
    form = RejectApplicationForm()
    return _perform(
        application, form, lambda: adoption_service.reject_application(application, _actor(), form.comment.data),
        "Application rejected. The applicant has been told why.")


@bp.route("/application/<int:application_id>/complete", methods=["POST"])
@roles_required(*STAFF_ROLES)
def complete(application_id):
    application = _reviewable_application(application_id)
    form = CompleteAdoptionForm()
    name = application.animal.display_name
    return _perform(
        application, form,
        lambda: adoption_service.complete_adoption(application, _actor(), form.adoption_date.data, form.final_notes.data),
        lambda: f"Adoption completed and recorded. {name} is now marked as adopted.")


@bp.route("/application/<int:application_id>/cancel", methods=["POST"])
@roles_required(C.ROLE_ADOPTER)
def cancel(application_id):
    application = db.get_or_404(AdoptionApplication, application_id)
    if application.adopter_id != _actor().id:
        abort(403)
    form = ConfirmForm()
    if not form.validate_on_submit():
        flash(first_error(form), "danger")
        return redirect(url_for("adoption.detail", application_id=application.id))
    try:
        adoption_service.cancel_application(application, _actor())
    except ServiceError as error:
        flash(str(error), "danger")
    else:
        flash("Your application was cancelled.", "success")
    return redirect_back(url_for("adoption.my_applications"))
