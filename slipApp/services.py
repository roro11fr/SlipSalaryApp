from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional, Dict

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


class _InlineInputs:
    def __init__(self, working_days=0, vacation_days_taken=0, bonus_total=0):
        self.working_days = int(working_days or 0)
        self.vacation_days_taken = int(vacation_days_taken or 0)
        self.bonus_total = Decimal(str(bonus_total or 0))


@transaction.atomic
def populate_paid_salary_for_manager_period(
    manager: User,
    period_start: date,
    inline_inputs: Optional[Dict[int, "_InlineInputs"]] = None,
) -> dict:
    inline_inputs = inline_inputs or {}

    subordinates = (
        User.objects.filter(manager=manager, active=True)
        .order_by("id")
        .only("id", "first_name", "last_name", "username")
    )

    created = 0
    updated = 0
    skipped_no_contract = 0
    processed = 0
    results: list[dict] = []

    for user in subordinates:
        p = (
            PayrollPeriod.objects
            .filter(user=user, period=period_start)
            .select_related("user")
            .first()
        )

        if p:
            inputs = _InlineInputs(
                working_days=p.working_days,
                vacation_days_taken=p.vacation_days_taken,
                bonus_total=p.bonus_total,
            )
            if user.id in inline_inputs:
                inl = inline_inputs[user.id]
                inputs.working_days = inl.working_days
                inputs.vacation_days_taken = inl.vacation_days_taken
                inputs.bonus_total = inl.bonus_total
        else:
            if user.id not in inline_inputs:
                continue
            inl = inline_inputs[user.id]
            inputs = _InlineInputs(
                working_days=inl.working_days,
                vacation_days_taken=inl.vacation_days_taken,
                bonus_total=inl.bonus_total,
            )

        computed = compute_salary_for_month(user, period_start, inputs)
        if computed is None:
            skipped_no_contract += 1
            results.append({"user_id": user.id, "status": "no_active_contract"})
            processed += 1
            continue

        if computed == _q2(0):
            results.append({"user_id": user.id, "status": "zero_amount"})
            processed += 1
            continue

        if p is None:
            p = PayrollPeriod(
                user=user,
                period=period_start,
                working_days=inputs.working_days,
                vacation_days_taken=inputs.vacation_days_taken,
                bonus_total=inputs.bonus_total,
                paid_salary=computed,
            )
            p.full_clean()
            p.save()
            created += 1
            results.append({
                "user_id": user.id,
                "status": "created",
                "paid_salary": str(computed)
            })
        else:
            changed_fields = []
            if p.working_days != inputs.working_days:
                p.working_days = inputs.working_days
                changed_fields.append("working_days")
            if p.vacation_days_taken != inputs.vacation_days_taken:
                p.vacation_days_taken = inputs.vacation_days_taken
                changed_fields.append("vacation_days_taken")
            if Decimal(p.bonus_total) != inputs.bonus_total:
                p.bonus_total = inputs.bonus_total
                changed_fields.append("bonus_total")

            if p.paid_salary != computed:
                p.paid_salary = computed
                changed_fields.append("paid_salary")

            if changed_fields:
                p.full_clean()
                p.save(update_fields=changed_fields + ["updated_at"])
                updated += 1
                results.append({
                    "user_id": user.id,
                    "status": "updated",
                    "paid_salary": str(computed)
                })
            else:
                results.append({
                    "user_id": user.id,
                    "status": "ok",
                    "paid_salary": str(computed)
                })

        processed += 1

    count_db = PayrollPeriod.objects.filter(user__manager=manager, user__active=True, period=period_start).count()

    return {
        "period": str(period_start),
        "manager_id": manager.id,
        "created": created,
        "updated": updated,
        "processed": processed,
        "skipped_no_contract": skipped_no_contract,
        "count": count_db,
        "results": results,
    }


def get_export_dir_for(kind: str) -> Path:
    base = Path(getattr(settings, "MEDIA_ROOT", "media")) / "exports" / kind.upper()
    base.mkdir(parents=True, exist_ok=True)
    return base

def get_manager_payroll_qs(manager: User, period_start: date):
    return (
        PayrollPeriod.objects
        .select_related("user")
        .filter(user__manager=manager, user__active=True, period=period_start)
        .order_by("user__last_name", "user__first_name")
    )
