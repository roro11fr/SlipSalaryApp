from __future__ import annotations
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, RegexValidator


class User(AbstractUser):
    class Role(models.TextChoices):
        MANAGER = "MANAGER", "Manager"
        EMPLOYEE = "EMPLOYEE", "Employee"

    email = models.EmailField(unique=True)

    cnp = models.CharField(
        max_length=13,
        unique=True,
        validators=[RegexValidator(r"^\d{13}$", "CNP must have exactly 13 digits")],
        help_text="Personal identification number (13 digits).",
    )

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.EMPLOYEE)

    manager = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reports",
        help_text="Direct manager for this user (nullable for managers).",
    )

    active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["manager"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(role__in=["MANAGER", "EMPLOYEE"]), name="user_role_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} ({self.username})"


class Contract(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="contracts")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text="Null = open-ended")
    base_salary = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default="RON")
    vacation_days_per_year = models.PositiveIntegerField(default=20)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user", "-start_date"]
        indexes = [
            models.Index(fields=["user", "start_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(models.Q(end_date__isnull=True) | models.Q(end_date__gte=models.F("start_date"))),
                name="contract_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"Contract#{self.id} for {self.user_id} ({self.start_date} → {self.end_date or 'open'})"


class PayrollPeriod(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payroll_periods")
    period = models.DateField(help_text="Anchor date = first day of the month")
    working_days = models.PositiveIntegerField(default=0)
    vacation_days_taken = models.PositiveIntegerField(default=0)
    bonus_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    paid_salary = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], help_text="Net or gross as per your business rules")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period", "user"]
        constraints = [
            models.UniqueConstraint(fields=["user", "period"], name="uniq_user_period"),
        ]
        indexes = [
            models.Index(fields=["period"]),
        ]

    def __str__(self) -> str:
        return f"Payroll {self.user_id} @ {self.period}"


class AuditFile(models.Model):
    class FileType(models.TextChoices):
        CSV = "CSV", "CSV"
        PDF = "PDF", "PDF"

    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    file_type = models.CharField(max_length=4, choices=FileType.choices)
    employee = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_employee_files")
    manager = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_manager_files")
    period = models.DateField(null=True, blank=True)
    file_name = models.CharField(max_length=512)
    file_path = models.CharField(max_length=1024, help_text="Absolute or storage path")
    checksum = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.CREATED)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="sent_files")
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["manager", "period"]),
            models.Index(fields=["employee", "period"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(file_type__in=["CSV", "PDF"]), name="audit_filetype_valid"),
            models.CheckConstraint(check=models.Q(status__in=["CREATED", "SENT", "FAILED"]), name="audit_status_valid"),
        ]

    def __str__(self) -> str:
        subject = self.employee_id or self.manager_id or "n/a"
        return f"{self.file_type} {self.file_name} (subj={subject})"
