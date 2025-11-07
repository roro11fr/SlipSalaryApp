# exporters.py
import os, csv, hashlib
from pathlib import Path
from django.utils.timezone import now
from .constants import CSV_FILENAME_PREFIX, CSV_HEADER, ENCODING_UTF8, HASH_ALGO
from .services import get_export_dir_for, get_manager_payroll_qs, record_audit

def _compute_checksum(path: Path) -> str:
    h = hashlib.new(HASH_ALGO)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def export_manager_csv(manager, period_start) -> dict:
    out_dir = get_export_dir_for("CSV")

    qs = get_manager_payroll_qs(manager, period_start)
    count = qs.count()

    if count == 0:
        return {
            "file_path": None,
            "file_name": None,
            "checksum": None,
            "count": 0,
            "audit_id": None,
            "created_at": now().isoformat(),
        }

    filename = f"{CSV_FILENAME_PREFIX}{manager.username}_{period_start}.csv"
    fpath = out_dir / filename
    tmp_path = fpath.with_suffix(".tmp")

    with open(tmp_path, "w", newline="", encoding=ENCODING_UTF8) as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for p in qs:
            w.writerow([
                f"{p.user.first_name} {p.user.last_name}",
                str(p.paid_salary),
                p.working_days,
                p.vacation_days_taken,
                str(p.bonus_total),
            ])

    os.replace(tmp_path, fpath)

    checksum = _compute_checksum(fpath)
    audit = record_audit(
        file_type="CSV",
        file_path=str(fpath),
        file_name=filename,
        period=period_start,
        manager=manager,
        status="CREATED",
        checksum=checksum,
        sent_by=manager,
    )
    return {
        "file_path": str(fpath),
        "file_name": filename,
        "checksum": checksum,
        "count": count,
        "audit_id": audit.id,
        "created_at": now().isoformat(),
    }
