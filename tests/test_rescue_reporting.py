"""Public rescue reporting: guests, validation, photo uploads, tracking by report ID, and who may follow a report."""
import io
import os
import re

import pytest

pytest.importorskip("flask_sqlalchemy")
pytest.importorskip("flask_login")
pytest.importorskip("flask_wtf")

from app import constants as C  # noqa: E402
from app.models import AnimalReport, Notification  # noqa: E402
from tests.helpers import (  # noqa: E402
    PNG_BYTES, count, create_report, create_user, field, form_values, login_as, report_data, url,
)

CODE_PATTERN = re.compile(r"^RPT-\d{4}-\d{5}$")


def post_report(client, **overrides):
    return client.post("/report", data=form_values(report_data(**overrides)))


def post_report_with_file(client, filename, content):
    data = form_values(report_data())
    data["image"] = (io.BytesIO(content), filename)
    return client.post("/report", data=data, content_type="multipart/form-data")


# ------------------------------------------------------------------ submitting
def test_a_guest_can_report_an_animal_without_an_account(app, client):
    admin_id = create_user(app, C.ROLE_ADMIN)
    assert client.get("/report").status_code == 200

    response = post_report(client)
    assert response.status_code == 302
    location = response.headers["Location"]
    code = location.rsplit("/", 1)[-1]
    assert CODE_PATTERN.match(code), code

    with app.app_context():
        report = AnimalReport.query.filter_by(report_code=code).one()
        assert report.status == C.REPORT_PENDING
        assert report.reporter_id is None  # a guest has no account
        assert report.animal_type == "Dog"
        assert report.emergency_level == "High"
        assert report.latitude == pytest.approx(12.9716)
        assert report.longitude == pytest.approx(77.5946)
        assert len(report.activities) == 1  # the first entry of the timeline

    assert count(app, Notification, user_id=admin_id, category=C.NOTIFY_RESCUE) == 1  # administrators are alerted

    confirmation = client.get(location)
    assert confirmation.status_code == 200
    assert code in confirmation.get_data(as_text=True)


def test_every_report_gets_its_own_id(app, client):
    codes = {post_report(client).headers["Location"].rsplit("/", 1)[-1] for _ in range(3)}
    assert len(codes) == 3
    assert count(app, AnimalReport) == 3


def test_the_confirmation_page_is_only_for_the_browser_that_submitted(app, client):
    location = post_report(client).headers["Location"]
    assert client.get(location).status_code == 200
    assert app.test_client().get(location).status_code == 404


@pytest.mark.parametrize("changes", [
    {"animal_description": "Too short"},
    {"reporter_name": ""},
    {"reporter_phone": "abc"},
    {"reporter_email": "not-an-email"},
    {"animal_type": ""},
    {"animal_condition": "Made up"},
    {"emergency_level": "Whatever"},
    {"animal_count": "0"},
    {"location_name": ""},
    {"address": ""},
    {"latitude": "123", "longitude": "77.5"},
    {"latitude": "12.9", "longitude": ""},
], ids=[
    "description-too-short", "no-name", "bad-phone", "bad-email", "no-animal-type", "unknown-condition",
    "unknown-urgency", "zero-animals", "no-place", "no-address", "latitude-out-of-range", "only-one-coordinate",
])
def test_invalid_reports_are_refused_and_nothing_is_saved(app, client, changes):
    response = post_report(client, **changes)
    assert response.status_code == 200  # the form is shown again with the problems
    assert count(app, AnimalReport) == 0


def test_a_report_without_a_map_position_is_still_accepted(app, client):
    response = post_report(client, latitude="", longitude="")
    assert response.status_code == 302
    with app.app_context():
        report = AnimalReport.query.one()
        assert report.latitude is None and report.longitude is None
        assert report.has_location is False


def test_the_hidden_bot_field_blocks_automatic_submissions(app, client):
    response = post_report(client, website="http://spam.example")
    assert response.status_code == 200
    assert count(app, AnimalReport) == 0


def test_a_signed_in_user_report_is_linked_to_the_account(app, client):
    user_id = login_as(app, client, C.ROLE_ADOPTER)
    response = post_report(client)
    assert response.status_code == 302
    code = response.headers["Location"].rsplit("/", 1)[-1]

    with app.app_context():
        report = AnimalReport.query.filter_by(report_code=code).one()
        assert report.reporter_id == user_id
    assert count(app, Notification, user_id=user_id, category=C.NOTIFY_RESCUE) == 1  # "Report received"

    mine = client.get(url(app, "reports.mine"))
    assert mine.status_code == 200
    assert code in mine.get_data(as_text=True)


# ------------------------------------------------------------------ photos
def test_a_png_photo_is_stored_under_a_server_chosen_name(app, client):
    response = post_report_with_file(client, "dog.png", PNG_BYTES)
    assert response.status_code == 302
    with app.app_context():
        stored = AnimalReport.query.one().image_filename
    assert stored.endswith(".png") and stored != "dog.png"
    assert os.path.isfile(os.path.join(app.config["UPLOAD_FOLDER"], C.UPLOAD_ANIMAL_REPORTS, stored))

    served = client.get(f"/uploads/{C.UPLOAD_ANIMAL_REPORTS}/{stored}")  # report photos are public
    assert served.status_code == 200
    assert served.headers["Content-Type"].startswith("image/png")
    assert served.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("filename, content", [
    ("virus.exe", b"MZ\x90\x00" + b"\x00" * 60),  # a program, not a picture
    ("fake.jpg", b"<?php echo 1; ?>" + b"\x00" * 40),  # right extension, but not a picture inside
    ("mismatch.gif", PNG_BYTES),  # the content is a PNG but the name says GIF
    ("empty.png", b""),
], ids=["wrong-extension", "not-an-image", "extension-mismatch", "empty-file"])
def test_unsafe_uploads_are_refused(app, client, filename, content):
    response = post_report_with_file(client, filename, content)
    assert response.status_code == 200
    assert count(app, AnimalReport) == 0
    assert os.listdir(os.path.join(app.config["UPLOAD_FOLDER"], C.UPLOAD_ANIMAL_REPORTS)) == []


# ------------------------------------------------------------------ tracking
def test_a_report_can_be_tracked_with_its_id_and_the_phone_number(app, client):
    _id, code = create_report(app)
    response = client.post("/track", data={"code": code, "contact": "98765-01234"})  # same digits, other format
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Last update" in body and "Gandhi Chowk" in body


def test_a_report_can_be_tracked_with_the_email_address(app, client):
    _id, code = create_report(app, reporter_email="meena@pawconnect.test")
    response = client.post("/track", data={"code": code.lower(), "contact": "Meena@PawConnect.test"})
    assert "Gandhi Chowk" in response.get_data(as_text=True)


@pytest.mark.parametrize("contact", ["9999999999", "other@pawconnect.test", "01234"])
def test_tracking_needs_the_matching_contact_details(app, client, contact):
    _id, code = create_report(app)
    response = client.post("/track", data={"code": code, "contact": contact})
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "We could not find a report" in body
    assert "Gandhi Chowk" not in body  # nothing about the report is shown


def test_guessing_report_ids_is_slowed_down(app, client):
    _id, code = create_report(app)
    for _ in range(8):
        client.post("/track", data={"code": code, "contact": "9999999999"})
    response = client.post("/track", data={"code": code, "contact": "98765 01234"})  # now even the right answer waits
    body = response.get_data(as_text=True)
    assert "Too many attempts" in body
    assert "Gandhi Chowk" not in body


def test_the_tracking_page_does_not_reveal_the_other_contact_detail(app, client):
    _id, code = create_report(app, reporter_email="meena@pawconnect.test")
    by_phone = client.post("/track", data={"code": code, "contact": "98765 01234"}).get_data(as_text=True)
    assert "Gandhi Chowk" in by_phone and "meena@pawconnect.test" not in by_phone
    by_email = client.post("/track", data={"code": code, "contact": "meena@pawconnect.test"}).get_data(as_text=True)
    assert "Gandhi Chowk" in by_email and "98765 01234" not in by_email


def test_a_new_report_starts_as_pending(app):
    report_id, _code = create_report(app)
    assert field(app, AnimalReport, report_id, "status") == C.REPORT_PENDING
