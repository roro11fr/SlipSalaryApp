from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from django.utils.timezone import now
from .constants import (
    PDF_FILENAME_PREFIX,
    PDF_LABEL_TITLE,
    PDF_LABEL_NAME,
    PDF_LABEL_EMP_ID,
    PDF_LABEL_CNP,
    PDF_LABEL_PERIOD,
    PDF_LABEL_SALARY,
    PDF_START_X,
    PDF_START_Y,
    PDF_LEADING,
    HASH_ALGO,
)
from .services import get_export_dir_for, record_audit
import hashlib

def _checksum(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def _protect_pdf_if_possible(src_path: Path, password: str) -> Path:
    try:
        import pikepdf
        dst_path = src_path.with_name(src_path.stem + "_protected.pdf")
        with pikepdf.open(str(src_path)) as pdf:
            pdf.save(str(dst_path), encryption=pikepdf.Encryption(user=password, owner=password))
        src_path.unlink(missing_ok=True)
        return dst_path
    except Exception:
        return src_path

def generate_employee_pdf(employee, period_start, salary_to_pay):
    out_dir = get_export_dir_for("PDF")
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{PDF_FILENAME_PREFIX}{employee.username}_{period_start}.pdf"
    fpath = out_dir / filename
    c = canvas.Canvas(str(fpath), pagesize=A4)
    t = c.beginText(PDF_START_X, PDF_START_Y)
    t.setLeading(PDF_LEADING)
    t.textLine(PDF_LABEL_TITLE)
    t.textLine(f"{PDF_LABEL_NAME}: {employee.first_name} {employee.last_name}")
    t.textLine(f"{PDF_LABEL_EMP_ID}: {employee.id}")
    t.textLine(f"{PDF_LABEL_CNP}: {employee.cnp}")
    t.textLine(f"{PDF_LABEL_PERIOD}: {period_start}")
    t.textLine(f"{PDF_LABEL_SALARY}: {salary_to_pay}")
    c.drawText(t)
    c.showPage()
    c.save()
    protected_path = _protect_pdf_if_possible(fpath, employee.cnp)
    checksum = _checksum(protected_path, HASH_ALGO)
    audit = record_audit(
        file_type="PDF",
        file_path=str(protected_path),
        file_name=protected_path.name,
        period=period_start,
        employee=employee,
        status="CREATED",
        checksum=checksum,
        sent_by=employee.manager if employee.manager else None,
    )
    return {"path": str(protected_path), "checksum": checksum, "audit_id": audit.id, "created_at": now().isoformat()}
