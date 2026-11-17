from django.contrib import admin
from .models import FinancialTransaction, RecurringExpense

admin.site.register(FinancialTransaction)
admin.site.register(RecurringExpense)
