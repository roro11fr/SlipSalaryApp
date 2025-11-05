from django.utils.dateparse import parse_date
from rest_framework import status, views
from rest_framework.response import Response
from .permissions import IsManager
from .constants import PERIOD_FIRST_DAY
from .excel_export import export_manager_xlsx
from .exporters import export_manager_csv
from .pdfs import generate_employee_pdf
from .services import get_manager_payroll_qs
from .mailer import send_with_attachment
from .archive import archive_files
from .models import AuditFile
from .idempotency import idempotent

class CreateAggregatedEmployeeDataView(views.APIView):
    permission_classes = [IsManager]

    @idempotent
    def post(self, request):
        period_str = request.data.get("period")
        p = parse_date(period_str) if period_str else None
        if not p or p.day != PERIOD_FIRST_DAY:
            return Response({"detail": "Use YYYY-MM-01."}, status=status.HTTP_400_BAD_REQUEST)
        result = export_manager_xlsx(request.user, p)
        return Response(result, status=status.HTTP_201_CREATED)

class SendAggregatedEmployeeDataView(views.APIView):
    permission_classes = [IsManager]

    @idempotent
    def post(self, request):
        period_str = request.data.get("period")
        p = parse_date(period_str) if period_str else None
        if not p or p.day != PERIOD_FIRST_DAY:
            return Response({"detail": "Use YYYY-MM-01."}, status=status.HTTP_400_BAD_REQUEST)
        latest = AuditFile.objects.filter(manager=request.user, period=p, file_type="CSV").order_by("-created_at").first()
        if not latest:
            return Response({"detail": "No file to send."}, status=status.HTTP_404_NOT_FOUND)
        send_with_attachment(request.user.email, f"Salaries {p}", "Attached.", [latest.file_path])
        latest.status = AuditFile.Status.SENT
        latest.sent_at = latest.created_at
        latest.save(update_fields=["status", "sent_at"])
        arch = archive_files([latest.id])
        return Response({"sent_id": latest.id, "archived": arch}, status=status.HTTP_200_OK)

class CreatePdfForEmployeesView(views.APIView):
    permission_classes = [IsManager]

    @idempotent
    def post(self, request):
        period_str = request.data.get("period")
        p = parse_date(period_str) if period_str else None
        if not p or p.day != PERIOD_FIRST_DAY:
            return Response({"detail": "Use YYYY-MM-01."}, status=status.HTTP_400_BAD_REQUEST)
        generated = []
        for rec in get_manager_payroll_qs(request.user, p):
            payload = generate_employee_pdf(rec.user, p, rec.paid_salary)
            generated.append({"employee": rec.user.get_full_name(), **payload})
        return Response({"period": str(p), "generated": generated}, status=status.HTTP_201_CREATED)

class SendPdfToEmployeesView(views.APIView):
    permission_classes = [IsManager]

    @idempotent
    def post(self, request):
        period_str = request.data.get("period")
        p = parse_date(period_str) if period_str else None
        if not p or p.day != PERIOD_FIRST_DAY:
            return Response({"detail": "Use YYYY-MM-01."}, status=status.HTTP_400_BAD_REQUEST)
        targets = AuditFile.objects.filter(employee__manager=request.user, period=p, file_type="PDF", status=AuditFile.Status.CREATED)
        if not targets.exists():
            return Response({"detail": "No PDFs to send."}, status=status.HTTP_404_NOT_FOUND)
        sent_ids = []
        for af in targets:
            to = af.employee.email
            send_with_attachment(to, f"Payslip {p}", "Attached payslip.", [af.file_path])
            af.status = AuditFile.Status.SENT
            af.sent_at = af.created_at
            af.save(update_fields=["status", "sent_at"])
            sent_ids.append(af.id)
        arch = archive_files(sent_ids)
        return Response({"sent_ids": sent_ids, "archived": arch}, status=status.HTTP_200_OK)
