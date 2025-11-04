from django.core.management.base import BaseCommand
from datetime import date
from decimal import Decimal
from slipApp.models import User, Contract, PayrollPeriod

class Command(BaseCommand):
    help = "Populate database with managers, employees, contracts, and payroll data."

    def handle(self, *args, **options):
        self.stdout.write("Clearing existing data...")
        PayrollPeriod.objects.all().delete()
        Contract.objects.all().delete()
        User.objects.exclude(is_superuser=True).delete()

        self.stdout.write("Creating managers...")
        m1 = User.objects.create_user(
            username="manager1",
            password="test1234",
            first_name="Andrei",
            last_name="Popescu",
            email="manager1@example.com",
            cnp="1234567890123",
            role="MANAGER",
        )
        m2 = User.objects.create_user(
            username="manager2",
            password="test1234",
            first_name="Ioana",
            last_name="Dumitru",
            email="manager2@example.com",
            cnp="2234567890123",
            role="MANAGER",
        )

        self.stdout.write("Creating employees...")
        employees = []
        for i in range(1, 6):
            manager = m1 if i <= 3 else m2
            e = User.objects.create_user(
                username=f"emp{i}",
                password="test1234",
                first_name=f"Employee{i}",
                last_name="Test",
                email=f"emp{i}@example.com",
                cnp=f"33345678901{i:02d}",
                role="EMPLOYEE",
                manager=manager,
            )
            employees.append(e)

        self.stdout.write("Creating contracts...")
        start_date = date(2025, 1, 1)
        for idx, e in enumerate(employees):
            base_salary = Decimal("5000.00") + (Decimal("500.00") * idx)
            Contract.objects.create(
                user=e,
                start_date=start_date,
                base_salary=base_salary,
                currency="RON",
                vacation_days_per_year=20,
            )

        self.stdout.write("Creating payroll periods...")
        period = date(2025, 11, 1)
        for idx, e in enumerate(employees):
            base_salary = Decimal("5000.00") + (Decimal("500.00") * idx)
            PayrollPeriod.objects.create(
                user=e,
                period=period,
                working_days=20,
                vacation_days_taken=2,
                bonus_total=Decimal("300.00"),
                paid_salary=base_salary + Decimal("300.00"),
            )

        self.stdout.write(self.style.SUCCESS("✅ Seed data created successfully."))
