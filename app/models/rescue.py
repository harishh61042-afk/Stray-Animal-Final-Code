"""Rescue reports, assignments and the activity timeline."""
from app import constants as C
from app.extensions import db
from app.utils.timeutil import utcnow


class AnimalReport(db.Model):
    __tablename__ = "animal_reports"

    id = db.Column(db.Integer, primary_key=True)
    report_code = db.Column(db.String(30), nullable=False, unique=True, index=True)  # e.g. RPT-2026-00042
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reporter_name = db.Column(db.String(100), nullable=False)
    reporter_phone = db.Column(db.String(20), nullable=False)
    reporter_email = db.Column(db.String(120), nullable=True)
    animal_type = db.Column(db.String(30), nullable=False, index=True)
    animal_description = db.Column(db.Text, nullable=False)
    approximate_age = db.Column(db.String(50), nullable=True)
    animal_condition = db.Column(db.String(60), nullable=False)
    emergency_level = db.Column(db.String(20), nullable=False, default="Medium", index=True)
    animal_count = db.Column(db.Integer, nullable=False, default=1)
    image_filename = db.Column(db.String(255), nullable=True)
    location_name = db.Column(db.String(150), nullable=False, index=True)
    address = db.Column(db.Text, nullable=False)
    latitude = db.Column(db.Float(53), nullable=True)
    longitude = db.Column(db.Float(53), nullable=True)
    additional_info = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Pending", index=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)

    reporter = db.relationship("User", foreign_keys=[reporter_id], backref=db.backref("reports"))

    @property
    def is_open(self):
        return self.status in C.OPEN_REPORT_STATUSES

    @property
    def active_assignment(self):
        """The assignment currently waiting on / working with a rescuer (or ``None``)."""
        for assignment in self.assignments:
            if assignment.status in C.ACTIVE_ASSIGNMENT_STATUSES:
                return assignment
        return None

    @property
    def latest_assignment(self):
        return self.assignments[-1] if self.assignments else None

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def emergency_tone(self):
        return C.EMERGENCY_TONES.get(self.emergency_level, "secondary")

    def __repr__(self):
        return f"<AnimalReport {self.report_code} {self.status}>"


class RescueAssignment(db.Model):
    """A rescuer assigned to a report. A report may be reassigned several times."""

    __tablename__ = "rescue_assignments"
    __table_args__ = (
        db.Index("ix_rescue_assignments_report_status", "report_id", "status"),
        db.Index("ix_rescue_assignments_rescuer_status", "rescuer_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("animal_reports.id", ondelete="CASCADE"), nullable=False)
    rescuer_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Assigned")
    deadline = db.Column(db.DateTime, nullable=True)
    instructions = db.Column(db.Text, nullable=True)
    response_note = db.Column(db.Text, nullable=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    completion_details = db.Column(db.Text, nullable=True)

    report = db.relationship("AnimalReport", backref=db.backref("assignments", order_by="RescueAssignment.id", cascade="all, delete-orphan"))
    rescuer = db.relationship("User", foreign_keys=[rescuer_id], backref=db.backref("rescue_assignments"))
    assigner = db.relationship("User", foreign_keys=[assigned_by])

    @property
    def is_active(self):
        return self.status in C.ACTIVE_ASSIGNMENT_STATUSES

    @property
    def is_overdue(self):
        return bool(self.deadline and self.is_active and self.deadline < utcnow())


class RescueActivity(db.Model):
    """One entry in a report's history (status change, note, assignment ...)."""

    __tablename__ = "rescue_activities"
    __table_args__ = (db.Index("ix_rescue_activities_report_created", "report_id", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("animal_reports.id", ondelete="CASCADE"), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    activity_type = db.Column(db.String(40), nullable=False)
    old_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    report = db.relationship("AnimalReport", backref=db.backref("activities", order_by="RescueActivity.id", cascade="all, delete-orphan"))
    actor = db.relationship("User", foreign_keys=[actor_id])
