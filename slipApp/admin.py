from django.contrib import admin
from .models import User, Contract, PayrollPeriod, AuditFile

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "first_name", "last_name", "email", "role", "manager", "active")
    list_filter = ("role", "active")
    search_fields = ("username", "first_name", "last_name", "email", "cnp")

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("user", "start_date", "end_date", "base_salary", "currency")
    list_filter = ("currency",)
    search_fields = ("user__username",)

@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ("user", "period", "working_days", "vacation_days_taken", "bonus_total", "paid_salary")
    list_filter = ("period",)
    search_fields = ("user__username",)

@admin.register(AuditFile)
class AuditFileAdmin(admin.ModelAdmin):
    list_display = ("file_type", "file_name", "status", "manager", "employee", "period", "created_at", "sent_at")
    list_filter = ("file_type", "status", "period")
    search_fields = ("file_name", "manager__username", "employee__username")
