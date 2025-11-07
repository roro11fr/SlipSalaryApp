from pathlib import Path
from decimal import Decimal
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.pdfgen import canvas as pdfcanvas
from django.utils.timezone import now
from django.db import models
from django.conf import settings
from .constants import PDF_FILENAME_PREFIX, HASH_ALGO
from .services import get_export_dir_for, record_audit
from .models import PayrollPeriod, Contract
import hashlib, os

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

def _fmt_money(x) -> str:
    return f"{Decimal(x):.2f} RON" if x is not None else "-"

def _logo(path: str, w_mm=26):
    if path and os.path.exists(path):
        img = Image(path, width=w_mm*mm, height=(w_mm*mm*0.35))
        img.hAlign = "LEFT"
        return img
    return None

def _draw_page_decor(c: pdfcanvas.Canvas, doc):
    c.saveState()
    c.setFont("Helvetica-Bold", 60)
    c.setFillColorRGB(0.9, 0.9, 0.9)
    c.translate(A4[0] / 2, A4[1] / 2)
    c.rotate(45)
    c.drawCentredString(0, 0, "CONFIDENTIAL")
    c.restoreState()
    page = c.getPageNumber()
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.grey)
    c.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Page {page}")
    c.drawString(18 * mm, 12 * mm, f"Generated on {now().date().isoformat()} • This PDF is password-protected with your CNP.")

def generate_employee_pdf(employee, period_start, salary_to_pay, *, logo_path: str = None):
    p = (PayrollPeriod.objects
         .filter(user=employee, period=period_start)
         .values("working_days", "vacation_days_taken", "bonus_total")
         .first()) or {"working_days": 0, "vacation_days_taken": 0, "bonus_total": Decimal("0")}
    contract = (Contract.objects
                .filter(user=employee, start_date__lte=period_start)
                .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=period_start))
                .order_by("-start_date").first())
    base_salary = getattr(contract, "base_salary", None)
    total_days = (p["working_days"] or 0) + (p["vacation_days_taken"] or 0)
    daily_rate = (Decimal(base_salary) / Decimal(total_days)).quantize(Decimal("0.01")) if base_salary and total_days else None

    out_dir = get_export_dir_for("PDF")
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{PDF_FILENAME_PREFIX}{employee.username}_{period_start}.pdf"
    fpath = out_dir / filename

    doc = SimpleDocTemplate(
        str(fpath),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title=f"Salary Slip {employee.get_full_name()} - {period_start}",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="H1", fontSize=16, leading=20, spaceAfter=6))
    styles.add(ParagraphStyle(name="Sub", fontSize=10, textColor=colors.grey))
    styles.add(ParagraphStyle(name="Section", fontSize=12, spaceBefore=12, spaceAfter=6))
    story = []

    header_row = []
    lg = _logo(logo_path or getattr(settings, "PAYSLIP_LOGO_PATH", ""))
    if lg:
        header_row.append(lg)
    else:
        header_row.append(Paragraph("<b>SlipSalary Inc.</b>", styles["H1"]))
    header_row.append(Paragraph(f"<b>SALARY SLIP</b><br/><font size=10>{period_start:%m/%Y}</font>", styles["H1"]))
    header_tbl = Table([header_row], colWidths=[60 * mm, 110 * mm])
    header_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [header_tbl, Paragraph("CONFIDENTIAL", styles["Sub"]), Spacer(1, 6)]

    info = [
        ["Name:", f"{employee.get_full_name()} ({employee.username})",
        "Employee ID:", str(employee.id),
         "Manager:", employee.manager.get_full_name() if employee.manager else "-"],
        ["Period:", f"{period_start}", "", ""],
    ]
    info_tbl = Table(info, colWidths=[35 * mm, 70 * mm, 35 * mm, 30 * mm])
    info_tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [info_tbl, Spacer(1, 8)]

    story.append(Paragraph("<b>EARNINGS & WORK SUMMARY</b>", styles["Section"]))
    earn = [
        ["Description", "Value"],
        ["Base Salary (Contract)", _fmt_money(base_salary)],
        ["Bonus (Period)", _fmt_money(p["bonus_total"])],
        ["Daily Rate", f"{daily_rate:.2f} RON/day" if daily_rate else "-"],
        ["Working Days", str(p["working_days"])],
        ["Paid Vacation Days", str(p["vacation_days_taken"])],
        ["Total Days", str(total_days)],
        ["Salary Paid (Gross)", _fmt_money(salary_to_pay)],
    ]
    earn_tbl = Table(earn, colWidths=[100 * mm, 70 * mm])
    earn_tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("LINEABOVE", (0, 0), (-1, 0), 1, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.Color(0.98, 0.98, 0.98), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(earn_tbl)

    story.append(Spacer(1, 10))
    net_tbl = Table(
        [[Paragraph("<b>NET SALARY (RON)</b>", styles["Normal"]), Paragraph(f"<b>{Decimal(salary_to_pay):.2f}</b>", styles["Normal"])]],
        colWidths=[120 * mm, 48 * mm],
    )
    net_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.Color(0.85, 0.97, 0.85)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.Color(0.3, 0.7, 0.3)),
        ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 11),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(net_tbl)

    doc.build(story, onFirstPage=_draw_page_decor, onLaterPages=_draw_page_decor)

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
    return {
        "file_path": str(protected_path),
        "checksum": checksum,
        "audit_id": audit.id,
        "created_at": now().isoformat(),
    }
