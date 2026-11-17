import uuid

from django.db import models
from apps.core.models import BaseModel
from apps.properties.models import Property
from apps.reservations.models import Reservation


def receipt_upload_to(instance, filename):
    """Medya nginx'te kimlik doğrulamasız servis edilir: yol tahmin edilemez olsun."""
    return f"receipts/{uuid.uuid4().hex}/{filename}"


class FinancialTransaction(BaseModel):

    class TransactionType(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    class Category(models.TextChoices):
        # Gelir
        RESERVATION = "reservation", "Reservation income"
        OTHER_INCOME = "other_income", "Other income"
        # Masraf
        CLEANING = "cleaning", "Cleaning"
        MAINTENANCE = "maintenance", "Maintenance / repair"
        ELECTRICITY = "electricity", "Electricity"
        WATER = "water", "Water"
        INTERNET = "internet", "Internet"
        GAS = "gas", "Natural gas"
        DUES = "dues", "Building dues"
        SUPPLIES = "supplies", "Supplies"
        TAX = "tax", "Tax"
        OTHER = "other", "Other"

    INCOME_CATEGORIES = (Category.RESERVATION, Category.OTHER_INCOME)

    property = models.ForeignKey(
        Property,
        on_delete=models.PROTECT,
        related_name="financial_transactions"
    )
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_transactions"
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=TransactionType.choices
    )
    # Eski kayıtlar serbest metin olabileceği için DB'de kısıt yok; API choices ile doğrular.
    category = models.CharField(max_length=100, choices=Category.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="TRY")
    description = models.TextField(blank=True)
    transaction_date = models.DateField()
    receipt = models.FileField(upload_to=receipt_upload_to, null=True, blank=True, max_length=255)

    # Otomatik oluşturulan kayıtların kaynağı (idempotent güncelleme için).
    housekeeping_task = models.OneToOneField(
        "operations.HouseKeepingTasks", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="expense",
    )
    general_task = models.OneToOneField(
        "operations.GeneralTask", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="expense",
    )
    recurring_expense = models.ForeignKey(
        "finance.RecurringExpense", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transactions",
    )

    class Meta:
        constraints = [
            # Rezervasyon başına tek otomatik gelir kaydı.
            models.UniqueConstraint(
                fields=["reservation"],
                condition=models.Q(category="reservation"),
                name="unique_reservation_income",
            ),
            # Tekrarlayan masraf başına ayda tek kayıt (tarih = üretildiği gün).
            models.UniqueConstraint(
                fields=["recurring_expense", "transaction_date"],
                name="unique_recurring_expense_date",
            ),
        ]

    def __str__(self):
        return f"{self.transaction_type} - {self.amount}"


class RecurringExpense(BaseModel):
    """Aylık tekrarlayan masraf (aidat, internet ...). Beat her gün kontrol eder, ayda bir kayıt üretir."""

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="recurring_expenses")
    category = models.CharField(max_length=100, choices=FinancialTransaction.Category.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="TRY")
    description = models.TextField(blank=True)
    day_of_month = models.PositiveSmallIntegerField(default=1)  # 1-28
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["property__name", "day_of_month"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(day_of_month__gte=1, day_of_month__lte=28),
                name="recurring_expense_day_1_28",
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="recurring_expense_amount_positive"),
        ]

    def __str__(self):
        return f"{self.property.name} - {self.category} {self.amount}/month"
