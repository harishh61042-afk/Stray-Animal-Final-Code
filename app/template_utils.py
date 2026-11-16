"""Jinja filters, global helpers and the context processor used by every template."""
from flask import current_app, request, url_for
from flask_login import current_user
from markupsafe import Markup, escape

from app import constants as C
from app import navigation
from app.services import rules
from app.utils import timeutil

PLACEHOLDER_TYPES = ("dog", "cat", "cow", "goat", "bird", "rabbit", "monkey", "other")

CDN = {
    "bootstrap_css": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
    "bootstrap_js": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js",
    "icons_css": "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
    "leaflet_css": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
    "leaflet_js": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
    "chart_js": "https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.js",
    "font_css": "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
}
LOCAL_VENDOR = {  # used when USE_LOCAL_VENDOR=1 (files downloaded into app/static/vendor)
    "bootstrap_css": "vendor/bootstrap/bootstrap.min.css",
    "bootstrap_js": "vendor/bootstrap/bootstrap.bundle.min.js",
    "icons_css": "vendor/bootstrap-icons/bootstrap-icons.min.css",
    "leaflet_css": "vendor/leaflet/leaflet.css",
    "leaflet_js": "vendor/leaflet/leaflet.js",
    "chart_js": "vendor/chartjs/chart.umd.js",
    "font_css": None,
}


def library_urls():
    """URLs of the front-end libraries (CDN by default, local copies if enabled)."""
    if current_app.config.get("USE_LOCAL_VENDOR"):
        return {k: (url_for("static", filename=v) if v else "") for k, v in LOCAL_VENDOR.items()}
    return dict(CDN)


# ----------------------------------------------------------------- images
def placeholder_url(animal_type):
    slug = (animal_type or "other").lower()
    if slug not in PLACEHOLDER_TYPES:
        slug = "other"
    return url_for("static", filename=f"images/placeholders/{slug}.svg")


def upload_url(category, filename):
    return url_for("files.uploaded", category=category, filename=filename)


def animal_image_url(animal):
    """Cover photo of an animal, or a drawn placeholder (never a broken image)."""
    image = animal.primary_image
    if image is not None:
        return upload_url(C.UPLOAD_ANIMALS, image.filename)
    return placeholder_url(animal.animal_type)


def report_image_url(report):
    if report.image_filename:
        return upload_url(C.UPLOAD_ANIMAL_REPORTS, report.image_filename)
    return placeholder_url(report.animal_type)


# ----------------------------------------------------------------- filters
def nl2br(text):
    """Escape text and keep its line breaks."""
    if not text:
        return ""
    return Markup(escape(text).replace("\n", Markup("<br>\n")))


def pct(part, whole):
    """Integer percentage (0 when ``whole`` is 0)."""
    try:
        return round(float(part) * 100 / float(whole)) if whole else 0
    except (TypeError, ValueError):
        return 0


def initials(name):
    parts = [p for p in (name or "?").split() if p]
    if not parts:
        return "?"
    return (parts[0][:2] if len(parts) == 1 else parts[0][0] + parts[-1][0]).upper()


def url_with(**changes):
    """URL of the current page with some query parameters changed (used by filters / pagination).

    ``url_with(page=3)`` keeps every other filter; ``url_with(status=None)`` removes one.
    """
    args = {key: value for key, value in request.args.items() if key not in changes}
    args.update({key: value for key, value in changes.items() if value not in (None, "")})
    values = dict(request.view_args or {})
    values.update(args)
    return url_for(request.endpoint, **values)


def endpoint_is(patterns):
    """True if the current endpoint matches one of ``patterns``.

    A pattern ending in ``.`` is a blueprint prefix (``"animals."``), anything
    else must match the full endpoint name exactly.
    """
    endpoint = request.endpoint or ""
    for pattern in patterns:
        if (pattern.endswith(".") and endpoint.startswith(pattern)) or endpoint == pattern:
            return True
    return False


AVATAR_COLORS = ("#1f9d63", "#0ea5a4", "#3b82f6", "#f59f00", "#e5484d", "#8b5cf6", "#ec4899", "#64748b")


def avatar_color(name):
    """Stable colour for a person's initials avatar."""
    return AVATAR_COLORS[sum(ord(ch) for ch in (name or "?")) % len(AVATAR_COLORS)]


def register_template_utils(app):
    offset = lambda: current_app.config.get("DISPLAY_UTC_OFFSET_MINUTES", timeutil.DEFAULT_OFFSET_MINUTES)  # noqa: E731

    app.add_template_filter(lambda v, fmt="%d %b %Y, %I:%M %p": timeutil.format_datetime(v, offset(), fmt), "localdt")
    app.add_template_filter(timeutil.format_date, "localdate")
    app.add_template_filter(timeutil.time_ago, "timeago")
    app.add_template_filter(lambda s: C.STATUS_TONES.get(s, "secondary"), "tone")
    app.add_template_filter(nl2br, "nl2br")
    app.add_template_filter(pct, "pct")
    app.add_template_filter(initials, "initials")
    app.add_template_filter(avatar_color, "avatar_color")
    app.add_template_filter(rules.age_text, "age_text")
    app.add_template_filter(lambda v, fmt="%Y-%m-%dT%H:%M": (timeutil.to_local(v, offset()).strftime(fmt) if v else ""), "input_dt")

    app.jinja_env.globals.update(
        C=C,
        rules=rules,
        library_urls=library_urls,
        animal_image_url=animal_image_url,
        report_image_url=report_image_url,
        placeholder_url=placeholder_url,
        upload_url=upload_url,
        url_with=url_with,
        endpoint_is=endpoint_is,
        nav_active=lambda item: endpoint_is(item["match"]),
        local_today=lambda: timeutil.local_today(offset()),
        utcnow=timeutil.utcnow,
    )

    @app.context_processor
    def inject_common():
        context = {
            "C": C,
            "app_name": current_app.config.get("APP_NAME", "PawConnect"),
            "lib": library_urls(),
            "current_year": timeutil.utcnow().year,
            "contact_email": current_app.config.get("CONTACT_EMAIL"),
            "contact_phone": current_app.config.get("CONTACT_PHONE"),
            "contact_address": current_app.config.get("CONTACT_ADDRESS"),
            "poll_seconds": current_app.config.get("NOTIFICATION_POLL_SECONDS", 30),
            "unread_count": 0,
            "nav_sections": [],
            "search_endpoint": "public.animals",
            "search_placeholder": "Search animals...",
        }
        if current_user.is_authenticated:
            context["nav_sections"] = navigation.sections_for(current_user)
            context["search_endpoint"] = navigation.SEARCH_ENDPOINT.get(current_user.role, "public.animals")
            context["search_placeholder"] = navigation.SEARCH_PLACEHOLDER.get(current_user.role, "Search...")
            try:
                from app.services import notifications

                context["unread_count"] = notifications.unread_count(current_user.id)
            except Exception:  # noqa: BLE001 - never let the badge break a page
                from app.extensions import db

                db.session.rollback()
        return context
