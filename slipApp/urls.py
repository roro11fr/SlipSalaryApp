from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, ContractViewSet, PayrollPeriodViewSet, AuditFileViewSet

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="users")
router.register(r"contracts", ContractViewSet, basename="contracts")
router.register(r"payroll", PayrollPeriodViewSet, basename="payroll")
router.register(r"audit-files", AuditFileViewSet, basename="audit-files")

urlpatterns = [
    path("", include(router.urls)),
]
