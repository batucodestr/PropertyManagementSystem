from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.core.testing import AuthenticatedAPITestCase, make_guest, make_property
from apps.finance import services
from apps.finance.models import FinancialTransaction, RecurringExpense
from apps.operations.models import GeneralTask, HouseKeepingTasks
from apps.reservations.models import Reservation

IST = ZoneInfo('Europe/Istanbul')


def make_reservation(prop=None, *, source='airbnb', status='confirmed', total='1000.00',
                     check_in=date(2030, 7, 1), nights=4, **extra):
    return Reservation.objects.create(
        property=prop or make_property(), guest=make_guest(),
        check_in=datetime.combine(check_in, datetime.min.time().replace(hour=15), tzinfo=IST),
        check_out=datetime.combine(check_in + timedelta(days=nights), datetime.min.time().replace(hour=11), tzinfo=IST),
        total_price=Decimal(total), source=source, status=status, **extra,
    )


def income(reservation):
    return FinancialTransaction.objects.filter(reservation=reservation, category='reservation')


@override_settings(CHANNEL_COMMISSIONS={'airbnb': '15.5', 'booking': '15', 'direct': '0', 'other': '0'},
                   PROPERTY_TIMEZONE='Europe/Istanbul')
class ReservationFinanceTests(TestCase):
    def test_airbnb_commission_is_estimated_and_net_computed(self):
        r = make_reservation(total='1000.00')
        self.assertEqual(r.channel_commission, Decimal('155.00'))
        self.assertTrue(r.commission_is_estimated)
        self.assertEqual(r.net_amount, Decimal('845.00'))

    def test_net_formula_excludes_cleaning_fee_and_subtracts_taxes(self):
        r = make_reservation(total='1000.00', taxes=Decimal('50'), cleaning_fee=Decimal('120'))
        # net = toplam - komisyon - vergi ; temizlik ücreti toplamın içinde, ayrıca düşülmez
        self.assertEqual(r.net_amount, Decimal('795.00'))

    def test_rounding_is_half_up(self):
        r = make_reservation(total='99.99')  # 99.99 * 0.155 = 15.49845
        self.assertEqual(r.channel_commission, Decimal('15.50'))
        self.assertEqual(r.net_amount, Decimal('84.49'))
        r2 = make_reservation(total='10.10', source='booking')  # 1.515 -> 1.52
        self.assertEqual(r2.channel_commission, Decimal('1.52'))

    def test_direct_has_no_commission(self):
        r = make_reservation(source='direct', total='500')
        self.assertEqual((r.channel_commission, r.commission_is_estimated, r.net_amount),
                         (Decimal('0.00'), False, Decimal('500.00')))

    def test_estimate_follows_price_but_manual_commission_sticks(self):
        r = make_reservation(total='1000')
        r.total_price = Decimal('2000')
        r.save()
        self.assertEqual(r.channel_commission, Decimal('310.00'))
        r.channel_commission, r.commission_is_estimated = Decimal('250'), False
        r.save()
        r.total_price = Decimal('3000')
        r.save()
        r.refresh_from_db()
        self.assertEqual((r.channel_commission, r.net_amount), (Decimal('250.00'), Decimal('2750.00')))

    def test_income_transaction_lifecycle(self):
        r = make_reservation(status='pending')
        self.assertFalse(income(r).exists())
        r.status = 'confirmed'
        r.save()
        tx = income(r).get()
        self.assertEqual((tx.transaction_type, tx.amount, tx.transaction_date),
                         ('income', Decimal('845.00'), date(2030, 7, 1)))
        r.total_price = Decimal('1200')
        r.save()
        self.assertEqual(income(r).get().amount, Decimal('1014.00'))
        self.assertEqual(income(r).count(), 1)
        r.status = 'cancelled'
        r.save()
        self.assertFalse(income(r).exists())  # iptal: kayıt silinir (ters kayıt yok)
        r.status = 'confirmed'
        r.save()
        self.assertEqual(income(r).count(), 1)

    def test_completed_keeps_income_and_no_show_removes_it(self):
        r = make_reservation()
        r.status = 'completed'
        r.save()
        self.assertTrue(income(r).exists())
        r2 = make_reservation(check_in=date(2030, 8, 1))
        r2.status = 'no_show'
        r2.save()
        self.assertFalse(income(r2).exists())

    def test_update_fields_save_still_persists_finance(self):
        r = make_reservation(total='1000')
        r.total_price = Decimal('2000')
        r.save(update_fields=['total_price', 'updated_at'])
        r.refresh_from_db()
        self.assertEqual(r.net_amount, Decimal('1690.00'))
        self.assertEqual(income(r).get().amount, Decimal('1690.00'))


class TaskExpenseTests(TestCase):
    def setUp(self):
        self.prop = make_property()

    def test_housekeeping_cost_becomes_cleaning_expense(self):
        task = HouseKeepingTasks.objects.create(property=self.prop, scheduled_date=date(2030, 7, 5))
        task.status, task.cost, task.completed_date = 'completed', Decimal('350'), date(2030, 7, 5)
        task.save()
        tx = FinancialTransaction.objects.get(housekeeping_task=task)
        self.assertEqual((tx.transaction_type, tx.category, tx.amount), ('expense', 'cleaning', Decimal('350.00')))
        task.cost = Decimal('400')
        task.save()
        self.assertEqual(FinancialTransaction.objects.get(housekeeping_task=task).amount, Decimal('400.00'))
        task.status = 'in_progress'
        task.save()
        self.assertFalse(FinancialTransaction.objects.filter(housekeeping_task=task).exists())

    def test_general_task_cost_becomes_maintenance_expense(self):
        task = GeneralTask.objects.create(property=self.prop, description='Fix boiler', due_date=date(2030, 7, 1),
                                          status='completed', cost=Decimal('1200'))
        self.assertEqual(FinancialTransaction.objects.get(general_task=task).category, 'maintenance')

    def test_completed_without_cost_creates_nothing(self):
        HouseKeepingTasks.objects.create(property=self.prop, scheduled_date=date(2030, 7, 5), status='completed')
        self.assertFalse(FinancialTransaction.objects.exists())


class RecurringExpenseTests(TestCase):
    def setUp(self):
        self.rec = RecurringExpense.objects.create(
            property=make_property(), category='dues', amount=Decimal('750'), day_of_month=5,
            start_date=date(2030, 1, 1),
        )

    def test_generates_once_per_month_on_or_after_day(self):
        self.assertEqual(services.generate_recurring_expenses(date(2030, 3, 4)), 0)
        self.assertEqual(services.generate_recurring_expenses(date(2030, 3, 5)), 1)
        self.assertEqual(services.generate_recurring_expenses(date(2030, 3, 20)), 0)
        tx = FinancialTransaction.objects.get()
        self.assertEqual((tx.transaction_date, tx.amount, tx.category), (date(2030, 3, 5), Decimal('750.00'), 'dues'))
        self.assertEqual(services.generate_recurring_expenses(date(2030, 4, 6)), 1)

    def test_respects_end_date_and_active_flag(self):
        self.rec.end_date = date(2030, 2, 28)
        self.rec.save()
        self.assertEqual(services.generate_recurring_expenses(date(2030, 3, 10)), 0)
        self.rec.end_date, self.rec.is_active = None, False
        self.rec.save()
        self.assertEqual(services.generate_recurring_expenses(date(2030, 3, 10)), 0)


@override_settings(CHANNEL_COMMISSIONS={'airbnb': '15.5', 'booking': '15', 'direct': '0', 'other': '0'},
                   PROPERTY_TIMEZONE='Europe/Istanbul')
class FinanceApiTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.a = make_property(name='A')
        self.b = make_property(name='B')

    def test_summary_prorates_by_night_and_breaks_down(self):
        # 4 gece: 30 Haz – 4 Tem -> Temmuz'a 3 gece düşer (3/4)
        make_reservation(self.a, total='1000', check_in=date(2030, 6, 30), nights=4)
        make_reservation(self.b, source='direct', total='600', check_in=date(2030, 7, 10), nights=2)
        make_reservation(self.b, status='cancelled', total='9999', check_in=date(2030, 7, 20))
        FinancialTransaction.objects.create(property=self.a, transaction_type='expense', category='cleaning',
                                            amount=Decimal('100'), transaction_date=date(2030, 7, 5))
        data = self.client.get('/api/finance/summary/', {'from': '2030-07-01', 'to': '2030-07-31'}).json()
        t = data['totals']
        self.assertEqual(t['gross'], '1350.00')        # 750 + 600
        self.assertEqual(t['commission'], '116.25')    # 155 * 3/4
        self.assertEqual(t['net'], '1233.75')          # 633.75 + 600
        self.assertEqual(t['expenses'], '100.00')
        self.assertEqual(t['profit'], '1133.75')
        self.assertEqual(t['nights'], 5)
        self.assertEqual(t['available_nights'], 62)    # 2 ev x 31 gün
        self.assertEqual(t['occupancy'], '8.06')
        self.assertEqual(t['adr'], '270.00')
        self.assertEqual(t['revpar'], '21.77')
        by_prop = {p['name']: p for p in data['by_property']}
        self.assertEqual(by_prop['A']['profit'], '533.75')
        self.assertEqual(by_prop['B']['net'], '600.00')
        by_channel = {c['source']: c for c in data['by_channel']}
        self.assertEqual(by_channel['airbnb']['gross'], '750.00')
        self.assertEqual(by_channel['direct']['gross'], '600.00')
        self.assertEqual(data['expenses_by_category'], {'cleaning': '100.00'})

    def test_adding_expense_updates_property_profit(self):
        make_reservation(self.a, source='direct', total='1000', check_in=date(2030, 7, 1), nights=2)
        url = '/api/finance/summary/'
        params = {'from': '2030-07-01', 'to': '2030-07-31', 'property': str(self.a.pk)}
        self.assertEqual(self.client.get(url, params).json()['totals']['profit'], '1000.00')
        response = self.client.post('/api/finance/transactions/', {
            'property': str(self.a.pk), 'transaction_type': 'expense', 'category': 'maintenance',
            'amount': '250.50', 'transaction_date': '2030-07-15',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.client.get(url, params).json()['totals']['profit'], '749.50')

    def test_summary_validation(self):
        url = '/api/finance/summary/'
        self.assertEqual(self.client.get(url, {'from': '2030-07-10', 'to': '2030-07-01'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'from': 'x'}).status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 200)  # varsayılan: bu ay

    def test_transaction_rules(self):
        url = '/api/finance/transactions/'
        base = {'property': str(self.a.pk), 'amount': '10', 'transaction_date': '2030-07-01'}
        self.assertEqual(self.client.post(url, {**base, 'transaction_type': 'expense', 'category': 'other_income'},
                                          format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {**base, 'transaction_type': 'income', 'category': 'reservation'},
                                          format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {**base, 'transaction_type': 'expense', 'category': 'nonsense'},
                                          format='json').status_code, 400)
        r = make_reservation(self.a)
        auto = income(r).get()
        self.assertEqual(self.client.patch(f'{url}{auto.pk}/', {'amount': '1'}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(f'{url}{auto.pk}/').status_code, 400)
        listed = self.client.get(url, {'transaction_type': 'income'}).json()['results']
        self.assertTrue(listed[0]['is_automatic'])

    def test_receipt_upload(self):
        response = self.client.post('/api/finance/transactions/', {
            'property': str(self.a.pk), 'transaction_type': 'expense', 'category': 'electricity',
            'amount': '420', 'transaction_date': '2030-07-01',
            'receipt': SimpleUploadedFile('fatura.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        tx = FinancialTransaction.objects.get()
        self.assertRegex(tx.receipt.name, r'^receipts/[0-9a-f]{32}/fatura\.pdf$')
        tx.receipt.delete(save=False)
        bad = self.client.post('/api/finance/transactions/', {
            'property': str(self.a.pk), 'transaction_type': 'expense', 'category': 'other',
            'amount': '1', 'transaction_date': '2030-07-01',
            'receipt': SimpleUploadedFile('x.exe', b'MZ', content_type='application/octet-stream'),
        }, format='multipart')
        self.assertEqual(bad.status_code, 400)

    def test_payments_list_totals_and_mark_paid(self):
        r = make_reservation(self.a, total='1000')
        make_reservation(self.b, status='pending', total='500')  # gelir yok -> listede yok
        data = self.client.get('/api/finance/payments/').json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['totals'], {'gross': '1000.00', 'commission': '155.00', 'net': '845.00',
                                          'pending_net': '845.00'})
        response = self.client.patch(f'/api/finance/payments/{r.pk}/', {'payout_status': 'paid'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()['payout_date'])
        response = self.client.patch(f'/api/finance/payments/{r.pk}/', {'channel_commission': '120.00'},
                                     format='json')
        body = response.json()
        self.assertEqual((body['commission_is_estimated'], body['net_amount']), (False, '880.00'))
        self.assertEqual(income(r).get().amount, Decimal('880.00'))
        # total_price bu uçtan değiştirilemez
        self.client.patch(f'/api/finance/payments/{r.pk}/', {'total_price': '1'}, format='json')
        r.refresh_from_db()
        self.assertEqual(r.total_price, Decimal('1000.00'))

    def test_recurring_expense_validation(self):
        url = '/api/finance/recurring-expenses/'
        base = {'property': str(self.a.pk), 'amount': '750', 'start_date': '2030-01-01'}
        self.assertEqual(self.client.post(url, {**base, 'category': 'dues', 'day_of_month': 31},
                                          format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {**base, 'category': 'other_income', 'day_of_month': 1},
                                          format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {**base, 'category': 'dues', 'day_of_month': 5},
                                          format='json').status_code, 201)
