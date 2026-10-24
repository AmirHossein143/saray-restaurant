# رستوران سارای — Saray Restaurant website

The website of Saray, a kabab house in Baghmisheh, Tabriz. Persian (RTL),
built with Django. It includes:

- **Home**: hero slideshow, chef's signature dishes, menu categories, visit-us section.
- **Menu** (`/menu/`): the full menu from the database. Sticky category tabs,
  live search (handles Persian/Arabic letters and digits), filters
  (vegetarian / spicy / chef's pick), a dish detail dialog, and a print layout.
- **Table reservations** (`/reserve/`): Jalali (Shamsi) dates, time slots,
  Persian phone validation, spam protection. New bookings appear in the admin panel.
- **About, Contact, Photo credits**, a branded 404/500, `sitemap.xml`,
  `robots.txt`, and schema.org data for Google.
- **Admin panel** (`/admin/`), in Persian. A dashboard of today's reservations;
  edit prices, mark dishes unavailable, upload dish photos, and change the
  phone, hours, address, announcement bar and social links.

Fonts, icons and scripts are all served from this site, with no CDNs or
Google services, so the site works reliably for visitors in Iran.

## Run it locally

Use Python 3.12 or newer. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd saray_restaurant
python manage.py migrate          # creates db.sqlite3 and loads the real menu
python manage.py createsuperuser  # your admin login
python manage.py runserver
```

Open <http://127.0.0.1:8000/> for the site and <http://127.0.0.1:8000/admin/>
for the admin panel.

## Data Studio (browse and edit the database)

`/studio/` is a superuser-only, English control panel for the whole database:
every table with its row counts, search, column sorting, filters, paging, show/hide columns,
**double-click a cell to edit it in place**, a side panel to add or edit a row (with image
upload), delete with a warning of which dependent rows go with it, bulk delete, and CSV export.

- Open it from the **Data Studio** button on the Django admin home page, or go to `/studio/`
  and sign in with your admin account.
- Every change is validated like in the Django admin and recorded in its history (LogEntry).
- User, group, permission and system tables are read-only, and password hashes are never shown.
- Shortcuts: `/` search, `N` new row, `R` refresh, `Esc` close, `Ctrl+S` save.
- Deleting a category also deletes its dishes. The confirmation dialog tells you how many.

## Managing content

Everything the restaurant changes day to day is in the admin panel:

| Task | Where |
|---|---|
| Change a price, mark a dish sold out, feature a dish | **غذاها**: edit right in the list and press save |
| Add a photo of a dish | Open the dish and upload an image. It replaces the stock photo |
| Pizza sizes and prices | Open the pizza: **اندازه‌ها / انواع** at the bottom |
| Phone, address, hours, Instagram/Telegram, map location, announcement bar, turn reservations on/off | **تنظیمات سایت** |
| Today's bookings | The admin home page, or **رزروها**. Use the actions to confirm, cancel or mark as seated |

Map: enter the restaurant's latitude and longitude in **تنظیمات سایت** to
show an embedded map. Until then, the site links to Google Maps, Neshan and
Balad searches for the address.

The original menu spreadsheet is in [docs/menu.xlsx](docs/menu.xlsx). Its
contents were converted to `saray_restaurant/saray_menu/data/menu_seed.json`,
which `migrate` loads on a new database.
`python manage.py import_menu` loads that file again. **This overwrites prices
and text changed in the admin**, so use it only to reset the menu.

## Photos

Dish and site photos are freely licensed images from Wikimedia Commons, used
as illustrations. Each one is credited on `/credits/`, as its license
requires. Real photos of Saray's own dishes and dining room will always look
better: upload them per dish in the admin panel, or replace the files in
`saray_restaurant/saray_menu/static/saray_menu/img/site/` (hero images are
2000×1200 WebP).

## Tests

From `saray_restaurant/`:

```powershell
python manage.py check
python manage.py test
```

Browser checks (start the server first, in another terminal):

```powershell
python -m pip install -r requirements-test.txt
python -m playwright install firefox
python scripts/browser_smoke.py --base-url http://127.0.0.1:8000
```

The browser checks cover every page from 320px to 1440px wide: no
horizontal scrolling, no broken images or JavaScript errors. They also test
the mobile menu, menu search and filters, the dish dialog, and reservation
validation. Screenshots go to `.test-output/`. Add `--submit-reservation` to
also create one real test booking.

## Deploying

Set these environment variables on the server:

| Variable | Value |
|---|---|
| `DJANGO_DEBUG` | `0` |
| `DJANGO_SECRET_KEY` | a long random string (required when DEBUG is off) |
| `DJANGO_ALLOWED_HOSTS` | e.g. `saray-restaurant.ir,www.saray-restaurant.ir` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | e.g. `https://saray-restaurant.ir` |
| `DJANGO_ADMIN_USER` / `DJANGO_ADMIN_PASSWORD` | optional: `python manage.py ensure_admin` creates that admin |
| `RESERVATION_NOTIFY_EMAIL` | optional: email address notified of new bookings (plus the `DJANGO_EMAIL_*` SMTP settings) |
| `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_HSTS_SECONDS` | enable once HTTPS works |
| `DJANGO_TRUSTED_PROXY_COUNT` | number of reverse proxies in front of Django (usually `1` behind nginx). Needed so the booking limit sees real visitor IPs |
| `DJANGO_SERVE_MEDIA` | `1` if no separate web server serves `/media/` |

Then:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn saray_restaurant.wsgi   # or any WSGI server
```

Static files are served by WhiteNoise when DEBUG is off. Back up
`db.sqlite3` and the `media/` folder: they hold reservations, admin
changes and uploaded photos. Neither is in git.
