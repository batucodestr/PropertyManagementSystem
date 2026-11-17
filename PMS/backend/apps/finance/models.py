from django.db import models
from apps.core.models import BaseModel
from apps.properties.models import Property
from apps.reservations.models import Reservation


def receipt_upload_to(instance, filename):
    """Sadece eski migration'lar (0004-0006) için; fiş yükleme kaldırıldı."""
    return f"receipts/{filename}"


class FinancialTransaction(BaseModel):
    """Gelir defteri. Kayıtlar otomatik oluşur (rezervasyon başına tek gelir kaydı); elle girilmez."""

    class TransactionType(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    class Category(models.TextChoices):
        RESERVATION = "reservation", "Reservation income"

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
    category = models.CharField(max_length=100, choices=Category.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="TRY")
    description = models.TextField(blank=True)
    transaction_date = models.DateField()

    class Meta:
        constraints = [
            # Rezervasyon başına tek otomatik gelir kaydı.
            models.UniqueConstraint(
                fields=["reservation"],
                condition=models.Q(category="reservation"),
                name="unique_reservation_income",
            ),
        ]

    def __str__(self):
        return f"{self.transaction_type} - {self.amount}"
