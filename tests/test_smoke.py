"""Smoke tests: open every page as every kind of user and check that nothing crashes or points nowhere.

Two situations are covered, because they break in different ways:

* a brand-new installation with an empty database (every page must cope with "nothing here yet"), and
* the sample data from ``python init_db.py --seed`` (every page must cope with rows of every kind).

The test configuration lets errors through instead of showing the friendly error page, so a template or a query that
fails turns into a visible exception here. The pages are found automatically from the URL map, so a page added later
is covered without touching this file.
"""
import csv
import io
import re
from html.parser import HTMLParser

import pytest

pytest.importorskip("flask_sqlalchemy")
pytest.importorskip("flask_login")
pytest.importorskip("flask_wtf")

from flask import url_for  # noqa: E402
from werkzeug.exceptions import HTTPException  # noqa: E402
from werkzeug.routing import BuildError, RequestRedirect  # noqa: E402

from app import constants as C  # noqa: E402
from app.models import (  # noqa: E402
    AdoptionApplication, AdoptionRecord, Animal, AnimalReport, ContactMessage, MedicalRecord, Notification,
    ShelterProfile, User, Vaccination, VolunteerTask,
)
from app.services import admin_service  # noqa: E402
from database import seed_data  # noqa: E402
from tests.helpers import count, create_report, create_user, login_as, sign_in, url  # noqa: E402

ADMIN_EMAIL = "admin@pawconnect.test"
ADMIN_PASSWORD = "Admin@12345"
SAMPLE_ACCOUNTS = [ADMIN_EMAIL] + [account[2] for account in seed_data.ACCOUNTS]
FIXED_PAGE_STATUSES = (200, 302, 403)  # a page with a fixed address opens, sends you on or refuses you - never crashes
RECORD_PAGE_STATUSES = FIXED_PAGE_STATUSES + (404,)  # a page for one record may also say "there is no such record"
ID_ARGUMENT = re.compile(r"(^|_)id$")
RECORD_NUMBERS = (1, 2)


# ------------------------------------------------------------------ finding and opening the pages
def page_routes(app, numbers=None):
    """``[(path, endpoint)]`` for the pages (GET routes) that need no input except a record number.

    Without ``numbers``: the pages with a fixed address. With ``numbers``: the pages whose address only holds record
    numbers (``/animals/<animal_id>`` and the like), once for every number.
    """
    found = []
    with app.test_request_context():
        for rule in sorted(app.url_map.iter_rules(), key=lambda item: item.rule):
            if rule.endpoint == "static" or "GET" not in rule.methods:
                continue
            arguments = sorted(rule.arguments - set(rule.defaults or ()))
            if numbers is None:
                if arguments:
                    continue
                combinations = [{}]
            else:
                if not arguments or not all(ID_ARGUMENT.search(name) for name in arguments):
                    continue
                combinations = [{name: number for name in arguments} for number in numbers]
            for values in combinations:
                try:
                    found.append((url_for(rule.endpoint, **values), rule.endpoint))
                except BuildError:
                    continue
    return found


def open_pages(client, routes, allowed):
    """Open every page. Returns ``(problems, pages)``: what went wrong, and the HTML of each page that opened."""
    problems, pages = [], {}
    for path, endpoint in routes:
        try:
            response = client.get(path)
        except Exception as error:  # the test configuration lets errors through, so a crash shows up right here
            problems.append(f"{path} [{endpoint}] crashed: {type(error).__name__}: {error}")
            continue
        if response.status_code not in allowed:
            problems.append(f"{path} [{endpoint}] answered {response.status_code}")
        elif response.status_code == 200 and response.mimetype == "text/html":
            pages[path] = response.get_data(as_text=True)
    return problems, pages


def sweep(app, client):
    """Open every page of the site (fixed addresses first, then the pages for records 1 and 2)."""
    problems, pages = open_pages(client, page_routes(app), FIXED_PAGE_STATUSES)
    more_problems, more_pages = open_pages(client, page_routes(app, RECORD_NUMBERS), RECORD_PAGE_STATUSES)
    return problems + more_problems, {**pages, **more_pages}


def report(title, problems):
    return f"{title} ({len(problems)}):\n  " + "\n  ".join(problems)


# ------------------------------------------------------------------ links, files and forms inside the pages
class Targets(HTMLParser):
    """Collects what a page points to: links, the files it loads and the addresses its forms send to."""

    def __init__(self):
        super().__init__()
        self.addresses = set()  # links and files
        self.forms = set()  # (action, method)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in ("a", "link"):
            self.addresses.add(values.get("href"))
        elif tag in ("script", "img", "source"):
            self.addresses.add(values.get("src"))
        elif tag == "form":
            self.forms.add((values.get("action"), (values.get("method") or "get").upper()))


def local_path(address):
    """The path (with its query) of an address on this site; ``None`` for other sites, e-mail links and anchors."""
    if not address:
        return None
    address = address.strip().split("#")[0]
    if not address.startswith("/") or address.startswith("//"):
        return None
    return address


def route_accepts(app, path, method):
    """Does the site have a page at ``path`` that answers ``method``?"""
    adapter = app.url_map.bind("localhost")
    try:
        adapter.match(path.split("?")[0], method=method)
    except RequestRedirect:
        return True
    except HTTPException:
        return False
    return True


def broken_targets(app, client, pages):
    """Links, files and form actions on ``pages`` that lead nowhere, as readable sentences."""
    problems, seen = [], {}
    for page_path, html in pages.items():
        targets = Targets()
        targets.feed(html)
        for address in targets.addresses:
            path = local_path(address)
            if path is not None:
                seen.setdefault(path, page_path)  # remember the first page that holds this address
        for action, method in targets.forms:
            path = local_path(action)
            if path is not None and not route_accepts(app, path, method):
                problems.append(f"a form on {page_path} sends {method} to {action}, but no page answers that")
    for path, page_path in sorted(seen.items()):
        try:
            response = client.get(path)
        except Exception as error:
            problems.append(f"{path} (linked from {page_path}) crashed: {type(error).__name__}: {error}")
            continue
        if response.status_code in (404, 405) or response.status_code >= 500:
            problems.append(f"{path} (linked from {page_path}) answered {response.status_code}")
    return problems


# ------------------------------------------------------------------ the sample data
def load_sample_data(app):
    """The administrator that ``init_db.py`` creates, then the sample data. Returns what ``seed()`` returns."""
    create_user(app, C.ROLE_ADMIN, ADMIN_EMAIL, password=ADMIN_PASSWORD)
    with app.app_context():
        return seed_data.seed()


def password_of(email):
    return ADMIN_PASSWORD if email == ADMIN_EMAIL else seed_data.SAMPLE_PASSWORD


@pytest.fixture()
def sample_app(app):
    load_sample_data(app)
    return app


# ------------------------------------------------------------------ the sweep itself must find something
def test_the_sweeps_really_find_the_pages(app):
    assert len(page_routes(app)) >= 50
    assert len(page_routes(app, RECORD_NUMBERS)) >= 2 * 18
    assert ("/", "public.home") in page_routes(app)


@pytest.mark.parametrize("path", ["/", "/login", "/adopt", "/no-such-page"])
def test_every_response_carries_the_basic_security_headers(client, path):
    response = client.get(path)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


# ------------------------------------------------------------------ a brand-new installation
@pytest.mark.parametrize("role", C.ALL_ROLES)
def test_every_page_opens_on_a_new_installation(app, client, role):
    login_as(app, client, role)
    problems, _pages = sweep(app, client)
    assert not problems, report(f"Pages that fail for a {role} on an empty database", problems)


def test_every_public_page_opens_for_a_visitor_on_a_new_installation(app, client):
    problems, _pages = sweep(app, client)
    assert not problems, report("Pages that fail for a visitor on an empty database", problems)


# ------------------------------------------------------------------ the sample data
def test_sample_data_loads_once_and_fills_every_part_of_the_site(app):
    created = load_sample_data(app)
    assert len(created) == len(seed_data.ACCOUNTS)
    with app.app_context():
        assert seed_data.seed() == []  # a second run adds nothing
    assert count(app, User) == len(seed_data.ACCOUNTS) + 1  # plus the administrator
    assert count(app, AnimalReport) == len(seed_data.REPORTS)
    assert count(app, Animal) == len(seed_data.ANIMALS)
    assert count(app, MedicalRecord) == len(seed_data.MEDICAL)
    assert count(app, Vaccination) == len(seed_data.VACCINATIONS)
    assert count(app, ShelterProfile) == 2
    assert count(app, VolunteerTask) >= 3
    assert count(app, AdoptionApplication) >= 3
    assert count(app, AdoptionRecord) == 1
    assert count(app, ContactMessage) >= 1
    assert count(app, Notification) >= 5


def test_sample_data_follows_the_business_rules(app):
    load_sample_data(app)
    with app.app_context():
        for shelter in ShelterProfile.query.all():
            assert shelter.current_count <= shelter.capacity, shelter.shelter_name
        for animal in Animal.query.all():
            if animal.status == C.ANIMAL_AVAILABLE:
                assert animal.shelter_id is not None, f"{animal.name} is listed for adoption but has no shelter"
            if animal.status == C.ANIMAL_ADOPTED:
                assert AdoptionRecord.query.filter_by(animal_id=animal.id).count() == 1, animal.name
        for application in AdoptionApplication.query.filter_by(status=C.ADOPTION_COMPLETED):
            assert application.animal.status == C.ANIMAL_ADOPTED
        for email in (seed_data.FIRST_SAMPLE_EMAIL, "newrescuer@pawconnect.test"):
            assert User.query.filter_by(email=email).one().role == C.ROLE_RESCUER
        assert User.query.filter_by(email="newrescuer@pawconnect.test").one().verification_status == C.VERIFY_PENDING


@pytest.mark.parametrize("email", [account[2] for account in seed_data.ACCOUNTS])
def test_every_sample_account_can_sign_in(sample_app, email):
    response = sign_in(sample_app.test_client(), email, seed_data.SAMPLE_PASSWORD)
    assert response.headers["Location"].endswith(url(sample_app, "dashboard.index"))


def test_the_public_adoption_list_shows_only_animals_that_can_be_adopted(sample_app, client):
    body = client.get("/adopt").get_data(as_text=True)
    with sample_app.app_context():
        wanted = [animal.name for animal in Animal.query.filter_by(status=C.ANIMAL_AVAILABLE)]
        hidden = [animal.name for animal in Animal.query.filter(Animal.status != C.ANIMAL_AVAILABLE)]
    assert wanted and hidden
    for name in wanted:
        assert name in body, f"{name} is available but not listed"
    for name in hidden:
        assert f">{name}<" not in body, f"{name} is not available but is listed"


@pytest.mark.parametrize("email", SAMPLE_ACCOUNTS)
def test_every_page_opens_with_the_sample_data(sample_app, email):
    client = sample_app.test_client()
    sign_in(client, email, password_of(email))
    problems, _pages = sweep(sample_app, client)
    assert not problems, report(f"Pages that fail for {email}", problems)


@pytest.mark.parametrize("email", SAMPLE_ACCOUNTS)
def test_every_link_and_form_on_those_pages_leads_somewhere(sample_app, email):
    client = sample_app.test_client()
    sign_in(client, email, password_of(email))
    _problems, pages = sweep(sample_app, client)
    assert pages, "no page opened at all"
    problems = broken_targets(sample_app, client, pages)
    assert not problems, report(f"Broken links, files or forms for {email}", problems)


def test_the_visitor_pages_have_no_broken_links_either(sample_app, client):
    _problems, pages = sweep(sample_app, client)
    assert pages
    problems = broken_targets(sample_app, client, pages)
    assert not problems, report("Broken links, files or forms for a visitor", problems)


# ------------------------------------------------------------------ CSV exports
def looks_like_a_formula(cell):
    if not cell:
        return False
    if cell[0] in "=+@\t\r":
        return True
    if cell[0] == "-":
        try:
            float(cell)
        except ValueError:
            return True
    return False


@pytest.mark.parametrize("dataset", admin_service.DATASET_KEYS)
def test_every_csv_export_downloads_and_opens_safely(sample_app, dataset):
    client = sample_app.test_client()
    sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    response = client.get(url(sample_app, "admin.export_csv", dataset=dataset))
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/csv")
    assert "attachment" in response.headers["Content-Disposition"]
    text = response.get_data(as_text=True)
    assert text.startswith("﻿")  # lets Excel read accented letters correctly
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert len(rows) >= 2, "the header row and at least one data row are expected"
    assert len({len(row) for row in rows}) == 1, "every row must have the same number of columns"
    risky = [cell for row in rows for cell in row if looks_like_a_formula(cell)]
    assert not risky, f"cells a spreadsheet could run as formulas: {risky[:3]}"


def test_an_unknown_export_is_not_found(sample_app):
    client = sample_app.test_client()
    sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert client.get("/admin/export/passwords.csv").status_code == 404


def test_text_from_a_visitor_cannot_run_as_a_formula_in_an_export(app):
    create_user(app, C.ROLE_ADMIN, ADMIN_EMAIL, password=ADMIN_PASSWORD)
    attack = '=cmd|" /C calc"!A0'
    create_report(app, reporter_name=attack)
    client = app.test_client()
    sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    text = client.get(url(app, "admin.export_csv", dataset="reports")).get_data(as_text=True)
    cells = [cell for row in csv.reader(io.StringIO(text.lstrip("﻿"))) for cell in row]
    assert "'" + attack in cells  # kept as text, with a leading apostrophe
    assert attack not in cells
