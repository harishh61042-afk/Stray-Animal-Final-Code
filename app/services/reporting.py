"""Numbers and charts for the administrator's analytics page.

Everything is counted from the database for the chosen date range. Dates are local dates; timestamps are stored
as UTC and shifted with the configured display offset. Time buckets (days, months or years) are made in Python,
so the same code runs on MySQL and on SQLite. Nothing here is a made-up figure: an empty database simply
produces zeros and empty charts.
"""
from datetime import date, datetime, time, timedelta

from flask import current_app

from app import constants as C
from app.extensions import db
from app.models import (
    AdoptionApplication, AdoptionRecord, Animal, AnimalReport, MedicalRecord, RescueAssignment, ShelterAdmission,
    User, Vaccination, VolunteerProfile, VolunteerTask, VolunteerTaskAssignment,
)
from app.services import animal_service, medical_service, rules, stats
from app.utils import timeutil
from app.utils.timeutil import local_today, month_start, to_local

GREEN, TEAL, AMBER, CORAL, BLUE, VIOLET = stats.GREEN, stats.TEAL, stats.AMBER, stats.CORAL, stats.BLUE, stats.VIOLET
SLATE = "#64748b"
MIN_DATE = date(2000, 1, 1)
MAX_SPAN_DAYS = 3660  # about ten years
MEDICAL_COLORS = {
    C.MEDICAL_HEALTHY: GREEN, C.MEDICAL_OBSERVATION: BLUE, C.MEDICAL_TREATMENT: AMBER,
    C.MEDICAL_RECOVERING: TEAL, C.MEDICAL_CRITICAL: CORAL,
}


def display_offset():
    return current_app.config.get("DISPLAY_UTC_OFFSET_MINUTES", timeutil.DEFAULT_OFFSET_MINUTES)


# ------------------------------------------------------------------- dates
def parse_date(value):
    """``YYYY-MM-DD`` text -> ``date`` (``None`` when missing or invalid)."""
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_dates(args):
    """``(start, end)`` from query-string values; each is ``None`` when missing or invalid."""
    start, end = parse_date(args.get("start")), parse_date(args.get("end"))
    if start and end and start > end:
        start, end = end, start
    return start, end


def parse_range(args, today=None):
    """The date range of the analytics page: defaults to the last 12 calendar months, never in the future."""
    today = today or local_today(display_offset())
    start, end = parse_dates(args)
    end = min(end, today) if end else today
    start = start or month_start(today, 11)
    start = min(max(start, MIN_DATE), end)
    if (end - start).days > MAX_SPAN_DAYS:
        start = end - timedelta(days=MAX_SPAN_DAYS)
    return start, end


def earliest_activity():
    """Local date of the oldest record (report, animal, application or account), or ``None`` on an empty database."""
    days = []
    for column in (AnimalReport.created_at, Animal.created_at, AdoptionApplication.created_at, User.created_at):
        stamp = db.session.query(db.func.min(column)).scalar()
        if stamp is not None:
            days.append(to_local(stamp, display_offset()).date())
    return min(days) if days else None


def presets(today=None):
    """Quick ranges shown above the date pickers."""
    today = today or local_today(display_offset())
    first = earliest_activity() or (today - timedelta(days=364))
    return [
        {"key": "30d", "label": "Last 30 days", "start": today - timedelta(days=29), "end": today},
        {"key": "90d", "label": "Last 90 days", "start": today - timedelta(days=89), "end": today},
        {"key": "12m", "label": "Last 12 months", "start": month_start(today, 11), "end": today},
        {"key": "year", "label": "This year", "start": date(today.year, 1, 1), "end": today},
        {"key": "all", "label": "All time", "start": max(first, MIN_DATE), "end": today},
    ]


def date_clauses(column, start=None, end=None, is_date=False):
    """WHERE clauses limiting ``column`` to the local dates ``start`` .. ``end`` (inclusive; either may be ``None``).

    ``is_date`` is True for ``Date`` columns; ``DateTime`` columns hold UTC and are shifted by the display offset.
    """
    clauses = []
    if is_date:
        if start:
            clauses.append(column >= start)
        if end:
            clauses.append(column <= end)
        return clauses
    shift = timedelta(minutes=display_offset())
    if start:
        clauses.append(column >= datetime.combine(start, time.min) - shift)
    if end:
        clauses.append(column < datetime.combine(end + timedelta(days=1), time.min) - shift)
    return clauses


# ----------------------------------------------------------- time buckets
def granularity(start, end):
    days = (end - start).days + 1
    if days <= 62:
        return "day"
    return "month" if days <= 1100 else "year"


def _key(day, mode):
    if mode == "day":
        return day
    if mode == "month":
        return (day.year, day.month)
    return day.year


def bucket_keys(start, end, mode):
    keys = []
    if mode == "day":
        current = start
        while current <= end:
            keys.append(current)
            current += timedelta(days=1)
    elif mode == "month":
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            keys.append((year, month))
            month += 1
            if month > 12:
                year, month = year + 1, 1
    else:
        keys = list(range(start.year, end.year + 1))
    return keys


def bucket_labels(keys, mode):
    labels = []
    for index, key in enumerate(keys):
        if mode == "day":
            labels.append(key.strftime("%d %b"))
        elif mode == "month":
            year, month = key
            name = date(year, month, 1).strftime("%b")
            labels.append(f"{name} '{str(year)[2:]}" if index == 0 or month == 1 else name)
        else:
            labels.append(str(key))
    return labels


def series(column, start, end, mode, is_date=False, conditions=(), value=None):
    """Rows (or the sum of ``value``) per time bucket: ``{"labels": [...], "values": [...]}``."""
    keys = bucket_keys(start, end, mode)
    position = {key: index for index, key in enumerate(keys)}
    totals = [0] * len(keys)
    offset = display_offset()
    query = db.session.query(column, value) if value is not None else db.session.query(column)
    for row in query.filter(*date_clauses(column, start, end, is_date), *conditions).all():
        stamp = row[0]
        if stamp is None:
            continue
        day = stamp if is_date else to_local(stamp, offset)
        if isinstance(day, datetime):
            day = day.date()
        index = position.get(_key(day, mode))
        if index is not None:
            totals[index] += (row[1] or 0) if value is not None else 1
    if value is not None:
        totals = [round(float(total), 1) for total in totals]
    return {"labels": bucket_labels(keys, mode), "values": totals}


# ----------------------------------------------------------------- helpers
def average(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def _hours(start, finish):
    if start is None or finish is None or finish < start:
        return None
    return (finish - start).total_seconds() / 3600


def duration_text(hours):
    """"35 min", "6.5 h" or "3.2 days" for an average length of time."""
    if hours is None:
        return "No data yet"
    if hours < 1:
        return f"{max(1, round(hours * 60))} min"
    if hours < 48:
        return f"{round(hours, 1):g} h"
    return f"{round(hours / 24, 1):g} days"


def top_bars(counts, limit=6):
    """``[{label, value, pct}]`` for the biggest groups (``pct`` is relative to the largest one)."""
    items = sorted(((name, count) for name, count in counts.items() if name and count),
                   key=lambda item: (-item[1], str(item[0])))[:limit]
    top = items[0][1] if items else 0
    return [{"label": name, "value": count, "pct": stats.percent(count, top)} for name, count in items]


def _doughnut(counts, order, colors, label, title):
    names = [name for name in order if counts.get(name)]
    chart = {
        "type": "doughnut", "labels": names,
        "datasets": [{"label": label, "data": [counts[name] for name in names],
                      "colors": [colors.get(name, SLATE) for name in names]}],
        "center": {"text": str(sum(counts.get(name, 0) for name in names)), "title": title},
    }
    legend = [{"label": name, "value": counts[name], "color": colors.get(name, SLATE)} for name in names]
    return chart, legend


def _category_bars(counts, order, colors, label, labels=None):
    return {
        "type": "bar", "labels": list(labels or order),
        "datasets": [{"label": label, "data": [counts.get(name, 0) for name in order],
                      "colors": [colors.get(name, GREEN) for name in order]}],
        "legend": False,
    }


def _trend(first, second, first_label, second_label, kind="bar"):
    datasets = [{"label": first_label, "data": first["values"], "color": GREEN}]
    if second is not None:
        datasets.append({"label": second_label, "data": second["values"], "color": BLUE})
    return {"type": kind, "labels": first["labels"], "datasets": datasets, "legend": second is not None}


class Window:
    """A date range plus the equally long range just before it (for "compared with the previous period")."""

    def __init__(self, start, end):
        self.start, self.end = start, end
        self.days = (end - start).days + 1
        self.prev_end = start - timedelta(days=1)
        self.prev_start = self.prev_end - timedelta(days=self.days - 1)
        self.can_compare = self.prev_start >= MIN_DATE
        self.mode = granularity(start, end)

    def clauses(self, column, is_date=False):
        return date_clauses(column, self.start, self.end, is_date)

    def count(self, model, column, is_date=False, conditions=()):
        return db.session.query(db.func.count(model.id)).filter(*self.clauses(column, is_date), *conditions).scalar() or 0

    def compare(self, model, column, is_date=False, conditions=()):
        """``(rows in the range, percent change against the previous range or None)``."""
        now = self.count(model, column, is_date, conditions)
        if not self.can_compare:
            return now, None
        before = db.session.query(db.func.count(model.id)).filter(
            *date_clauses(column, self.prev_start, self.prev_end, is_date), *conditions).scalar() or 0
        return now, stats.pct_change(now, before)

    def group(self, column, date_column, is_date=False, conditions=()):
        return stats.group_counts(column, *self.clauses(date_column, is_date), *conditions)

    def series(self, column, is_date=False, conditions=(), value=None):
        return series(column, self.start, self.end, self.mode, is_date, conditions, value)


# ---------------------------------------------------------------- sections
def _rescue(w):
    created = AnimalReport.created_at
    received, delta = w.compare(AnimalReport, created)
    status = w.group(AnimalReport.status, created)
    emergency = w.group(AnimalReport.emergency_level, created)
    resolved = status.get(C.REPORT_RESCUED, 0) + status.get(C.REPORT_CLOSED, 0)

    first_assigned = (
        db.session.query(AnimalReport.created_at, db.func.min(RescueAssignment.assigned_at))
        .select_from(AnimalReport)
        .join(RescueAssignment, RescueAssignment.report_id == AnimalReport.id)
        .filter(*w.clauses(created))
        .group_by(AnimalReport.id, AnimalReport.created_at)
        .all()
    )
    finished = (
        db.session.query(AnimalReport.created_at, RescueAssignment.completed_at)
        .select_from(AnimalReport)
        .join(RescueAssignment, RescueAssignment.report_id == AnimalReport.id)
        .filter(RescueAssignment.completed_at.isnot(None), *w.clauses(created))
        .all()
    )
    to_assign = [h for h in (_hours(a, b) for a, b in first_assigned) if h is not None]
    to_rescue = [h for h in (_hours(a, b) for a, b in finished) if h is not None]

    open_query = AnimalReport.query.filter(AnimalReport.status.in_(C.OPEN_REPORT_STATUSES))
    status_chart, status_legend = _doughnut(status, C.REPORT_STATUSES, stats.REPORT_STATUS_COLORS, "Reports", "reports")
    trend = _trend(
        w.series(created),
        w.series(RescueAssignment.completed_at, conditions=(RescueAssignment.completed_at.isnot(None),)),
        "Reports received", "Rescues completed")
    return {
        "received": received, "delta": delta, "resolved": resolved, "resolved_percent": stats.percent(resolved, received),
        "open_now": open_query.count(),
        "critical_now": open_query.filter(AnimalReport.emergency_level == C.EMERGENCY_CRITICAL).count(),
        "avg_assign": duration_text(average(to_assign)), "avg_assign_count": len(to_assign),
        "avg_rescue": duration_text(average(to_rescue)), "avg_rescue_count": len(to_rescue),
        "trend_chart": trend, "status_chart": status_chart, "status_legend": status_legend,
        "emergency_chart": _category_bars(emergency, C.EMERGENCY_LEVELS, C.EMERGENCY_COLORS, "Reports"),
        "type_bars": top_bars(w.group(AnimalReport.animal_type, created)),
        "condition_bars": top_bars(w.group(AnimalReport.animal_condition, created)),
    }


def _animals(w):
    registered, delta = w.compare(Animal, Animal.created_at)
    now = stats.group_counts(Animal.status)
    medical = stats.group_counts(Animal.medical_status)
    status_chart, status_legend = _doughnut(now, C.ANIMAL_STATUSES, stats.ANIMAL_STATUS_COLORS, "Animals", "animals")
    trend = _trend(
        w.series(Animal.created_at), w.series(AdoptionRecord.adoption_date, is_date=True),
        "Animals registered", "Animals adopted")
    return {
        "registered": registered, "delta": delta, "total": sum(now.values()),
        "in_care": sum(now.get(name, 0) for name in stats.IN_CARE_STATUSES),
        "available": now.get(C.ANIMAL_AVAILABLE, 0), "adopted": now.get(C.ANIMAL_ADOPTED, 0),
        "trend_chart": trend, "status_chart": status_chart, "status_legend": status_legend,
        "medical_chart": _category_bars(medical, C.MEDICAL_STATUSES, MEDICAL_COLORS, "Animals"),
        "type_bars": top_bars(w.group(Animal.animal_type, Animal.created_at)),
    }


def _adoption(w):
    created = AdoptionApplication.created_at
    received, delta = w.compare(AdoptionApplication, created)
    completed, completed_delta = w.compare(AdoptionRecord, AdoptionRecord.adoption_date, is_date=True)
    status = w.group(AdoptionApplication.status, created)
    positive = status.get(C.ADOPTION_APPROVED, 0) + status.get(C.ADOPTION_COMPLETED, 0)
    decided = positive + status.get(C.ADOPTION_REJECTED, 0)

    waits = (
        db.session.query(AdoptionRecord.adoption_date, AdoptionApplication.created_at)
        .select_from(AdoptionRecord)
        .join(AdoptionApplication, AdoptionApplication.id == AdoptionRecord.application_id)
        .filter(*w.clauses(AdoptionRecord.adoption_date, is_date=True))
        .all()
    )
    offset = display_offset()
    days = [max(0, (adopted - to_local(applied, offset).date()).days) for adopted, applied in waits if adopted and applied]
    by_type = dict(
        db.session.query(Animal.animal_type, db.func.count(AdoptionRecord.id))
        .select_from(AdoptionRecord)
        .join(Animal, Animal.id == AdoptionRecord.animal_id)
        .filter(*w.clauses(AdoptionRecord.adoption_date, is_date=True))
        .group_by(Animal.animal_type)
        .all()
    )
    status_chart, status_legend = _doughnut(
        status, C.ADOPTION_STATUSES, stats.ADOPTION_STATUS_COLORS, "Applications", "applications")
    trend = _trend(
        w.series(created), w.series(AdoptionRecord.adoption_date, is_date=True),
        "Applications received", "Adoptions completed")
    return {
        "received": received, "delta": delta, "completed": completed, "completed_delta": completed_delta,
        "approval_percent": stats.percent(positive, decided) if decided else None, "decided": decided,
        "avg_days": duration_text(average(days) * 24) if days else "No data yet", "avg_days_count": len(days),
        "trend_chart": trend, "status_chart": status_chart, "status_legend": status_legend,
        "type_bars": top_bars(by_type),
    }


def _medical(w):
    exams, exams_delta = w.compare(MedicalRecord, MedicalRecord.examination_date, is_date=True)
    shots, shots_delta = w.compare(Vaccination, Vaccination.vaccination_date, is_date=True)
    today = local_today(display_offset())
    due = medical_service.due_vaccinations(within_days=14)
    overdue = len([item for item in due if item.next_due_date < today])
    trend = _trend(
        w.series(MedicalRecord.examination_date, is_date=True), w.series(Vaccination.vaccination_date, is_date=True),
        "Examinations", "Vaccinations")
    return {
        "examinations": exams, "examinations_delta": exams_delta, "vaccinations": shots, "vaccinations_delta": shots_delta,
        "overdue": overdue, "due_soon": len(due) - overdue,
        "unvaccinated": Animal.query.filter(Animal.vaccination_status == C.VACC_NONE,
                                            Animal.status != C.ANIMAL_ADOPTED).count(),
        "trend_chart": trend,
        "vaccine_bars": top_bars(w.group(Vaccination.vaccine_name, Vaccination.vaccination_date, is_date=True)),
    }


def _volunteers(w):
    done = VolunteerTaskAssignment.status == C.TA_COMPLETED
    finished = w.clauses(VolunteerTaskAssignment.completed_at)
    created, created_delta = w.compare(VolunteerTask, VolunteerTask.created_at)
    completed, completed_delta = w.compare(
        VolunteerTask, VolunteerTask.completed_at, conditions=(VolunteerTask.status == C.TASK_COMPLETED,))
    applications, applications_delta = w.compare(VolunteerProfile, VolunteerProfile.applied_at)
    hours = db.session.query(db.func.coalesce(db.func.sum(VolunteerTaskAssignment.hours_spent), 0)).filter(
        done, *finished).scalar()
    active = db.session.query(db.func.count(db.distinct(VolunteerTaskAssignment.volunteer_id))).filter(
        done, *finished).scalar() or 0

    hours_sum = db.func.coalesce(db.func.sum(VolunteerTaskAssignment.hours_spent), 0)
    jobs = db.func.count(VolunteerTaskAssignment.id)
    top = (
        db.session.query(User.id, User.full_name, jobs, hours_sum)
        .select_from(VolunteerTaskAssignment)
        .join(User, User.id == VolunteerTaskAssignment.volunteer_id)
        .filter(done, *finished)
        .group_by(User.id, User.full_name)
        .order_by(hours_sum.desc(), jobs.desc(), User.full_name)
        .limit(5)
        .all()
    )
    by_type = dict(
        db.session.query(VolunteerTask.task_type, db.func.count(VolunteerTaskAssignment.id))
        .select_from(VolunteerTaskAssignment)
        .join(VolunteerTask, VolunteerTask.id == VolunteerTaskAssignment.task_id)
        .filter(done, *finished)
        .group_by(VolunteerTask.task_type)
        .all()
    )
    hours_series = w.series(VolunteerTaskAssignment.completed_at, conditions=(done,),
                            value=VolunteerTaskAssignment.hours_spent)
    return {
        "created": created, "created_delta": created_delta, "completed": completed, "completed_delta": completed_delta,
        "hours": round(float(hours or 0), 1), "active": active,
        "applications": applications, "applications_delta": applications_delta,
        "approved_now": stats.approved_volunteer_count(),
        "trend_chart": _trend(w.series(VolunteerTask.created_at),
                              w.series(VolunteerTask.completed_at, conditions=(VolunteerTask.status == C.TASK_COMPLETED,)),
                              "Tasks created", "Tasks completed"),
        "hours_chart": {"type": "line", "labels": hours_series["labels"], "legend": False, "integer": False,
                        "datasets": [{"label": "Volunteer hours", "data": hours_series["values"], "color": TEAL}]},
        "type_bars": top_bars(by_type),
        "top": [{"name": name, "tasks": count, "hours": round(float(total or 0), 1)} for _id, name, count, total in top],
    }


def _shelters(w):
    housed = animal_service.occupancy_counts()
    admissions = w.group(ShelterAdmission.shelter_id, ShelterAdmission.admitted_at)
    adoptions = w.group(AdoptionRecord.shelter_id, AdoptionRecord.adoption_date, is_date=True)
    rows = []
    for shelter in animal_service.verified_shelters():
        count = housed.get(shelter.id, 0)
        rows.append({
            "shelter": shelter, "housed": count, "percent": rules.occupancy_percent(shelter.capacity, count),
            "admissions": admissions.get(shelter.id, 0), "adoptions": adoptions.get(shelter.id, 0),
        })
    capacity = sum(row["shelter"].capacity for row in rows)
    total_housed = sum(row["housed"] for row in rows)
    return {
        "rows": rows, "capacity": capacity, "housed": total_housed,
        "occupancy_percent": rules.occupancy_percent(capacity, total_housed) if capacity else 0,
        "admissions": w.count(ShelterAdmission, ShelterAdmission.admitted_at),
        "overrides": w.count(ShelterAdmission, ShelterAdmission.admitted_at,
                             conditions=(ShelterAdmission.capacity_override.is_(True),)),
    }


def _people(w):
    new, delta = w.compare(User, User.created_at)
    new_by_role = w.group(User.role, User.created_at)
    totals = stats.group_counts(User.role)
    rows = [{"label": C.ROLE_LABELS[role], "icon": C.ROLE_ICONS[role], "new": new_by_role.get(role, 0),
             "total": totals.get(role, 0)} for role in C.ALL_ROLES]
    return {
        "new": new, "delta": delta, "total": sum(totals.values()), "rows": rows,
        "pending_verification": User.query.filter(User.verification_status == C.VERIFY_PENDING).count(),
        "trend_chart": _trend(w.series(User.created_at), None, "New accounts", None),
        "role_chart": {"type": "bar", "labels": [row["label"] for row in rows], "legend": False,
                       "datasets": [{"label": "New accounts", "data": [row["new"] for row in rows], "color": VIOLET}]},
    }


# ------------------------------------------------------------------- entry
def analytics(start, end):
    """Everything the analytics page shows for the local dates ``start`` .. ``end`` (inclusive)."""
    w = Window(start, end)
    rescue, animals, adoption = _rescue(w), _animals(w), _adoption(w)
    medical, volunteers, shelters, people = _medical(w), _volunteers(w), _shelters(w), _people(w)
    headline = [
        {"label": "Rescue reports", "value": rescue["received"], "icon": "bi-life-preserver", "tone": "coral",
         "delta": rescue["delta"], "delta_good": "up", "hint": f"{rescue['resolved_percent']}% rescued or closed"},
        {"label": "Animals registered", "value": animals["registered"], "icon": "bi-heart-pulse", "tone": "teal",
         "delta": animals["delta"], "delta_good": "up", "hint": f"{animals['in_care']} in care right now"},
        {"label": "Adoptions completed", "value": adoption["completed"], "icon": "bi-balloon-heart", "tone": "green",
         "delta": adoption["completed_delta"], "delta_good": "up", "hint": f"{adoption['received']} applications received"},
        {"label": "Volunteer hours", "value": volunteers["hours"], "icon": "bi-clock-history", "tone": "blue",
         "delta": None, "delta_good": "up", "hint": f"{volunteers['completed']} tasks completed"},
        {"label": "New accounts", "value": people["new"], "icon": "bi-person-plus", "tone": "amber",
         "delta": people["delta"], "delta_good": "up", "hint": f"{people['total']} accounts in total"},
    ]
    return {
        "start": start, "end": end, "days": w.days, "mode": w.mode,
        "label": f"{start:%d %b %Y} - {end:%d %b %Y}",
        "compared": f"{w.prev_start:%d %b %Y} - {w.prev_end:%d %b %Y}" if w.can_compare else None,
        "headline": headline, "rescue": rescue, "animals": animals, "adoption": adoption, "medical": medical,
        "volunteers": volunteers, "shelters": shelters, "people": people,
    }
