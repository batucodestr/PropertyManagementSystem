# PMS — Property Management System

Kısa dönem kiralık evler için mülk yönetim sistemi. Rezervasyonları, misafirleri, operasyonel görevleri ve finansı tek panelde toplar; Beds24 üzerinden Airbnb ve Booking.com gibi kanallarla senkron çalışır.

## Özellikler

- **Mülkler** — ev bilgileri, fiyatlandırma, erişim bilgileri ve herkese açık salt-okunur API
- **Rezervasyonlar & Misafirler** — takvim görünümü, misafir kayıtları
- **Beds24 entegrasyonu** — mülk/rezervasyon senkronu, webhook, periyodik polling, silinen rezervasyonların takibi
- **Mesajlaşma** — kanal mesajları ve e-posta ile misafire yanıt
- **Operasyon** — öncelikli görev yönetimi
- **Finans** — rezervasyonlardan otomatik gelir/komisyon kaydı ve raporlar
- **Dashboard** — özet metrikler, çoklu dil desteği (i18n)

## Teknolojiler

| Katman   | Teknoloji |
|----------|-----------|
| Backend  | Django 5, Django REST Framework, SimpleJWT |
| Arka plan | Celery + Redis |
| Veritabanı | PostgreSQL 16 |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS |
| Dağıtım  | Docker Compose, Nginx, Gunicorn |

## Proje Yapısı

```
PMS/
├── backend/          # Django API (apps: properties, reservations, guests,
│                     #   operations, finance, messaging, integrations, ...)
├── frontend/         # React yönetim paneli
└── docker-compose.yml
```

## Kurulum

### Docker ile (önerilen)

```bash
cd PMS
cp backend/pms/.env.example backend/pms/.env   # değerleri doldurun
docker compose up -d --build
docker compose exec backend python manage.py createsuperuser
```

Uygulama `http://localhost` adresinde açılır (port `WEB_PORT` ile değiştirilebilir).

### Yerel geliştirme

```bash
# Backend
cd PMS/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

# Celery (ayrı terminallerde)
celery -A pms worker -l info
celery -A pms beat -l info

# Frontend
cd PMS/frontend
npm install
npm run dev
```

PostgreSQL ve Redis için `docker compose up -d db redis` kullanılabilir.

## Yapılandırma

Tüm ayarlar `PMS/backend/pms/.env` dosyasından okunur; şablon için [.env.example](PMS/backend/pms/.env.example) dosyasına bakın. Başlıca değişkenler:

- `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`
- `DATABASE_*`, `REDIS_URL`
- `BEDS24_REFRESH_TOKEN`, `BEDS24_WEBHOOK_SECRET`, `PUBLIC_BASE_URL`
- `EMAIL_*` (opsiyonel)

> `.env` dosyası gizli bilgiler içerir, asla commit'lemeyin.

## Beds24 Komutları

```bash
python manage.py beds24_ping             # bağlantı testi
python manage.py beds24_sync_all         # tam senkron
python manage.py beds24_pull_bookings    # rezervasyonları çek
python manage.py beds24_link_property    # mülkü Beds24 ile eşle
```

## Testler

```bash
cd PMS/backend
python manage.py test
```

API örnekleri için Postman koleksiyonu: [PMS.postman_collection.json](PMS/backend/postman/PMS.postman_collection.json)

## Lisans

[MIT](LICENSE) — Frontend, MIT lisanslı [TailAdmin](https://tailadmin.com) şablonu üzerine inşa edilmiştir.
