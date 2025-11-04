from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from .constants import DECIMAL_QUANT, CSV_SUBDIR, PDF_SUBDIR
from .models import User, Contract, PayrollPeriod, AuditFile


def _q2(x: Decimal | int | float | str) -> Decimal:
    return Decimal(x).quantize(DECIMAL_QUANT, rounding=ROUND_HALF_UP)


def get_active_contract(user: User, on_date: date) -> Optional[Contract]:
    return (
        Contract.objects
        .filter(user=user, start_date__lte=on_date)
        .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=on_date))
        .order_by("-start_date")
        .first()
    )


@dataclass(frozen=True)
class SalaryInputs:
    working_days: int
    vacation_days_taken: int
    bonus_total: Decimal


def compute_salary_for_month(user: User, period_start: date, inputs: SalaryInputs) -> Optional[Decimal]:
    if inputs.working_days < 0 or inputs.vacation_days_taken < 0:
        raise ValidationError("Days cannot be negative.")
    if inputs.working_days == 0 and inputs.vacation_days_taken == 0:
        return _q2(0)

    contract = get_active_contract(user, period_start)
    if not contract:
        return None

    total_days = inputs.working_days + inputs.vacation_days_taken
    daily_rate = Decimal(contract.base_salary) / Decimal(total_days)
    paid = daily_rate * Decimal(inputs.working_days) + Decimal(inputs.bonus_total)
    return _q2(paid)


def record_audit(
    *,
    file_type: str,
    file_path: str,
    file_name: str,
    period: Optional[date] = None,
    manager: Optional[User] = None,
    employee: Optional[User] = None,
    status: str = AuditFile.Status.CREATED,
    checksum: str = "",
    sent_by: Optional[User] = None,
) -> AuditFile:
    return AuditFile.objects.create(
        file_type=file_type,
        file_path=file_path,
        file_name=file_name,
        period=period,
        manager=manager,
        employee=employee,
        status=status,
        checksum=checksum,
        sent_by=sent_by,
    )


@transaction.atomic
def populate_paid_salary_for_manager_period(manager: User, period_start: date) -> dict:
    qs = (
        PayrollPeriod.objects
        .select_related("user")
        .filter(user__manager=manager, user__active=True, period=period_start)
        .order_by("user_id")
    )

    updated = 0
    skipped_no_contract = 0
    results: list[dict] = []

    for p in qs:
        inputs = SalaryInputs(
            working_days=p.working_days,
            vacation_days_taken=p.vacation_days_taken,
            bonus_total=p.bonus_total,
        )
        computed = compute_salary_for_month(p.user, period_start, inputs)
        if computed is None:
            skipped_no_contract += 1
            results.append({"user_id": p.user_id, "status": "no_active_contract"})
            continue

        if p.paid_salary != computed:
            p.paid_salary = computed
            p.full_clean()
            p.save(update_fields=["paid_salary", "updated_at"])
            updated += 1

        results.append({"user_id": p.user_id, "status": "ok", "paid_salary": str(computed)})

    return {
        "period": str(period_start),
        "manager_id": manager.id,
        "updated": updated,
        "skipped_no_contract": skipped_no_contract,
        "count": qs.count(),
        "results": results,
    }


def get_export_dir_for(kind: str) -> Path:
    base_dir = Path(getattr(settings, "EXPORT_DIR", getattr(settings, "MEDIA_ROOT")))
    return base_dir / (CSV_SUBDIR if kind == "CSV" else PDF_SUBDIR)


def get_manager_payroll_qs(manager: User, period_start: date):
    return (
        PayrollPeriod.objects
        .select_related("user")
        .filter(user__manager=manager, user__active=True, period=period_start)
        .order_by("user__last_name", "user__first_name")
    )
