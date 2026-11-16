"""Registration, sign-in, account lock-out, forced password change and sign-out."""
import pytest

pytest.importorskip("flask_sqlalchemy")
pytest.importorskip("flask_login")
pytest.importorskip("flask_wtf")

from app import constants as C  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AuditLog, Notification, User, VolunteerProfile  # noqa: E402
from app.services import user_service  # noqa: E402
from app.services.common import ServiceError  # noqa: E402
from tests.helpers import (  # noqa: E402
    PASSWORD, count, create_user, field, form_values, login_as, sign_in, url, user_id_for,
)

STRONG = "Strong@123"
EMAIL = "asha@pawconnect.test"


def account_form(**overrides):
    """What a browser sends for the registration form."""
    data = {
        "full_name": "Asha Verma", "email": EMAIL, "phone": "9876543210",
        "password": STRONG, "confirm_password": STRONG, "accept_terms": True, "role": C.ROLE_ADOPTER,
    }
    data.update(overrides)
    return form_values(data)


# ------------------------------------------------------------------ registration
def test_adopter_registers_and_then_signs_in(app, client):
    response = client.post("/register", data=account_form())
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    user_id = user_id_for(app, EMAIL)
    assert user_id is not None
    assert field(app, User, user_id, "role") == C.ROLE_ADOPTER
    assert field(app, User, user_id, "verification_status") == C.VERIFY_NOT_REQUIRED
    assert STRONG not in field(app, User, user_id, "password_hash")  # only a hash is stored, never the password
    assert count(app, Notification, user_id=user_id) == 1  # the welcome message
    assert count(app, AuditLog, action="user_registered") == 1

    response = client.post("/login", data={"email": EMAIL, "password": STRONG})
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url(app, "dashboard.index"))


def test_duplicate_email_is_refused_whatever_the_letter_case(app, client):
    create_user(app, C.ROLE_ADOPTER, EMAIL)
    response = client.post("/register", data=account_form(email=EMAIL.upper()))
    assert response.status_code == 200
    assert "already exists" in response.get_data(as_text=True)
    assert count(app, User) == 1


@pytest.mark.parametrize("password", ["short1", "onlyletters", "12345678"])
def test_weak_passwords_are_refused(app, client, password):
    response = client.post("/register", data=account_form(password=password, confirm_password=password))
    assert response.status_code == 200
    assert count(app, User) == 0


def test_the_two_passwords_must_match(app, client):
    response = client.post("/register", data=account_form(confirm_password="Different@123"))
    assert response.status_code == 200
    assert count(app, User) == 0


def test_the_declaration_must_be_accepted(app, client):
    response = client.post("/register", data=account_form(accept_terms=False))
    assert response.status_code == 200
    assert count(app, User) == 0


@pytest.mark.parametrize("role", [C.ROLE_ADMIN, "superuser", C.ROLE_VOLUNTEER])
def test_a_role_that_is_not_offered_cannot_be_chosen_on_the_register_page(app, client, role):
    response = client.post("/register", data=account_form(role=role))
    assert response.status_code == 200  # the form is shown again
    assert count(app, User) == 0


def test_volunteer_page_ignores_a_role_sent_by_the_browser(app, client):
    data = form_values({
        "full_name": "Divya Rao", "email": EMAIL, "phone": "9876543210", "password": STRONG,
        "confirm_password": STRONG, "accept_terms": True, "skills": "Dog walking", "availability": "Weekends",
        "role": C.ROLE_ADMIN,  # a tampered form
    })
    response = client.post("/register/volunteer", data=data)
    assert response.status_code == 302
    user_id = user_id_for(app, EMAIL)
    assert field(app, User, user_id, "role") == C.ROLE_VOLUNTEER
    with app.app_context():
        profile = VolunteerProfile.query.filter_by(user_id=user_id).one()
        assert profile.application_status == C.APPLICATION_PENDING  # an administrator must approve first


def test_rescuer_registration_waits_for_administrator_verification(app, client):
    admin_id = create_user(app, C.ROLE_ADMIN)
    data = account_form(
        role=C.ROLE_RESCUER, service_area="Testville", verification_details="Five years with a local animal NGO.",
        has_vehicle=True)
    assert client.post("/register", data=data).status_code == 302

    user_id = user_id_for(app, EMAIL)
    assert field(app, User, user_id, "verification_status") == C.VERIFY_PENDING
    assert count(app, Notification, user_id=admin_id, category=C.NOTIFY_ACCOUNT) == 1  # the administrator is told

    sign_in(client, EMAIL, STRONG)
    response = client.get(url(app, "dashboard.index"))
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url(app, "account.pending"))


def test_veterinarian_and_shelter_registration_need_their_own_details(app, client):
    response = client.post("/register", data=account_form(role=C.ROLE_VETERINARIAN))  # no licence number
    assert response.status_code == 200
    response = client.post("/register", data=account_form(role=C.ROLE_SHELTER, verification_details="Registered trust."))
    assert response.status_code == 200  # no shelter name, address, city or capacity
    assert count(app, User) == 0

    shelter = account_form(
        role=C.ROLE_SHELTER, shelter_name="Happy Tails", address="5 Park Road", city="Testville", capacity=12,
        verification_details="Registered trust, number 4567.")
    assert client.post("/register", data=shelter).status_code == 302
    assert field(app, User, user_id_for(app, EMAIL), "role") == C.ROLE_SHELTER


# ------------------------------------------------------------------ sign in
def test_wrong_password_and_unknown_email_get_the_same_message(app, client):
    create_user(app, C.ROLE_ADOPTER, EMAIL)
    wrong_password = client.post("/login", data={"email": EMAIL, "password": "Wrong@12345"})
    unknown_email = client.post("/login", data={"email": "nobody@pawconnect.test", "password": PASSWORD})
    for response in (wrong_password, unknown_email):
        assert response.status_code == 200
        assert "Invalid e-mail or password." in response.get_data(as_text=True)  # does not reveal which part was wrong


def test_account_is_locked_after_repeated_wrong_passwords(app, client):
    create_user(app, C.ROLE_ADOPTER, EMAIL)
    for _ in range(3):  # MAX_FAILED_LOGINS is 3 in the testing configuration
        response = client.post("/login", data={"email": EMAIL, "password": "Wrong@12345"})
        assert "Invalid e-mail or password." in response.get_data(as_text=True)

    response = client.post("/login", data={"email": EMAIL, "password": PASSWORD})  # even the right password
    assert response.status_code == 200
    assert "Too many failed sign-in attempts" in response.get_data(as_text=True)
    assert client.get(url(app, "dashboard.index")).status_code == 302  # still signed out
    assert count(app, AuditLog, action="account_locked") == 1


def test_a_good_sign_in_resets_the_failure_counter(app, client):
    user_id = create_user(app, C.ROLE_ADOPTER, EMAIL)
    for _ in range(2):
        client.post("/login", data={"email": EMAIL, "password": "Wrong@12345"})
    assert field(app, User, user_id, "failed_login_attempts") == 2

    sign_in(client, EMAIL)
    assert field(app, User, user_id, "failed_login_attempts") == 0
    assert field(app, User, user_id, "last_login_at") is not None


@pytest.mark.parametrize("status", [C.ACCOUNT_SUSPENDED, C.ACCOUNT_INACTIVE])
def test_suspended_and_inactive_accounts_cannot_sign_in(app, client, status):
    create_user(app, C.ROLE_ADOPTER, EMAIL, status=status)
    response = client.post("/login", data={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    assert "This account is" in response.get_data(as_text=True)
    assert client.get(url(app, "dashboard.index")).status_code == 302


def test_suspending_an_account_ends_its_open_session(app, client):
    user_id = login_as(app, client, C.ROLE_ADOPTER)
    assert client.get(url(app, "dashboard.adopter")).status_code == 200
    with app.app_context():
        db.session.get(User, user_id).status = C.ACCOUNT_SUSPENDED
        db.session.commit()
    response = client.get(url(app, "dashboard.adopter"))
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_signed_in_visitors_are_sent_on_from_the_sign_in_pages(app, client):
    login_as(app, client, C.ROLE_ADOPTER)
    for path in ("/login", "/register", "/register/volunteer"):
        assert client.get(path).status_code == 302


# ------------------------------------------------------------------ redirects after sign in
def test_sign_in_returns_to_the_requested_page_but_never_leaves_the_site(app, client):
    admin_email = "admin.test@pawconnect.test"
    create_user(app, C.ROLE_ADMIN, admin_email)

    response = client.get("/admin/users")  # asked for while signed out
    assert response.status_code == 302
    assert "/login" in response.headers["Location"] and "next=" in response.headers["Location"]

    response = client.post("/login?next=/admin/users", data={"email": admin_email, "password": PASSWORD})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/users")

    other = app.test_client()  # an address on another site is ignored
    response = other.post("/login?next=https://evil.example/", data={"email": admin_email, "password": PASSWORD})
    assert response.status_code == 302
    assert "evil.example" not in response.headers["Location"]
    assert response.headers["Location"].endswith(url(app, "dashboard.index"))


# ------------------------------------------------------------------ sign out
def test_sign_out_only_works_with_post(app, client):
    login_as(app, client, C.ROLE_ADOPTER)
    assert client.get("/logout").status_code == 405  # a link or an image cannot sign anyone out
    assert client.get(url(app, "dashboard.adopter")).status_code == 200

    response = client.post("/logout")
    assert response.status_code == 302
    assert client.get(url(app, "dashboard.adopter")).status_code == 302


# ------------------------------------------------------------------ passwords
def test_temporary_password_must_be_changed_before_anything_else(app, client):
    login_as(app, client, C.ROLE_ADOPTER, must_change_password=True)
    response = client.get(url(app, "dashboard.adopter"))
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url(app, "account.change_password"))
    assert client.get(url(app, "account.change_password")).status_code == 200


def test_password_change_rules(app):
    user_id = create_user(app, C.ROLE_ADOPTER, must_change_password=True)
    with app.app_context():
        user = db.session.get(User, user_id)
        with pytest.raises(ServiceError, match="current password is incorrect"):
            user_service.change_password(user, "Wrong@12345", "Another@123")
        with pytest.raises(ServiceError, match="at least 8 characters"):
            user_service.change_password(user, PASSWORD, "short1")
        with pytest.raises(ServiceError, match="different from your current one"):
            user_service.change_password(user, PASSWORD, PASSWORD)

        user_service.change_password(user, PASSWORD, "Another@123")
        assert user.check_password("Another@123")
        assert not user.check_password(PASSWORD)
        assert user.must_change_password is False
