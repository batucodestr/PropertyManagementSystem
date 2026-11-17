from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.core.testing import AuthenticatedAPITestCase, make_guest, make_property
from apps.finance.models import FinancialTransaction
from apps.operations.models import GeneralTask, HouseKeepingTasks, TaskPhoto
from apps.properties.models import Property
from apps.reservations.models import AvailabilityBlock, Reservation

IST = ZoneInfo('Europe/Istanbul')


def png_bytes():
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new('RGB', (2, 2), (200, 30, 30)).save(buf, format='PNG')
    return buf.getvalue()


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
        self.cleaner = User.objects.create_user('cleaner1')
        self.prop = make_property(default_cleaner=self.cleaner)

    def test_confirmed_reservation_creates_checkout_task_once(self):
        r = book(self.prop, date(2030, 7, 1), nights=3)
        task = auto_task(r)
        self.assertEqual((task.scheduled_date, task.assigned_to, task.priority),
                         (date(2030, 7, 4), self.cleaner, 'normal'))
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


@override_settings(PROPERTY_TIMEZONE='Europe/Istanbul')
class CleanerViewTests(APITestCase):
    def setUp(self):
        self.cleaner = User.objects.create_user('cleaner1')
        self.cleaner.groups.add(Group.objects.get(name='cleaner'))
        self.other = User.objects.create_user('cleaner2')
        self.prop = make_property()
        today = timezone.localdate(timezone=IST)
        self.mine = HouseKeepingTasks.objects.create(property=self.prop, scheduled_date=today, assigned_to=self.cleaner)
        self.tomorrow = HouseKeepingTasks.objects.create(property=self.prop, scheduled_date=today + timedelta(days=1),
                                                         assigned_to=self.cleaner)
        HouseKeepingTasks.objects.create(property=self.prop, scheduled_date=today + timedelta(days=5),
                                         assigned_to=self.cleaner)
        self.theirs = HouseKeepingTasks.objects.create(property=self.prop, scheduled_date=today, assigned_to=self.other)
        self.client.force_authenticate(self.cleaner)

    def test_lists_only_own_today_and_tomorrow(self):
        ids = {t['id'] for t in self.client.get('/api/cleaner/tasks/').json()}
        self.assertEqual(ids, {str(self.mine.pk), str(self.tomorrow.pk)})

    def test_start_complete_notes_and_photo(self):
        url = f'/api/cleaner/tasks/{self.mine.pk}/'
        self.assertEqual(self.client.post(url + 'start/').json()['status'], 'in_progress')
        self.client.post(url + 'notes/', {'notes': 'Towels missing'}, format='json')
        response = self.client.post(url + 'photos/', {'image': SimpleUploadedFile('a.png', png_bytes(), 'image/png')},
                                    format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(len(response.json()['photos']), 1)
        done = self.client.post(url + 'complete/').json()
        self.assertEqual((done['status'], done['notes']), ('completed', 'Towels missing'))
        photo = TaskPhoto.objects.get()
        self.assertRegex(photo.image.name, r'^task_photos/[0-9a-f]{32}/a\.png$')
        photo.image.delete(save=False)

    def test_cannot_touch_someone_elses_task(self):
        self.assertEqual(self.client.post(f'/api/cleaner/tasks/{self.theirs.pk}/start/').status_code, 404)

    def test_cleaner_is_blocked_from_management_api(self):
        for url in ('/api/reservations/', '/api/properties/', '/api/finance/summary/', '/api/guests/',
                    f'/api/properties/{self.prop.pk}/access-info/'):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        me = self.client.get('/api/accounts/me/').json()
        self.assertEqual(me['role'], 'cleaner')

    def test_manager_in_both_groups_has_full_access(self):
        self.cleaner.groups.add(Group.objects.get(name='manager'))
        self.assertEqual(self.client.get('/api/reservations/').status_code, 200)
        self.assertEqual(self.client.get('/api/accounts/me/').json()['role'], 'manager')


class MaintenanceTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.prop = make_property()

    def test_critical_issue_closes_calendar_until_resolved(self):
        until = (timezone.localdate() + timedelta(days=3)).isoformat()
        response = self.client.post('/api/general-tasks/', {
            'property': str(self.prop.pk), 'description': 'Water leak', 'due_date': timezone.localdate().isoformat(),
            'task_type': 'maintenance', 'priority': 'critical', 'close_calendar_until': until,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['calendar_closed_until'], until)
        task = GeneralTask.objects.get()
        self.assertEqual(AvailabilityBlock.objects.get().end_date.isoformat(), until)
        response = self.client.patch(f'/api/general-tasks/{task.pk}/', {'status': 'completed', 'cost': '850'},
                                     format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AvailabilityBlock.objects.exists())
        self.assertEqual(FinancialTransaction.objects.get(general_task=task).amount, Decimal('850.00'))

    def test_filters_and_validation(self):
        GeneralTask.objects.create(property=self.prop, description='Fix', due_date=date(2030, 1, 1),
                                   task_type='maintenance', priority='high')
        GeneralTask.objects.create(property=self.prop, description='Buy', due_date=date(2030, 1, 1))
        data = self.client.get('/api/general-tasks/', {'task_type': 'maintenance'}).json()
        self.assertEqual(data['count'], 1)
        bad = self.client.post('/api/general-tasks/', {
            'property': str(self.prop.pk), 'description': 'x', 'due_date': '2030-01-01',
            'close_calendar_until': '2000-01-01',
        }, format='json')
        self.assertEqual(bad.status_code, 400)

    def test_users_endpoint_filters_by_group(self):
        cleaner = User.objects.create_user('c1', first_name='Ayşe')
        cleaner.groups.add(Group.objects.get(name='cleaner'))
        data = self.client.get('/api/accounts/users/', {'group': 'cleaner'}).json()
        self.assertEqual([u['username'] for u in data], ['c1'])
