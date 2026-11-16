"""Sidebar navigation for every role (one place, so links can be verified)."""
from app import constants as C


def _i(label, endpoint, icon, match=None, badge=None, approved_only=False):
    """One sidebar link. ``match`` lists endpoint prefixes that mark it active."""
    return {"label": label, "endpoint": endpoint, "icon": icon, "match": match or [endpoint], "badge": badge, "approved_only": approved_only}


_COMMON_BOTTOM = [
    _i("Notifications", "notifications.index", "bi-bell", ["notifications."], badge="notifications"),
    _i("My Profile", "account.profile", "bi-person-circle", ["account.profile", "account.change_password"]),
]

NAV = {
    C.ROLE_ADMIN: [
        ("Overview", [_i("Dashboard", "dashboard.admin", "bi-grid-1x2", ["dashboard."])]),
        ("Rescue", [
            _i("Rescue Reports", "rescue.manage", "bi-life-preserver", ["rescue.", "reports."]),
            _i("Rescue Map", "maps.overview", "bi-geo-alt", ["maps."]),
        ]),
        ("Animals & Care", [
            _i("Animals", "animals.index", "bi-heart", ["animals."]),
            _i("Medical Records", "medical.index", "bi-clipboard2-pulse", ["medical.index", "medical.animal_profile", "medical.add_record", "medical.record_detail", "medical.edit_record"]),
            _i("Vaccinations", "medical.vaccinations", "bi-shield-plus", ["medical.vaccinations"]),
            _i("Shelters", "shelters.index", "bi-house-heart", ["shelters."]),
        ]),
        ("Adoption", [
            _i("Adoption Requests", "adoption.manage", "bi-balloon-heart", ["adoption.manage", "adoption.detail"]),
            _i("Adoption Records", "adoption.records", "bi-journal-check", ["adoption.records"]),
        ]),
        ("People", [
            _i("Users", "admin.users", "bi-people", ["admin.users", "admin.user_detail", "admin.user_create"]),
            _i("Verifications", "admin.verifications", "bi-patch-check", ["admin.verifications"]),
            _i("Volunteers", "volunteers.index", "bi-person-heart", ["volunteers.index", "volunteers.detail"]),
            _i("Volunteer Applications", "volunteers.applications", "bi-person-lines-fill", ["volunteers.applications"]),
            _i("Volunteer Tasks", "tasks.manage", "bi-list-check", ["tasks."]),
        ]),
        ("System", [
            _i("Reports & Analytics", "admin.reports", "bi-bar-chart-line", ["admin.reports", "admin.export_csv"]),
            _i("Activity Log", "admin.audit_log", "bi-activity", ["admin.audit_log"]),
            _i("Contact Messages", "admin.messages", "bi-envelope", ["admin.messages"]),
            _i("Send Notification", "admin.send_notification", "bi-megaphone", ["admin.send_notification"]),
        ]),
        ("Account", _COMMON_BOTTOM),
    ],
    C.ROLE_RESCUER: [
        ("Overview", [_i("Dashboard", "dashboard.rescuer", "bi-grid-1x2", ["dashboard."])]),
        ("Rescue Work", [
            _i("Incoming Reports", "rescue.manage", "bi-inbox", ["rescue.manage", "reports.detail"]),
            _i("My Cases", "rescue.my_cases", "bi-life-preserver", ["rescue.my_cases", "rescue.register_animal"]),
            _i("Case History", "rescue.history", "bi-clock-history", ["rescue.history"]),
            _i("Rescue Map", "maps.overview", "bi-geo-alt", ["maps."]),
        ]),
        ("Care & Coordination", [
            _i("Animals", "animals.index", "bi-heart", ["animals."]),
            _i("Volunteer Tasks", "tasks.manage", "bi-list-check", ["tasks."]),
            _i("Volunteers", "volunteers.index", "bi-person-heart", ["volunteers."]),
        ]),
        ("Account", _COMMON_BOTTOM),
    ],
    C.ROLE_VOLUNTEER: [
        ("Overview", [_i("Dashboard", "dashboard.volunteer", "bi-grid-1x2", ["dashboard."])]),
        ("Volunteering", [
            _i("My Application", "volunteers.my_application", "bi-person-vcard", ["volunteers.my_application"]),
            _i("Available Tasks", "tasks.available", "bi-search-heart", ["tasks.available"], approved_only=True),
            _i("My Tasks", "tasks.mine", "bi-list-check", ["tasks.mine", "tasks.detail"], approved_only=True),
            _i("Task History", "tasks.history", "bi-clock-history", ["tasks.history"], approved_only=True),
        ]),
        ("Account", _COMMON_BOTTOM),
    ],
    C.ROLE_VETERINARIAN: [
        ("Overview", [_i("Dashboard", "dashboard.veterinarian", "bi-grid-1x2", ["dashboard."])]),
        ("Medical Care", [
            _i("Assigned Animals", "animals.index", "bi-heart-pulse", ["animals."]),
            _i("Unassigned Animals", "medical.unassigned", "bi-hospital", ["medical.unassigned"]),
            _i("Medical Records", "medical.index", "bi-clipboard2-pulse", ["medical.index", "medical.animal_profile", "medical.add_record", "medical.record_detail", "medical.edit_record"]),
            _i("Vaccinations", "medical.vaccinations", "bi-shield-plus", ["medical.vaccinations"]),
        ]),
        ("Account", _COMMON_BOTTOM),
    ],
    C.ROLE_SHELTER: [
        ("Overview", [_i("Dashboard", "dashboard.shelter", "bi-grid-1x2", ["dashboard."])]),
        ("Shelter", [
            _i("Our Animals", "animals.index", "bi-heart", ["animals."]),
            _i("Admissions", "shelters.admissions", "bi-box-arrow-in-down", ["shelters.admissions"]),
            _i("Medical Records", "medical.index", "bi-clipboard2-pulse", ["medical."]),
            _i("Shelter Profile", "shelters.my_profile", "bi-house-gear", ["shelters.my_profile"]),
        ]),
        ("Adoption", [
            _i("Adoption Requests", "adoption.manage", "bi-balloon-heart", ["adoption.manage", "adoption.detail"]),
            _i("Adoption Records", "adoption.records", "bi-journal-check", ["adoption.records"]),
        ]),
        ("Account", _COMMON_BOTTOM),
    ],
    C.ROLE_ADOPTER: [
        ("Overview", [_i("Dashboard", "dashboard.adopter", "bi-grid-1x2", ["dashboard."])]),
        ("Adoption", [
            _i("Browse Animals", "public.animals", "bi-search-heart", ["public.animals", "public.animal_detail", "adoption.apply"]),
            _i("My Applications", "adoption.my_applications", "bi-file-earmark-heart", ["adoption.my_applications", "adoption.detail"]),
            _i("Adoption History", "adoption.history", "bi-journal-check", ["adoption.history"]),
            _i("Shelter Directory", "shelters.directory", "bi-house-heart", ["shelters.directory", "shelters.detail"]),
        ]),
        ("Account", _COMMON_BOTTOM),
    ],
}

# Shown to rescuers / veterinarians / shelters until an administrator verifies them.
PENDING_NAV = [
    ("Account", [_i("Verification Status", "account.pending", "bi-hourglass-split", ["account.pending"])] + _COMMON_BOTTOM),
]

# Where the search box in the top bar sends the visitor.
SEARCH_ENDPOINT = {
    C.ROLE_ADMIN: "animals.index",
    C.ROLE_RESCUER: "rescue.manage",
    C.ROLE_VOLUNTEER: "tasks.available",
    C.ROLE_VETERINARIAN: "animals.index",
    C.ROLE_SHELTER: "animals.index",
    C.ROLE_ADOPTER: "public.animals",
}
SEARCH_PLACEHOLDER = {
    C.ROLE_ADMIN: "Search animals by name or ID...",
    C.ROLE_RESCUER: "Search reports...",
    C.ROLE_VOLUNTEER: "Search tasks...",
    C.ROLE_VETERINARIAN: "Search animals by name or ID...",
    C.ROLE_SHELTER: "Search animals by name or ID...",
    C.ROLE_ADOPTER: "Search animals to adopt...",
}


def sections_for(user):
    """Navigation sections the given user should see."""
    if not user.is_verified:
        return PENDING_NAV
    sections = []
    for title, items in NAV.get(user.role, []):
        visible = [i for i in items if not (i["approved_only"] and not user.is_approved_volunteer)]
        if visible:
            sections.append((title, visible))
    return sections


def all_nav_endpoints():
    """Every endpoint referenced by the navigation (used by the link checker)."""
    endpoints = set()
    for sections in list(NAV.values()) + [PENDING_NAV]:
        for _title, items in sections:
            endpoints.update(item["endpoint"] for item in items)
    endpoints.update(SEARCH_ENDPOINT.values())
    return endpoints
