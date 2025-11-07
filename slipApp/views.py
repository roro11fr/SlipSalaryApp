from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from dataclasses import dataclass
from .constants import PERIOD_FIRST_DAY
from .models import User, Contract, PayrollPeriod, AuditFile
from .serializers import (
    UserSerializer,
    ContractSerializer,
    PayrollPeriodSerializer,
    AuditFileSerializer,
)
from .permissions import IsManager
from rest_framework.permissions import IsAuthenticated
from .services import (
    get_manager_payroll_qs,
    populate_paid_salary_for_manager_period,
)
from .exporters import export_manager_csv
from .pdfs import generate_employee_pdf
from django.core.mail import EmailMessage
from .archive import archive_files
from django.utils.timezone import now
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from .idempotency import idempotent
from rest_framework.views import APIView
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken

class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    queryset = User.objects.all()

    def _is_admin_like(self, u: User) -> bool:
        return bool(getattr(u, "is_superuser", False) or getattr(u, "is_staff", False))

    @action(detail=False, methods=["get"], url_path="subordinates")
    def subordinates(self, request):
        u = request.user
        if not (u.role == User.Role.MANAGER or self._is_admin_like(u)):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        qs = User.objects.filter(manager=u, active=True)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=False, methods=["get"], url_path="all")
    def all_users(self, request):
        u = request.user
        if not self._is_admin_like(u):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        qs = User.objects.all()
        return Response(self.get_serializer(qs, many=True).data)

class ContractViewSet(viewsets.ModelViewSet):
    serializer_class = ContractSerializer
    permission_classes = [IsManager, IsAuthenticated]

    def get_queryset(self):
        return Contract.objects.select_related("user").filter(user__manager=self.request.user)


@dataclass
class SalaryInputsInline:
    working_days: int = 0
    vacation_days_taken: int = 0
    bonus_total: float = 0.0


class PayrollPeriodViewSet(viewsets.ModelViewSet):
    serializer_class = PayrollPeriodSerializer
    permission_classes = [IsManager, IsAuthenticated]

    def get_queryset(self):
        qs = PayrollPeriod.objects.select_related("user")
        if getattr(self, "action", None) == "list":
            period_str = self.request.query_params.get("period")
            if not period_str:
                return qs.none()
            p = parse_date(period_str)
            if not p or p.day != PERIOD_FIRST_DAY:
                return qs.none()
            return get_manager_payroll_qs(self.request.user, p)
        return qs

    # @idempotent
    @action(detail=False, methods=["post"], url_path="compute")
    def compute(self, request):
        period_str = request.data.get("period")
        if not period_str:
            return Response({"detail": "Missing 'period'."}, status=status.HTTP_400_BAD_REQUEST)
        p = parse_date(period_str)
        if not p or p.day != PERIOD_FIRST_DAY:
            return Response({"detail": "Use YYYY-MM-01."}, status=status.HTTP_400_BAD_REQUEST)

        inputs_list = request.data.get("inputs", [])
        if inputs_list is not None and not isinstance(inputs_list, list):
            return Response({"detail": "Field 'inputs' must be a list."}, status=status.HTTP_400_BAD_REQUEST)

        inline_inputs = {}
        for item in inputs_list or []:
            try:
                uid = int(item["user"])
                inline_inputs[uid] = SalaryInputsInline(
                    working_days=int(item.get("working_days", 0)),
                    vacation_days_taken=int(item.get("vacation_days_taken", 0)),
                    bonus_total=float(item.get("bonus_total", 0)),
                )
            except Exception as e:
                return Response({"detail": f"Invalid item in 'inputs': {item}. Error: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        result = populate_paid_salary_for_manager_period(request.user, p, inline_inputs=inline_inputs)
        return Response(result, status=status.HTTP_200_OK)
    
    # @idempotent
    @action(detail=False, methods=["post"], url_path="export-csv")
    def export_csv(self, request):
        period_str = request.data.get("period")
        if not period_str:
            return Response({"detail": "Missing 'period'."}, status=status.HTTP_400_BAD_REQUEST)
        p = parse_date(period_str)
        if not p or p.day != PERIOD_FIRST_DAY:
            return Response({"detail": "Use YYYY-MM-01."}, status=status.HTTP_400_BAD_REQUEST)

        result = export_manager_csv(request.user, p)
        
        if not result["count"]:
            return Response({"detail": "No data for period.", "count": 0}, status=status.HTTP_404_NOT_FOUND)

        subject = f"Payroll CSV – {p.strftime('%B %Y')}"
        body = "Attached is your payroll report CSV file."
        try:
            msg = EmailMessage(subject=subject, body=body, to=[request.user.email])
            msg.attach_file(result["file_path"])
            msg.send()
            result["email_status"] = "sent"
        except Exception as e:
            result["email_status"] = f"error: {e}"

        return Response(result, status=status.HTTP_201_CREATED)

    # @idempotent
    @action(detail=False, methods=["post"], url_path="export-pdfs")
    def export_pdfs(self, request):
        period_str = request.data.get("period")
        if not period_str:
            return Response({"detail": "Missing 'period'."}, status=status.HTTP_400_BAD_REQUEST)
        p = parse_date(period_str)
        if not p or p.day != PERIOD_FIRST_DAY:
            return Response({"detail": "Use YYYY-MM-01."}, status=status.HTTP_400_BAD_REQUEST)

        qs = get_manager_payroll_qs(request.user, p)

        generated, to_archive = [], []
        for rec in qs:
            payload = generate_employee_pdf(rec.user, p, rec.paid_salary)
            file_path = payload.get("file_path")
            audit_id = payload.get("audit_id")
            status_item = {"employee": rec.user.get_full_name(), "file_path": file_path, "audit_id": audit_id}

            if rec.user.email and file_path:
                subject = f"Payslip – {p.strftime('%B %Y')}"
                body = (
                    f"Hello {rec.user.get_full_name()},\n\n"
                    f"Attached is your payslip for {p.strftime('%B %Y')}.\n"
                    f"Password to open the PDF: your CNP.\n\n"
                    f"Best regards,\nPayroll"
                )
                try:
                    msg = EmailMessage(subject=subject, body=body, to=[rec.user.email])
                    msg.attach_file(file_path)
                    msg.send()
                    status_item["email_status"] = "sent"

                    if audit_id:
                        AuditFile.objects.filter(id=audit_id).update(
                            status=AuditFile.Status.SENT, sent_at=now()
                        )
                        to_archive.append(audit_id)
                except Exception as e:
                    status_item["email_status"] = f"error: {e}"
            else:
                status_item["email_status"] = "skipped (missing email or file)"

            generated.append(status_item)

        if to_archive:
            archive_files(to_archive)

        return Response({"period": str(p), "generated": generated}, status=status.HTTP_201_CREATED)


class AuditFileViewSet(viewsets.ModelViewSet):
    serializer_class = AuditFileSerializer
    permission_classes = [IsManager, IsAuthenticated]

    def get_queryset(self):
        qs = (AuditFile.objects.filter(manager=self.request.user)
            | AuditFile.objects.filter(employee__manager=self.request.user))

        t = self.request.query_params.get("type")
        if t:
            t = t.upper()
            if t in AuditFile.FileType.values:
                qs = qs.filter(file_type=t)

        period_str = self.request.query_params.get("period")
        if period_str:
            d = parse_date(period_str)
            if d and d.day == PERIOD_FIRST_DAY:
                qs = qs.filter(period=d)
            else:
                pass

        return qs.order_by("-created_at")



class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response({"detail": "Missing 'refresh' in body"}, status=400)

        try:
            u = UntypedToken(refresh)
            if u.payload.get("token_type") != "refresh":
                return Response({"detail": "Provided token is not a refresh token"}, status=400)
        except TokenError as e:
            return Response({"detail": f"Invalid JWT: {e}"}, status=400)

        try:
            RefreshToken(refresh).blacklist()
            return Response({"detail": "Logout successful"}, status=status.HTTP_205_RESET_CONTENT)
        except (InvalidToken, TokenError) as e:
            if "blacklisted" in str(e).lower():
                return Response({"detail": "Already logged out"}, status=status.HTTP_205_RESET_CONTENT)
            return Response({"detail": f"Cannot blacklist: {e}"}, status=400)