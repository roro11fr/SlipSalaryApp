from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .constants import PERIOD_FIRST_DAY
from .models import User, Contract, PayrollPeriod, AuditFile
from .serializers import (
    UserSerializer,
    ContractSerializer,
    PayrollPeriodSerializer,
    AuditFileSerializer,
)
from .permissions import IsManager
from .services import (
    get_manager_payroll_qs,
    populate_paid_salary_for_manager_period,
)
from .exporters import export_manager_csv
from .pdfs import generate_employee_pdf

class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsManager]

    def get_queryset(self):
        return User.objects.filter(manager=self.request.user) | User.objects.filter(id=self.request.user.id)

class ContractViewSet(viewsets.ModelViewSet):
    serializer_class = ContractSerializer
    permission_classes = [IsManager]

    def get_queryset(self):
        return Contract.objects.select_related("user").filter(user__manager=self.request.user)

class PayrollPeriodViewSet(viewsets.ModelViewSet):
    serializer_class = PayrollPeriodSerializer
    permission_classes = [IsManager]

    def get_queryset(self):
        period_str = self.request.query_params.get("period")
        if not period_str:
            return PayrollPeriod.objects.none()
        p = parse_date(period_str)
        if not p or p.day != PERIOD_FIRST_DAY:
            return PayrollPeriod.objects.none()
        return get_manager_payroll_qs(self.request.user, p)

    @action(detail=False, methods=["post"], url_path="compute")
    def compute(self, request):
        period_str = request.data.get("period")
        if not period_str:
            return Response({"detail": "Missing 'period'."}, status=status.HTTP_400_BAD_REQUEST)
        p = parse_date(period_str)
        if not p or p.day != PERIOD_FIRST_DAY:
            return Response({"detail": "Use YYYY-MM-01."}, status=status.HTTP_400_BAD_REQUEST)
        result = populate_paid_salary_for_manager_period(request.user, p)
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="export-csv")
    def export_csv(self, request):
        period_str = request.data.get("period")
        if not period_str:
            return Response({"detail": "Missing 'period'."}, status=status.HTTP_400_BAD_REQUEST)
        p = parse_date(period_str)
        if not p or p.day != PERIOD_FIRST_DAY:
            return Response({"detail": "Use YYYY-MM-01."}, status=status.HTTP_400_BAD_REQUEST)
        result = export_manager_csv(request.user, p)
        return Response(result, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="export-pdfs")
    def export_pdfs(self, request):
        period_str = request.data.get("period")
        if not period_str:
            return Response({"detail": "Missing 'period'."}, status=status.HTTP_400_BAD_REQUEST)
        p = parse_date(period_str)
        if not p or p.day != PERIOD_FIRST_DAY:
            return Response({"detail": "Use YYYY-MM-01."}, status=status.HTTP_400_BAD_REQUEST)
        qs = self.get_queryset()
        generated = []
        for rec in qs:
            payload = generate_employee_pdf(rec.user, p, rec.paid_salary)
            generated.append({"employee": rec.user.get_full_name(), **payload})
        return Response({"period": str(p), "generated": generated}, status=status.HTTP_201_CREATED)

class AuditFileViewSet(viewsets.ModelViewSet):
    serializer_class = AuditFileSerializer
    permission_classes = [IsManager]

    def get_queryset(self):
        return AuditFile.objects.filter(manager=self.request.user) | AuditFile.objects.filter(employee__manager=self.request.user)
