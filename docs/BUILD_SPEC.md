# Saray Restaurant — Build Spec (shared contract)

Saray (سارای) is a real restaurant in Tabriz, Iran. Persian (fa), RTL. Address:
"تبریز، باغمیشه، روبروی بازار ماهی". Phone: 041-36688554 (tel:+984136688554).
Open every day 10:00–24:00. Site credit "noronet.co" (the original developer) stays
in the footer ("طراحی و توسعه: noronet.co").

NEVER fabricate facts about the business: no founding year, no awards, no fake
reviews/testimonials, no fake ratings, no invented coordinates, no invented
Instagram handle. Atmospheric marketing copy is fine ("کباب زغالی", "مهمان‌نوازی
تبریزی"); verifiable claims are not. Anything the owner should supply lives in
`SiteSettings` and renders only when filled.

Project root: `saray_restaurant/` (contains `manage.py`). Python 3.14, Django 6.1,
Pillow and whitenoise installed. Run commands from `saray_restaurant/`.
No CDNs or external runtime requests at all (Iranian users often can't reach
Google/CDNs): every font, icon, script is self-hosted. No jQuery, no Bootstrap.

## Apps and ownership

| Area | Owner |
|---|---|
| `saray_restaurant/saray_restaurant/settings.py`, `urls.py` | backend |
| app `saray_menu`: models, admin, views, urls, forms, utils, templatetags, sitemaps, management commands, migrations, tests | backend |
| app `reservations`: models, admin, forms, views, urls, migrations, tests | backend |
| `saray_menu/templates/admin/**` and `saray_menu/static/saray_menu/css/admin.css` | backend |
| `saray_menu/templates/saray_menu/**` (all public templates), `templates/404.html`, `500.html` | frontend |
| `reservations/templates/reservations/**` | frontend |
| `saray_menu/static/saray_menu/css/site.css`, `js/site.js`, `fonts/**`, `img/brand/**`, `img/ui/**` | frontend |
| `saray_menu/static/saray_menu/img/menu/**`, `img/site/**`, `saray_menu/data/photo_credits.json` | photos |

Do not edit files you don't own. If you need something from another owner, note it in
your final report.

## Data: `saray_menu/data/menu_seed.json` (already exists — do not change keys)

`{"categories":[{slug,name,name_en,icon,photo,description,items:[{slug,name,name_en,description,price|null,photo,is_featured,is_spicy,is_vegetarian,variants:[{label,price}]}]}]}`
Prices are integer Toman (e.g. 250000). `price` null + empty variants = no listed price
("قیمت را از همکاران ما بپرسید"). Pizzas have variants (medium 28 / large 32) and null price.
`photo` is a key; the image file for key K is
`saray_menu/static/saray_menu/img/menu/K.webp` (1200×900, 4:3) and `K-sm.webp` (600×450).

## Models (backend)

`saray_menu`:
- `SiteSettings` (singleton, pk=1, `SiteSettings.load()` classmethod): `name`
  ("رستوران سارای"), `tagline`, `phone`, `phone_display`, `address`, `about_text`
  (TextField), `opening_hours_text` ("همه‌روزه ۱۰ صبح تا ۱۲ شب"), `opens_at` (time 10:00),
  `closes_at` (time 23:59 — means midnight), `instagram_url` (blank), `telegram_url`
  (blank), `map_url` (blank), `latitude`/`longitude` (nullable Decimal), `reservations_enabled` (bool, True),
  `announcement` (blank short text; shown as a slim bar when filled).
- `Category`: `name`, `name_en`, `slug` (unique), `description`, `icon` (CharField choices
  matching icon keys: salad, skewer, pot, flame, pasta, pizza, burger, dessert, cup),
  `image` (ImageField upload_to='categories/', blank), `stock_photo` (CharField, the seed key),
  `order` (PositiveIntegerField), `is_active`. Meta ordering `['order','id']`.
  Property `photo_url` → uploaded image URL else static `img/menu/<stock_photo>.webp` else
  static placeholder `saray_menu/img/ui/placeholder.webp`. Also `photo_sm_url` (`-sm`).
  Method `get_absolute_url()` → `/menu/#<slug>`.
- `MenuItem`: `category` FK (related_name='items'), `name`, `name_en`, `slug` (unique),
  `description`, `price` (PositiveIntegerField null/blank, Toman), `image` (ImageField
  upload_to='menu/', blank), `stock_photo`, `is_available` (default True), `is_featured`,
  `is_spicy`, `is_vegetarian`, `order`, `created_at`, `updated_at`. Ordering
  `['category__order','order','id']`. Properties `photo_url`, `photo_sm_url` (same fallback),
  `display_price_range` not needed; `min_price` property (price or min variant price or None).
- `MenuItemVariant`: `item` FK (related_name='variants'), `label`, `price`, `order`.
- Data migration loads `menu_seed.json` (SiteSettings row + categories + items + variants),
  idempotent (update_or_create by slug). Also management command
  `python manage.py import_menu [--file path.json]` that does the same (shared function).

`reservations`:
- `Reservation`: `code` (unique, 6-char uppercase, auto, e.g. "SR4K7Q", no 0/O/1/I),
  `name`, `phone` (normalized ASCII digits), `date`, `time`, `guests` (1–20), `occasion`
  (choices: '', birthday تولد, anniversary سالگرد, business کاری, other سایر), `notes`,
  `status` (pending در انتظار تایید / confirmed تایید شده / seated حاضر شد / cancelled لغو شده /
  no_show نیامد; default pending), `staff_note`, `created_at`, `updated_at`, `ip_address`
  (nullable). Ordering `['date','time']`.

## Public URLs (names are the contract)

| URL | name | template | context |
|---|---|---|---|
| `/` | `home` | `saray_menu/home.html` | `featured_items` (≤8 MenuItem, available, featured, select_related category, prefetch variants), `categories` (active, annotated `item_count`) |
| `/menu/` | `menu` | `saray_menu/menu.html` | `categories` (active, with `prefetch_related('items__variants')` where items filtered to available — use `Prefetch('items', queryset=..., to_attr='available_items')`), `item_count` |
| `/about/` | `about` | `saray_menu/about.html` | — |
| `/contact/` | `contact` | `saray_menu/contact.html` | — |
| `/credits/` | `credits` | `saray_menu/credits.html` | `credits` (list of dicts from photo_credits.json: key, title, author, license, license_url, source_url) |
| `/reserve/` | `reservations:create` | `reservations/reserve.html` | `form`, `date_choices` (list of `{value:'2026-10-22', label:'پنج‌شنبه ۳۰ مهر', is_today, weekday}` for today..+30 days, labels Jalali + Persian digits), `time_choices` (list of `{value:'12:00', label:'۱۲:۰۰'}`, 12:00–22:30 every 30 min) |
| `/reserve/done/<code>/` | `reservations:done` | `reservations/done.html` | `reservation` (only viewable if code in session's `reservation_codes`, else 404) |
| `/sitemap.xml`, `/robots.txt` | | | |
| `/saray-menu/` → 301 `/`, `/saray-menu/menu/` → 301 `/menu/` | | | legacy redirects |
| `/admin/` | Django admin (Persian) | | |

Every public template gets, via context processor `saray_menu.context_processors.site`:
`site` (SiteSettings instance), `nav_categories` (active categories, id/name/slug only),
`current_year_fa` (Jalali year, Persian digits), `jalali_today` (string).

Reservation form (`reservations.forms.ReservationForm`, ModelForm): fields `name`, `phone`,
`date`, `time`, `guests`, `occasion`, `notes`, plus honeypot `website` (must be empty).
Persian error messages. Phone: accept Persian/Arabic digits, spaces, dashes, +98 → normalize
to `09xxxxxxxxx` (mobile) or 11-digit landline starting 0; reject otherwise. Date must be
within today..+30 (Asia/Tehran). Time must be one of `time_choices`; for today, at least
60 minutes after now. Guests 1–20 (for more: "برای مراسم بیش از ۲۰ نفر تماس بگیرید").
Rate limit: max 5 successful reservations per IP per hour (cache) → form error.
On success: save, append code to `request.session['reservation_codes']`, redirect to done.
If `site.reservations_enabled` is False: page shows a "call us" panel, POST rejected.
Form field widget attrs: name `autocomplete="name"`, phone `inputmode="tel" dir="ltr"
autocomplete="tel"`, date and time rendered by the template as radio "chips" (template
iterates `date_choices`/`time_choices`, input name `date` / `time`, value as given);
guests a number input min 1 max 20.

## Template tags/filters (backend, `{% load saray %}`)

- `fa_digits` — convert ASCII digits in str to Persian digits.
- `toman` — int Toman → `"۲۵۰ هزار تومان"` when divisible by 1000, else `"۲۵۰٬۵۰۰ تومان"`.
  `None` → `""`.
- `price_short` — int Toman → `"۲۵۰"` (thousands, Persian digits) for compact menu display
  (the template then writes "هزار تومان" once or as a small unit label).
- `jalali` — date → `"۱ آبان ۱۴۰۵"`; `jalali_long` → `"پنج‌شنبه ۱ آبان ۱۴۰۵"`.
- `{% json_ld_restaurant %}` simple_tag → `<script type="application/ld+json">` with
  schema.org Restaurant (name, address, telephone, servesCuisine, openingHours, url,
  hasMenu → menu url). Only real data.
Util `saray_menu/jalali.py`: `gregorian_to_jalali(y,m,d)`, `jalali_to_gregorian`,
month names, weekday names (Saturday-first Persian names), `format_jalali(date, long=False)`.

## Admin (backend)

Django admin in Persian (`LANGUAGE_CODE='fa'`, `TIME_ZONE='Asia/Tehran'`). Branding:
site_header "پنل مدیریت رستوران سارای", site_title "سارای", index_title "مدیریت".
`templates/admin/base_site.html` loads `saray_menu/fonts/fonts.css` and
`saray_menu/css/admin.css` (Vazirmatn everywhere, saffron accent `#C8902E`, brand colors).
`templates/admin/index.html`: dashboard cards on top — today's reservations (count +
list with time/name/guests/status), pending reservations count, upcoming 7 days count,
available/total menu items; link "مشاهده سایت". Then the normal app list.
MenuItem admin: list_display thumbnail, name, category, price (formatted), is_available,
is_featured; `list_editable` price/is_available/is_featured; filters; search; inline variants;
image preview; actions "ناموجود کردن"/"موجود کردن". Category admin with item counts,
list_editable order/is_active. SiteSettings admin: singleton (no add if exists, no delete).
Reservation admin: list_display code, jalali date, time, name, phone (tel link), guests,
colored status badge; filters status/date (custom "امروز/فردا/این هفته"), search name/phone/code;
actions confirm/cancel/seated/no_show; date_hierarchy date.

## Settings (backend)

Env-driven: `DJANGO_SECRET_KEY` (dev fallback), `DJANGO_DEBUG` (default "1" for local dev),
`DJANGO_ALLOWED_HOSTS` (comma list; default `localhost,127.0.0.1,[::1]` and `testserver`),
`DJANGO_CSRF_TRUSTED_ORIGINS`. When DEBUG is off: secure cookies, HSTS opt-in via env,
`SECURE_PROXY_SSL_HEADER`. whitenoise middleware + `CompressedManifestStaticFilesStorage`
only when not DEBUG (tests run with simple storage). `STATIC_ROOT = BASE_DIR/'staticfiles'`,
`MEDIA_URL='/media/'`, `MEDIA_ROOT=BASE_DIR/'media'` (served by Django in DEBUG). Cache:
LocMem. `handler404`/`handler500` use `404.html`/`500.html`. Optional
`RESERVATION_NOTIFY_EMAIL` → `send_mail(..., fail_silently=True)` on new reservation.

## Brand & design (frontend)

Mood: a warm Tabriz kabab house at night — charcoal grill glow, saffron, pomegranate,
turquoise tile accents, Persian geometric (girih / 8-point star) ornament. Elegant, not kitsch.
Tokens:
- `--ink #15110E` (near-black warm), `--charcoal #221B16`, `--ember #2C221B`
- `--saffron #C8902E` (primary accent), `--saffron-soft #E2B865`
- `--pomegranate #9E2B25` (secondary accent / badges), `--turquoise #1F7A74` (tile accent, small doses)
- `--ivory #F6EFE4` (light surface), `--sand #EADFCD`, `--text-dark #2A211B`, `--muted #8C7B6B`
Dark sections (hero, header, footer, signature) on ink/charcoal; menu and forms on ivory.
Font: Vazirmatn variable (self-hosted woff2 in `static/saray_menu/fonts/vazirmatn/`,
declared in `static/saray_menu/fonts/fonts.css` as family "Vazirmatn", with OFL license file).
Persian digits everywhere visible. Logo: SVG wordmark "سارای" + small Latin "SARAY · TABRIZ",
with an 8-point star mark; favicon SVG.
Icons: one inline SVG sprite (`{% include 'saray_menu/partials/icons.svg' %}` at top of body)
with symbols `i-salad,i-skewer,i-pot,i-flame,i-pasta,i-pizza,i-burger,i-dessert,i-cup,
i-phone,i-pin,i-clock,i-calendar,i-users,i-menu,i-close,i-search,i-instagram,i-telegram,
i-chili,i-leaf,i-star,i-arrow`.
Photos available (when photos phase is done): `img/menu/<key>.webp` and `-sm.webp` for every
seed key, plus `img/site/hero-1.webp`, `hero-2.webp`, `hero-3.webp` (2000×1200 food/ambience),
`img/site/tabriz.webp` (Tabriz city, 1600×1000), `img/site/grill.webp` (charcoal grill/kabab
skewers close-up, 1600×1000), `img/site/spread.webp` (Persian table spread, 1600×1000).
Placeholder for missing: `img/ui/placeholder.webp` (frontend generates — warm dark gradient
with the star mark).

Motion: subtle and purposeful — hero Ken Burns crossfade between hero images, scroll-reveal
(IntersectionObserver), ember particles or glow in hero (CSS/canvas, cheap), sticky header
that condenses on scroll, menu category nav scroll-spy with smooth scroll, live client-side
menu search/filter (veg/spicy chips), dish detail dialog (`<dialog>`) on click.
All motion disabled under `prefers-reduced-motion`. Works without JS (progressive enhancement).
Accessibility: semantic landmarks, skip link, focus-visible styles, contrast AA, `alt` text,
keyboard-operable nav drawer and dialog. Performance: `loading="lazy"` + `decoding="async"`
for below-the-fold images, width/height attributes, `-sm` images in grids with `srcset`.
Responsive 320px → 1920px, no horizontal overflow.
