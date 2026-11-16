"""Volunteer tasks and the volunteers assigned to them."""
from app import constants as C
from app.extensions import db
from app.services import rules
from app.utils.timeutil import utcnow


class VolunteerTask(db.Model):
    __tablename__ = "volunteer_tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    task_type = db.Column(db.String(60), nullable=False, index=True)
    location_name = db.Column(db.String(150), nullable=True)
    address = db.Column(db.Text, nullable=True)
    latitude = db.Column(db.Float(53), nullable=True)
    longitude = db.Column(db.Float(53), nullable=True)
    instructions = db.Column(db.Text, nullable=True)
    due_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Available", index=True)
    volunteers_needed = db.Column(db.Integer, nullable=False, default=1)
    report_id = db.Column(db.Integer, db.ForeignKey("animal_reports.id", ondelete="SET NULL"), nullable=True, index=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("animals.id", ondelete="SET NULL"), nullable=True)
    shelter_id = db.Column(db.Integer, db.ForeignKey("shelter_profiles.id", ondelete="SET NULL"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cancel_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    report = db.relationship("AnimalReport", backref=db.backref("tasks"))
    animal = db.relationship("Animal", backref=db.backref("tasks"))
    shelter = db.relationship("ShelterProfile", backref=db.backref("tasks"))
    creator = db.relationship("User", foreign_keys=[created_by], backref=db.backref("created_tasks"))

    # ------------------------------------------------------------- helpers
    @property
    def active_assignments(self):
        return [a for a in self.assignments if a.status not in C.INACTIVE_TASK_ASSIGNMENT_STATUSES]

    @property
    def open_slots(self):
        return rules.task_open_slots(self.volunteers_needed, [a.status for a in self.assignments])

    @property
    def is_overdue(self):
        return bool(self.due_at and self.status not in (C.TASK_COMPLETED, C.TASK_CANCELLED) and self.due_at < utcnow())

    @property
    def progress_percent(self):
        active = self.active_assignments
        if not active:
            return 0
        return round(sum(a.progress_percent or 0 for a in active) / max(len(active), self.volunteers_needed))

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    def __repr__(self):
        return f"<VolunteerTask {self.id} {self.title!r} {self.status}>"


class VolunteerTaskAssignment(db.Model):
    __tablename__ = "volunteer_task_assignments"
    __table_args__ = (db.UniqueConstraint("task_id", "volunteer_id", name="uq_task_volunteer"),)

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("volunteer_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    volunteer_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # NULL = volunteer claimed it
    status = db.Column(db.String(20), nullable=False, default="Assigned", index=True)
    progress_percent = db.Column(db.Integer, nullable=False, default=0)
    progress_note = db.Column(db.Text, nullable=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    hours_spent = db.Column(db.Float, nullable=True)
    completion_notes = db.Column(db.Text, nullable=True)

    task = db.relationship("VolunteerTask", backref=db.backref("assignments", order_by="VolunteerTaskAssignment.id", cascade="all, delete-orphan"))
    volunteer = db.relationship("User", foreign_keys=[volunteer_id], backref=db.backref("task_assignments"))
    assigner = db.relationship("User", foreign_keys=[assigned_by])

    @property
    def is_active(self):
        return self.status not in C.INACTIVE_TASK_ASSIGNMENT_STATUSES
