from django.dispatch import Signal

# Toplu fiyat değişikliği (kanal entegrasyonları dinler). kwargs: property, date_from, date_to
rates_changed = Signal()
