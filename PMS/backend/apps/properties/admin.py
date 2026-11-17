from django.contrib import admin
from .models import DailyRate, Property, PropertyImage, SeasonalRate

admin.site.register(Property)
admin.site.register(PropertyImage)
admin.site.register(SeasonalRate)
admin.site.register(DailyRate)
