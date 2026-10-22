# Saray Restaurant

The live site is the Django project in `saray_restaurant/`. The HTML files in
the repository root are older static prototypes.

Use Python 3.12 or newer. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd saray_restaurant
python manage.py migrate
python manage.py runserver 127.0.0.1:8011
```

Open <http://127.0.0.1:8011/>. The original `/saray-menu/` home URL and
`/saray-menu/menu/` menu URL also work. If another project is already running
on this port, choose a different port in the `runserver` command.

Run the Django regression suite from `saray_restaurant/`:

```powershell
python manage.py check
python manage.py test
```

For browser checks, install the optional test dependencies from the repository
root, start the server above in another terminal, and run:

```powershell
python -m pip install -r requirements-test.txt
python -m playwright install chromium
python scripts/browser_smoke.py
```

You can pass `--base-url http://127.0.0.1:PORT` for a different server port or
`--browser "C:\path\to\browser.exe"` to use an existing Chromium-based browser.
The script checks phone, tablet, and desktop layouts, image loading,
navigation, carousel controls, and mobile menu keyboard behavior. Screenshots
are saved in `.test-output/`.
