"""Every fixed list / status name used by PawConnect lives here.

Forms, models, services and templates all import from this module so the
exact same strings are used everywhere. This module is pure Python (no Flask).
"""

# ------------------------------------------------------------------ roles
ROLE_ADMIN = "admin"
ROLE_RESCUER = "rescuer"
ROLE_VOLUNTEER = "volunteer"
ROLE_VETERINARIAN = "veterinarian"
ROLE_SHELTER = "shelter"
ROLE_ADOPTER = "adopter"

ALL_ROLES = (ROLE_ADMIN, ROLE_RESCUER, ROLE_VOLUNTEER, ROLE_VETERINARIAN, ROLE_SHELTER, ROLE_ADOPTER)
# Roles a visitor may pick on the registration form (admin is never self-registered).
REGISTRABLE_ROLES = (ROLE_ADOPTER, ROLE_VOLUNTEER, ROLE_RESCUER, ROLE_VETERINARIAN, ROLE_SHELTER)
# Roles whose full permissions need an administrator's verification.
VERIFICATION_REQUIRED_ROLES = (ROLE_RESCUER, ROLE_VETERINARIAN, ROLE_SHELTER)

ROLE_LABELS = {
    ROLE_ADMIN: "Administrator",
    ROLE_RESCUER: "Rescuer",
    ROLE_VOLUNTEER: "Volunteer",
    ROLE_VETERINARIAN: "Veterinarian",
    ROLE_SHELTER: "Animal Shelter",
    ROLE_ADOPTER: "Adopter",
}
ROLE_DESCRIPTIONS = {
    ROLE_ADOPTER: "Browse rescued animals and apply to give one a forever home.",
    ROLE_VOLUNTEER: "Help with rescues, feeding, transport and shelter care.",
    ROLE_RESCUER: "Respond to rescue reports and bring animals to safety. Needs admin verification.",
    ROLE_VETERINARIAN: "Examine, treat and vaccinate rescued animals. Needs admin verification.",
    ROLE_SHELTER: "Give rescued animals a safe place to recover. Needs admin verification.",
}
ROLE_ICONS = {
    ROLE_ADMIN: "bi-shield-check",
    ROLE_RESCUER: "bi-life-preserver",
    ROLE_VOLUNTEER: "bi-people",
    ROLE_VETERINARIAN: "bi-heart-pulse",
    ROLE_SHELTER: "bi-house-heart",
    ROLE_ADOPTER: "bi-balloon-heart",
}
ROLE_DASHBOARD_ENDPOINT = {
    ROLE_ADMIN: "dashboard.admin",
    ROLE_RESCUER: "dashboard.rescuer",
    ROLE_VOLUNTEER: "dashboard.volunteer",
    ROLE_VETERINARIAN: "dashboard.veterinarian",
    ROLE_SHELTER: "dashboard.shelter",
    ROLE_ADOPTER: "dashboard.adopter",
}

# ------------------------------------------------------- account / approval
ACCOUNT_ACTIVE = "active"
ACCOUNT_INACTIVE = "inactive"
ACCOUNT_SUSPENDED = "suspended"
ACCOUNT_STATUSES = (ACCOUNT_ACTIVE, ACCOUNT_INACTIVE, ACCOUNT_SUSPENDED)

VERIFY_NOT_REQUIRED = "Not Required"
VERIFY_PENDING = "Pending"
VERIFY_VERIFIED = "Verified"
VERIFY_REJECTED = "Rejected"
VERIFICATION_STATUSES = (VERIFY_NOT_REQUIRED, VERIFY_PENDING, VERIFY_VERIFIED, VERIFY_REJECTED)

APPLICATION_PENDING = "Pending"
APPLICATION_APPROVED = "Approved"
APPLICATION_REJECTED = "Rejected"
VOLUNTEER_APPLICATION_STATUSES = (APPLICATION_PENDING, APPLICATION_APPROVED, APPLICATION_REJECTED)

# -------------------------------------------------------------- rescue reports
EMERGENCY_CRITICAL = "Critical"
EMERGENCY_HIGH = "High"
EMERGENCY_MEDIUM = "Medium"
EMERGENCY_LOW = "Low"
EMERGENCY_LEVELS = (EMERGENCY_CRITICAL, EMERGENCY_HIGH, EMERGENCY_MEDIUM, EMERGENCY_LOW)
EMERGENCY_RANK = {EMERGENCY_CRITICAL: 0, EMERGENCY_HIGH: 1, EMERGENCY_MEDIUM: 2, EMERGENCY_LOW: 3}
EMERGENCY_TONES = {EMERGENCY_CRITICAL: "danger", EMERGENCY_HIGH: "warning", EMERGENCY_MEDIUM: "info", EMERGENCY_LOW: "success"}
EMERGENCY_COLORS = {EMERGENCY_CRITICAL: "#e5484d", EMERGENCY_HIGH: "#f59f00", EMERGENCY_MEDIUM: "#3b82f6", EMERGENCY_LOW: "#22a06b"}

REPORT_PENDING = "Pending"
REPORT_UNDER_REVIEW = "Under Review"
REPORT_ASSIGNED = "Assigned"
REPORT_IN_PROGRESS = "Rescue in Progress"
REPORT_RESCUED = "Rescued"
REPORT_CLOSED = "Closed"
REPORT_REJECTED = "Rejected"
REPORT_STATUSES = (
    REPORT_PENDING, REPORT_UNDER_REVIEW, REPORT_ASSIGNED, REPORT_IN_PROGRESS,
    REPORT_RESCUED, REPORT_CLOSED, REPORT_REJECTED,
)
# Reports that still need work from the rescue team.
OPEN_REPORT_STATUSES = (REPORT_PENDING, REPORT_UNDER_REVIEW, REPORT_ASSIGNED, REPORT_IN_PROGRESS)
ACTIVE_RESCUE_STATUSES = (REPORT_ASSIGNED, REPORT_IN_PROGRESS)

ASSIGNMENT_ASSIGNED = "Assigned"
ASSIGNMENT_ACCEPTED = "Accepted"
ASSIGNMENT_REJECTED = "Rejected"
ASSIGNMENT_COMPLETED = "Completed"
ASSIGNMENT_CANCELLED = "Cancelled"
ASSIGNMENT_STATUSES = (ASSIGNMENT_ASSIGNED, ASSIGNMENT_ACCEPTED, ASSIGNMENT_REJECTED, ASSIGNMENT_COMPLETED, ASSIGNMENT_CANCELLED)
ACTIVE_ASSIGNMENT_STATUSES = (ASSIGNMENT_ASSIGNED, ASSIGNMENT_ACCEPTED)

ANIMAL_TYPES = ("Dog", "Cat", "Cow", "Goat", "Bird", "Rabbit", "Monkey", "Other")
ANIMAL_CONDITIONS = (
    "Injured", "Sick", "Hungry / Malnourished", "Abandoned", "Trapped / Stuck",
    "Hit by vehicle", "Newborn / Orphaned", "Aggressive / Dangerous", "Other",
)

# ------------------------------------------------------------------- animals
ANIMAL_REPORTED = "Reported"
ANIMAL_RESCUED = "Rescued"
ANIMAL_TREATMENT = "Under Medical Treatment"
ANIMAL_RECOVERING = "Recovering"
ANIMAL_IN_SHELTER = "In Shelter"
ANIMAL_AVAILABLE = "Available for Adoption"
ANIMAL_ADOPTED = "Adopted"
ANIMAL_STATUSES = (
    ANIMAL_REPORTED, ANIMAL_RESCUED, ANIMAL_TREATMENT, ANIMAL_RECOVERING,
    ANIMAL_IN_SHELTER, ANIMAL_AVAILABLE, ANIMAL_ADOPTED,
)
GENDERS = ("Male", "Female", "Unknown")
REHAB_STATUSES = ("Not Started", "In Progress", "Completed")

MEDICAL_HEALTHY = "Healthy"
MEDICAL_OBSERVATION = "Under Observation"
MEDICAL_TREATMENT = "Under Treatment"
MEDICAL_RECOVERING = "Recovering"
MEDICAL_CRITICAL = "Critical"
MEDICAL_STATUSES = (MEDICAL_HEALTHY, MEDICAL_OBSERVATION, MEDICAL_TREATMENT, MEDICAL_RECOVERING, MEDICAL_CRITICAL)

VACC_NONE = "Not Vaccinated"
VACC_PARTIAL = "Partially Vaccinated"
VACC_FULL = "Fully Vaccinated"
VACC_DUE = "Booster Due"
VACCINATION_STATUSES = (VACC_NONE, VACC_PARTIAL, VACC_FULL, VACC_DUE)
COMMON_VACCINES = (
    "Rabies", "DHPP (Distemper, Hepatitis, Parvo, Parainfluenza)", "Leptospirosis",
    "Bordetella", "FVRCP (Feline)", "Feline Leukemia", "Other",
)

AGE_GROUPS = (
    ("baby", "Baby (under 1 year)"),
    ("young", "Young (1 - 3 years)"),
    ("adult", "Adult (3 - 8 years)"),
    ("senior", "Senior (8+ years)"),
)
AGE_GROUP_RANGES = {"baby": (0, 12), "young": (12, 36), "adult": (36, 96), "senior": (96, None)}

DISCHARGE_REASONS = ("Adopted", "Transferred to another shelter", "Released back", "Deceased", "Other")

# ----------------------------------------------------------- volunteer tasks
TASK_TYPES = (
    "Animal Food Distribution", "Rescue Assistance", "Transportation Support", "Shelter Cleaning",
    "Animal Feeding", "Medical Assistance Support", "Adoption Event Assistance",
)
TASK_AVAILABLE = "Available"
TASK_ASSIGNED = "Assigned"
TASK_ACCEPTED = "Accepted"
TASK_IN_PROGRESS = "In Progress"
TASK_COMPLETED = "Completed"
TASK_CANCELLED = "Cancelled"
TASK_STATUSES = (TASK_AVAILABLE, TASK_ASSIGNED, TASK_ACCEPTED, TASK_IN_PROGRESS, TASK_COMPLETED, TASK_CANCELLED)

TA_ASSIGNED = "Assigned"
TA_ACCEPTED = "Accepted"
TA_DECLINED = "Declined"
TA_IN_PROGRESS = "In Progress"
TA_COMPLETED = "Completed"
TA_CANCELLED = "Cancelled"
TASK_ASSIGNMENT_STATUSES = (TA_ASSIGNED, TA_ACCEPTED, TA_DECLINED, TA_IN_PROGRESS, TA_COMPLETED, TA_CANCELLED)
INACTIVE_TASK_ASSIGNMENT_STATUSES = (TA_DECLINED, TA_CANCELLED)

# ------------------------------------------------------------------ adoption
ADOPTION_PENDING = "Pending"
ADOPTION_UNDER_REVIEW = "Under Review"
ADOPTION_APPROVED = "Approved"
ADOPTION_REJECTED = "Rejected"
ADOPTION_COMPLETED = "Completed"
ADOPTION_CANCELLED = "Cancelled"
ADOPTION_STATUSES = (
    ADOPTION_PENDING, ADOPTION_UNDER_REVIEW, ADOPTION_APPROVED,
    ADOPTION_REJECTED, ADOPTION_COMPLETED, ADOPTION_CANCELLED,
)
ACTIVE_ADOPTION_STATUSES = (ADOPTION_PENDING, ADOPTION_UNDER_REVIEW, ADOPTION_APPROVED)
HOUSING_TYPES = ("Own house", "Rented house", "Apartment / Flat", "Farm / Rural property", "Other")

# ------------------------------------------------------------- notifications
NOTIFY_RESCUE = "rescue"
NOTIFY_TASK = "task"
NOTIFY_MEDICAL = "medical"
NOTIFY_ADOPTION = "adoption"
NOTIFY_ACCOUNT = "account"
NOTIFY_SYSTEM = "system"
NOTIFICATION_CATEGORIES = (NOTIFY_RESCUE, NOTIFY_TASK, NOTIFY_MEDICAL, NOTIFY_ADOPTION, NOTIFY_ACCOUNT, NOTIFY_SYSTEM)
NOTIFICATION_ICONS = {
    NOTIFY_RESCUE: "bi-life-preserver",
    NOTIFY_TASK: "bi-list-check",
    NOTIFY_MEDICAL: "bi-heart-pulse",
    NOTIFY_ADOPTION: "bi-balloon-heart",
    NOTIFY_ACCOUNT: "bi-person-check",
    NOTIFY_SYSTEM: "bi-bell",
}

CONTACT_NEW = "New"
CONTACT_RESOLVED = "Resolved"
CONTACT_STATUSES = (CONTACT_NEW, CONTACT_RESOLVED)

# --------------------------------------------------------------------- uploads
UPLOAD_ANIMAL_REPORTS = "animal_reports"
UPLOAD_ANIMALS = "animals"
UPLOAD_MEDICAL = "medical_documents"
UPLOAD_VERIFICATION = "verification_documents"
UPLOAD_CATEGORIES = (UPLOAD_ANIMAL_REPORTS, UPLOAD_ANIMALS, UPLOAD_MEDICAL, UPLOAD_VERIFICATION)
ALLOWED_IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "gif", "webp")
ALLOWED_DOCUMENT_EXTENSIONS = ("pdf", "png", "jpg", "jpeg")

# ------------------------------------------------------------ badge colours
# Bootstrap-style tone for every status string (used by the status_badge macro).
STATUS_TONES = {
    # reports / assignments
    "Pending": "warning", "Under Review": "info", "Assigned": "primary", "Rescue in Progress": "primary",
    "Rescued": "success", "Closed": "secondary", "Rejected": "danger", "Accepted": "success",
    "Completed": "success", "Cancelled": "secondary", "Declined": "danger",
    # animals
    "Reported": "warning", "Under Medical Treatment": "danger", "Recovering": "info",
    "In Shelter": "primary", "Available for Adoption": "success", "Adopted": "dark",
    # medical / vaccination / rehab
    "Healthy": "success", "Under Observation": "info", "Under Treatment": "warning", "Critical": "danger",
    "Not Vaccinated": "danger", "Partially Vaccinated": "warning", "Fully Vaccinated": "success", "Booster Due": "warning",
    "Not Started": "secondary",
    # tasks
    "Available": "info", "In Progress": "primary",
    # approvals / accounts
    "Approved": "success", "Verified": "success", "Not Required": "secondary",
    "active": "success", "inactive": "secondary", "suspended": "danger",
    # emergency levels
    "High": "warning", "Medium": "info", "Low": "success",
    # contact messages
    "New": "warning", "Resolved": "success",
}


def choices(values):
    """Turn a tuple of strings into WTForms ``(value, label)`` choices."""
    return [(value, value) for value in values]


def blank_choices(values, blank_label="-- Select --"):
    """Same as :func:`choices` but with an empty first option."""
    return [("", blank_label)] + choices(values)
