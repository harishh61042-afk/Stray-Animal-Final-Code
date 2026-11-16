"""Public website: home, adoption listing and details, about, how it works and the contact form."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import constants as C
from app.extensions import db
from app.forms.contact import ContactForm
from app.models import AdoptionApplication, Animal
from app.services import animal_service, contact_service, stats
from app.services.common import ServiceError, like_pattern

bp = Blueprint("public", __name__)

ADOPT_PER_PAGE = 9
STAFF_ROLES = (C.ROLE_ADMIN, C.ROLE_RESCUER, C.ROLE_VETERINARIAN, C.ROLE_SHELTER)


def _available_animals():
    return Animal.query.filter(Animal.status == C.ANIMAL_AVAILABLE)


@bp.route("/")
def home():
    featured = _available_animals().order_by(Animal.available_since.desc(), Animal.id.desc()).limit(6).all()
    return render_template("public/home.html", overview=stats.public_overview(), featured=featured)


@bp.route("/about")
def about():
    return render_template("public/about.html")


@bp.route("/how-it-works")
def how_it_works():
    return render_template("public/how_it_works.html")


@bp.route("/adopt")
def animals():
    """Animals that are ready for adoption, with search and filters."""
    q = (request.args.get("q") or "").strip()
    animal_type = request.args.get("type", "")
    age_group = request.args.get("age_group", "")
    gender = request.args.get("gender", "")
    shelter_id = request.args.get("shelter_id", type=int)
    page = request.args.get("page", 1, type=int)

    query = _available_animals()
    if q:
        like = like_pattern(q)  # a typed % or _ is searched for literally
        query = query.filter(db.or_(*(
            column.ilike(like, escape="\\") for column in (
                Animal.name, Animal.breed, Animal.color, Animal.temperament, Animal.description))))
    if animal_type in C.ANIMAL_TYPES:
        query = query.filter(Animal.animal_type == animal_type)
    if age_group in C.AGE_GROUP_RANGES:
        low, high = C.AGE_GROUP_RANGES[age_group]
        query = query.filter(Animal.age_months >= low)
        if high is not None:
            query = query.filter(Animal.age_months < high)
    if gender in C.GENDERS:
        query = query.filter(Animal.gender == gender)
    if shelter_id:
        query = query.filter(Animal.shelter_id == shelter_id)

    pagination = query.order_by(Animal.available_since.desc(), Animal.id.desc()).paginate(
        page=page, per_page=ADOPT_PER_PAGE, error_out=False)
    shelter_options = [(shelter.id, shelter.shelter_name) for shelter in animal_service.verified_shelters()]
    return render_template(
        "public/animals.html", pagination=pagination, shelter_options=shelter_options,
        filters={"q": q, "type": animal_type, "age_group": age_group, "gender": gender, "shelter_id": shelter_id or ""},
        has_filters=bool(q or animal_type in C.ANIMAL_TYPES or age_group in C.AGE_GROUP_RANGES
                         or gender in C.GENDERS or shelter_id))


@bp.route("/adopt/<int:animal_id>")
def animal_detail(animal_id):
    animal = db.get_or_404(Animal, animal_id)
    if not animal.is_available:
        if current_user.is_authenticated and current_user.role in STAFF_ROLES:
            return redirect(url_for("animals.detail", animal_id=animal.id))
        abort(404)
    existing_application = None
    if current_user.is_authenticated and current_user.role == C.ROLE_ADOPTER:
        existing_application = AdoptionApplication.query.filter(
            AdoptionApplication.animal_id == animal.id, AdoptionApplication.adopter_id == current_user.id,
            AdoptionApplication.status.in_(C.ACTIVE_ADOPTION_STATUSES)).first()
    similar = _available_animals().filter(Animal.id != animal.id, Animal.animal_type == animal.animal_type).order_by(
        Animal.available_since.desc(), Animal.id.desc()).limit(3).all()
    return render_template("public/animal_detail.html", animal=animal, existing_application=existing_application,
                           similar=similar)


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    form = ContactForm()
    if request.method == "GET" and current_user.is_authenticated:
        form.name.data = current_user.full_name
        form.email.data = current_user.email
    if form.validate_on_submit():
        if form.website.data:  # honeypot filled in: pretend everything worked, store nothing
            flash("Thank you! Your message has been delivered to the PawConnect administrators.", "success")
            return redirect(url_for("public.contact"))
        try:
            contact_service.submit_message(form.name.data, form.email.data, form.subject.data, form.message.data)
            flash("Thank you! Your message has been delivered to the PawConnect administrators.", "success")
            return redirect(url_for("public.contact"))
        except ServiceError as error:
            flash(str(error), "danger")
    return render_template("public/contact.html", form=form)
