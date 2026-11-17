from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.testing import AuthenticatedAPITestCase, make_guest, make_property
from apps.operations.models import HouseKeepingTasks
from apps.properties.models import Property
from apps.reservations.models import Reservation

IST = ZoneInfo('Europe/Istanbul')


def book(prop, check_in, nights=2, status='confirmed', **extra):
    return Reservation.objects.create(
        property=prop, guest=make_guest(), status=status, total_price=Decimal('100'),
        check_in=datetime.combine(check_in, time(15), tzinfo=IST),
        check_out=datetime.combine(check_in + timedelta(days=nights), time(11), tzinfo=IST), **extra,
    )


def auto_task(reservation):
    return HouseKeepingTasks.objects.filter(reservation=reservation, is_auto=True).first()


@override_settings(PROPERTY_TIMEZONE='Europe/Istanbul')
class HousekeepingAutomationTests(TestCase):
    def setUp(self):
        self.prop = make_property()

    def test_confirmed_reservation_creates_checkout_task_once(self):
        r = book(self.prop, date(2030, 7, 1), nights=3)
        task = auto_task(r)
        self.assertEqual((task.scheduled_date, task.priority), (date(2030, 7, 4), 'normal'))
        r.save()
        r.save()
        self.assertEqual(HouseKeepingTasks.objects.filter(reservation=r).count(), 1)

    def test_pending_reservation_has_no_task_until_confirmed(self):
        r = book(self.prop, date(2030, 7, 1), status='pending')
        self.assertIsNone(auto_task(r))
        r.status = 'confirmed'
        r.save()
        self.assertIsNotNone(auto_task(r))

    def test_date_change_moves_pending_task(self):
        r = book(self.prop, date(2030, 7, 1), nights=3)
        r.check_out = datetime.combine(date(2030, 7, 6), time(11), tzinfo=IST)
        r.save()
        self.assertEqual(auto_task(r).scheduled_date, date(2030, 7, 6))

    def test_cancellation_removes_pending_task_but_keeps_started_one(self):
        r = book(self.prop, date(2030, 7, 1))
        r.status = 'cancelled'
        r.save()
        self.assertIsNone(auto_task(r))
        r2 = book(self.prop, date(2030, 8, 1))
        task = auto_task(r2)
        task.status = 'in_progress'
        task.save()
        r2.status = 'cancelled'
        r2.save()
        self.assertIsNotNone(auto_task(r2))

    def test_same_day_check_in_marks_task_urgent_and_back(self):
        first = book(self.prop, date(2030, 7, 1), nights=3)  # check-out 4 Tem
        second = book(self.prop, date(2030, 7, 4), nights=2)  # aynı gün giriş
        self.assertEqual(auto_task(first).priority, 'urgent')
        self.assertEqual(auto_task(second).priority, 'normal')
        second.status = 'cancelled'
        second.save()
        self.assertEqual(auto_task(first).priority, 'normal')

    def test_property_housekeeping_status_flow(self):
        r = book(self.prop, date(2030, 7, 1))
        r.status = 'completed'
        r.save()
        self.assertEqual(Property.objects.get(pk=self.prop.pk).housekeeping_status, 'dirty')
        task = auto_task(r)
        task.status = 'in_progress'
        task.save()
        self.assertEqual(Property.objects.get(pk=self.prop.pk).housekeeping_status, 'cleaning')
        task.status = 'completed'
        task.save()
        self.assertEqual(Property.objects.get(pk=self.prop.pk).housekeeping_status, 'ready')


class TaskPriorityTests(AuthenticatedAPITestCase):
    def test_task_priority_and_filter(self):
        prop = make_property()
        response = self.client.post('/api/general-tasks/', {
            'property': str(prop.pk), 'description': 'Fix boiler', 'due_date': '2030-01-01', 'priority': 'critical',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['priority'], 'critical')
        self.client.post('/api/general-tasks/', {
            'property': str(prop.pk), 'description': 'Buy soap', 'due_date': '2030-01-01',
        }, format='json')
        self.assertEqual(self.client.get('/api/general-tasks/', {'priority': 'critical'}).json()['count'], 1)
        bad = self.client.post('/api/general-tasks/', {
            'property': str(prop.pk), 'description': 'x', 'due_date': '2030-01-01', 'priority': 'asap',
        }, format='json')
        self.assertEqual(bad.status_code, 400)

    def test_removed_endpoints_are_gone(self):
        for url in ('/api/cleaner/tasks/', '/api/task-photos/', '/api/accounts/me/', '/api/messaging/templates/',
                    '/api/messaging/scheduled/', '/api/finance/recurring-expenses/'):
            self.assertEqual(self.client.get(url).status_code, 404, url)
