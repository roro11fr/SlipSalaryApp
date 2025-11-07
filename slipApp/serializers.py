from rest_framework import serializers
from .models import User, Contract, PayrollPeriod, AuditFile

from rest_framework import serializers
from .models import User

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    manager_username = serializers.CharField(source="manager.username", read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False, trim_whitespace=False)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name", "full_name",
            "cnp", "role", "manager", "manager_username", "active", "password",
        )
        read_only_fields = ("id",)

    def create(self, validated_data):
        pwd = validated_data.pop("password", None)
        user = super().create(validated_data)
        if pwd:
            user.set_password(pwd)
        user.is_active = True
        user.save()
        return user

    def update(self, instance, validated_data):
        pwd = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if pwd:
            user.set_password(pwd)
            user.save()
        return user


class ContractSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Contract
        fields = (
            "id",
            "user",
            "user_username",
            "start_date",
            "end_date",
            "base_salary",
            "currency",
            "vacation_days_per_year",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

class PayrollPeriodSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="user.get_full_name", read_only=True)
    user_username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = PayrollPeriod
        fields = ("id","user","user_username","employee_name","period",
                  "working_days","vacation_days_taken","bonus_total",
                  "paid_salary","created_at","updated_at")
        read_only_fields = ("id","created_at","updated_at","employee_name","user_username","paid_salary")


class AuditFileSerializer(serializers.ModelSerializer):
    employee_username = serializers.CharField(source="employee.username", read_only=True)
    manager_username = serializers.CharField(source="manager.username", read_only=True)

    class Meta:
        model = AuditFile
        fields = (
            "id",
            "file_type",
            "employee",
            "employee_username",
            "manager",
            "manager_username",
            "period",
            "file_name",
            "file_path",
            "checksum",
            "status",
            "created_at",
            "sent_at",
            "archived_at",
            "sent_by",
        )
        read_only_fields = ("id", "created_at", "sent_at", "archived_at")
