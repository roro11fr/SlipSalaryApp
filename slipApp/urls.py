from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, ContractViewSet, PayrollPeriodViewSet, AuditFileViewSet
from .views_aggregate import (
    CreateAggregatedEmployeeDataView,
    SendAggregatedEmployeeDataView,
    CreatePdfForEmployeesView,
    SendPdfToEmployeesView,
)

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="users")
router.register(r"contracts", ContractViewSet, basename="contracts")
router.register(r"payroll", PayrollPeriodViewSet, basename="payroll")
router.register(r"audit-files", AuditFileViewSet, basename="audit-files")

urlpatterns = [
    path("", include(router.urls)),
    path("createAggregatedEmployeeData", CreateAggregatedEmployeeDataView.as_view()),
    path("sendAggregatedEmployeeData", SendAggregatedEmployeeDataView.as_view()),
    path("createPdfForEmployees", CreatePdfForEmployeesView.as_view()),
    path("sendPdfToEmployees", SendPdfToEmployeesView.as_view()),
]
