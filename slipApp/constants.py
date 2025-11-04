from decimal import Decimal

CURRENCY_DEFAULT = "RON"
HASH_ALGO = "sha256"
ENCODING_UTF8 = "utf-8"

CSV_SUBDIR = "csv"
PDF_SUBDIR = "pdf"
CSV_FILENAME_PREFIX = "salary_"
PDF_FILENAME_PREFIX = "slip_"
CSV_HEADER = ["Employee", "SalaryToPay", "WorkingDays", "VacationDays", "Bonuses"]

DECIMAL_QUANT = Decimal("0.01")

PERIOD_FIRST_DAY = 1
PDF_LEADING = 16
PDF_START_X = 50
PDF_START_Y = 800

PDF_LABEL_TITLE = "Payslip"
PDF_LABEL_NAME = "Name"
PDF_LABEL_EMP_ID = "Employee ID"
PDF_LABEL_CNP = "CNP"
PDF_LABEL_PERIOD = "Period"
PDF_LABEL_SALARY = "Salary to pay"
PDF_LABEL_WORKING_DAYS = "Working days"
PDF_LABEL_VACATION_DAYS = "Vacation days taken"