"""Role-based access control: nobody reaches a page by guessing its address.

The sweeps below go through EVERY route of the protected parts of the site (found automatically from the URL map), so a
page added later without a permission check is caught by these tests.
"""
import pytest

pytest.importorskip("flask_sqlalchemy")
pytest.importorskip("flask_login")
pytest.importorskip("flask_wtf")

from flask import url_for  # noqa: E402
from werkzeug.routing import BuildError  # noqa: E402

from app import constants as C  # noqa: E402
from tests.helpers import (  # noqa: E402
    create_animal, create_application, create_report, create_user, login_as, sign_in, url,
)

# Every route of these blueprints needs a signed-in user. (public, auth, files, shelters.directory/detail and
# reports.new/submitted/track are public on purpose.)
PROTECTED_BLUEPRINTS = (
    "account", "admin", "adoption", "animals", "dashboard", "maps", "medical", "notifications", "rescue", "tasks",
    "volunteers",
)


def protected_routes(app, blueprint=None):
    """``[(method, path, endpoint)]`` for the protected routes; address arguments are filled with ``1``."""
    found = []
    with app.test_request_context():
        for rule in app.url_map.iter_rules():
            name = rule.endpoint.split(".")[0]
            if name not in PROTECTED_BLUEPRINTS or (blueprint and name != blueprint):
                continue
            arguments = {argument: 1 for argument in rule.arguments - set(rule.defaults or ())}
            try:
                path = url_for(rule.endpoint, **arguments)
            except BuildError:
                continue
            found.append(("GET" if "GET" in rule.methods else "POST", path, rule.endpoint))
    return found


def status_for(app, email, address):
    """The status code a signed-in user gets for ``address`` (a fresh browser every time)."""
    browser = app.test_client()
    sign_in(browser, email)
    return browser.get(address).status_code


# ------------------------------------------------------------------ nobody signed in
def test_the_sweep_really_finds_the_routes(app):
    assert len(protected_routes(app)) >= 60
    assert any(endpoint == "admin.users" for _method, _path, endpoint in protected_routes(app, "admin"))


def test_signed_out_visitors_are_sent_to_sign_in_from_every_protected_page(app, client):
    wrong = []
    for method, path, endpoint in protected_routes(app):
        response = client.open(path, method=method)
        if response.status_code != 302 or "/login" not in response.headers.get("Location", ""):
            wrong.append(f"{method} {path} ({endpoint}) -> {response.status_code}")
    assert not wrong, "These pages can be reached without signing in:\n" + "\n".join(wrong)


def test_script_requests_get_401_instead_of_a_redirect(app, client):
    response = client.get("/notifications/api/count", headers={"X-Requested-With": "XMLHttpRequest"})
    assert response.status_code == 401


# ------------------------------------------------------------------ wrong role
@pytest.mark.parametrize("role", [role for role in C.ALL_ROLES if role != C.ROLE_ADMIN])
def test_only_administrators_can_open_administrator_pages(app, client, role):
    login_as(app, client, role)
    wrong = []
    for method, path, endpoint in protected_routes(app, "admin"):
        response = client.open(path, method=method)
        if response.status_code != 403:
            wrong.append(f"{method} {path} ({endpoint}) -> {response.status_code}")
    assert not wrong, f"A {role} got into administrator pages:\n" + "\n".join(wrong)


@pytest.mark.parametrize("role", C.ALL_ROLES)
def test_every_role_reaches_its_own_dashboard_and_no_other(app, client, role):
    login_as(app, client, role)
    for other_role, endpoint in C.ROLE_DASHBOARD_ENDPOINT.items():
        response = client.get(url(app, endpoint))
        expected = 200 if other_role == role else 403
        assert response.status_code == expected, f"{role} opening the {other_role} dashboard gave {response.status_code}"

    response = client.get(url(app, "dashboard.index"))  # the generic address picks the right one
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url(app, C.ROLE_DASHBOARD_ENDPOINT[role]))


@pytest.mark.parametrize("role", [C.ROLE_ADOPTER, C.ROLE_VOLUNTEER, C.ROLE_VETERINARIAN, C.ROLE_SHELTER])
def test_rescue_coordination_pages_are_for_administrators_and_rescuers(app, client, role):
    login_as(app, client, role)
    assert client.get(url(app, "rescue.manage")).status_code == 403
    assert client.get(url(app, "rescue.my_cases")).status_code == 403


def test_adopters_cannot_manage_volunteer_tasks(app, client):
    login_as(app, client, C.ROLE_ADOPTER)
    assert client.get(url(app, "tasks.manage")).status_code == 403
    assert client.get(url(app, "tasks.new")).status_code == 403


# ------------------------------------------------------------------ verification and approval
@pytest.mark.parametrize("role", C.VERIFICATION_REQUIRED_ROLES)
def test_unverified_accounts_wait_on_the_pending_page(app, client, role):
    login_as(app, client, role, verified=False)
    response = client.get(url(app, C.ROLE_DASHBOARD_ENDPOINT[role]))
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url(app, "account.pending"))
    assert client.get(url(app, "account.pending")).status_code == 200


def test_verified_users_are_not_kept_on_the_pending_page(app, client):
    login_as(app, client, C.ROLE_RESCUER)
    assert client.get(url(app, "account.pending")).status_code == 302


def test_a_volunteer_must_be_approved_before_using_tasks(app, client):
    login_as(app, client, C.ROLE_VOLUNTEER, approved=False)
    response = client.get(url(app, "tasks.available"))
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url(app, "volunteers.my_application"))
    assert client.get(url(app, "volunteers.my_application")).status_code == 200


def test_an_approved_volunteer_can_see_available_tasks(app, client):
    login_as(app, client, C.ROLE_VOLUNTEER, approved=True)
    assert client.get(url(app, "tasks.available")).status_code == 200


# ------------------------------------------------------------------ other people's records
def test_an_application_is_private_to_its_adopter_and_the_reviewers(app):
    shelter_id = create_user(app, C.ROLE_SHELTER, "shelter.view@pawconnect.test")
    create_user(app, C.ROLE_SHELTER, "shelter.other@pawconnect.test")
    owner_id = create_user(app, C.ROLE_ADOPTER, "owner@pawconnect.test")
    create_user(app, C.ROLE_ADOPTER, "stranger@pawconnect.test")
    create_user(app, C.ROLE_ADMIN, "admin.view@pawconnect.test")
    animal_id = create_animal(app, shelter_user_id=shelter_id)
    application_id = create_application(app, animal_id, owner_id)
    address = url(app, "adoption.detail", application_id=application_id)

    assert app.test_client().get(address).status_code == 302  # signed out
    assert status_for(app, "stranger@pawconnect.test", address) == 403  # another adopter
    assert status_for(app, "shelter.other@pawconnect.test", address) == 403  # a shelter that does not house the animal
    assert status_for(app, "owner@pawconnect.test", address) == 200
    assert status_for(app, "shelter.view@pawconnect.test", address) == 200
    assert status_for(app, "admin.view@pawconnect.test", address) == 200


def test_a_report_is_private_to_its_reporter_and_the_rescue_staff(app):
    reporter_id = create_user(app, C.ROLE_ADOPTER, "reporter@pawconnect.test")
    create_user(app, C.ROLE_ADOPTER, "stranger@pawconnect.test")
    create_user(app, C.ROLE_RESCUER, "rescuer.view@pawconnect.test")
    create_user(app, C.ROLE_RESCUER, "rescuer.new@pawconnect.test", verified=False)
    report_id, _code = create_report(app, reporter_id=reporter_id)
    address = url(app, "reports.detail", report_id=report_id)

    assert status_for(app, "reporter@pawconnect.test", address) == 200
    assert status_for(app, "rescuer.view@pawconnect.test", address) == 200
    assert status_for(app, "stranger@pawconnect.test", address) == 403
    assert status_for(app, "rescuer.new@pawconnect.test", address) == 403  # not verified yet: no case details


def test_verification_documents_are_private(app, client):
    owner_id = create_user(app, C.ROLE_RESCUER)
    login_as(app, client, C.ROLE_ADOPTER)
    assert client.get(url(app, "files.verification_document", user_id=owner_id)).status_code == 403


def test_only_photo_folders_are_served_publicly(app, client):
    for address in (
        "/uploads/verification_documents/anything.pdf", "/uploads/medical_documents/anything.pdf",
        "/uploads/animals/../../config.py", "/uploads/animals/missing.png",
    ):
        assert client.get(address).status_code == 404, address


@pytest.mark.parametrize("endpoint", [
    "public.home", "public.about", "public.how_it_works", "public.animals", "public.contact", "shelters.directory",
    "reports.new", "reports.track", "auth.login", "auth.register", "auth.register_volunteer",
])
def test_public_pages_open_without_signing_in(app, client, endpoint):
    assert client.get(url(app, endpoint)).status_code == 200
