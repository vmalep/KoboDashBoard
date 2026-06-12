# KoboToolBox Dashboard

A Django web application that connects to a [KoboToolBox](https://www.kobotoolbox.org/) server, pulls form submission data via the v2 REST API, and displays it to authenticated users through customisable dashboards.

The app is generic: it can connect to any KoboToolBox server and display any number of forms. Each form can have its own **dashboard module** — a single Python file that defines how submissions are parsed, visualised, and exported. Forms without a module fall back to a generic group/tab table view.

---

## Features

- Connect to any KoboToolBox server (IFRC, Humanitarian, or self-hosted)
- Manage multiple forms simultaneously, each with its own module and cache TTL
- Per-form dashboard modules: upload/download via the web UI, no server restart needed for new forms
- Authentication with email + password, registration, and password reset (French UI)
- Staff user management: activate/deactivate/delete users from the web UI
- File-based cache with configurable TTL per form
- CSV and XLSX export

---

## Architecture

```
kobodashboard/        Django project config
                      settings.py reads .env via python-decouple

kobo/                 KoboToolBox integration
  models.py           KoboConfig (server URL + API token)
                      ConfiguredForm (one row per active form)
  api_client.py       requests wrapper for /api/v2/assets/ and /data/
  cache_helpers.py    file-based cache layer keyed by form UID

accounts/             Email-based login, registration, password reset

dashboard/            UI views and Bootstrap 5 templates
  views.py            form_list, settings_view, coverage, submission_list,
                      submission_detail, export_csv, export_xlsx,
                      module_download, module_upload

form_modules/         Dashboard module plugin system
  __init__.py         Registry + auto-discovery of *.py files
  base.py             FormModule base class
  dnh.py              Do Not Harm checklist module (AMOPAH project)
```

---

## Module system

Each form type has a **module** — a Python file in `form_modules/` decorated with `@register('form-uid')`:

```python
from form_modules import register
from form_modules.base import FormModule

@register('your-form-uid-here')
class MyFormModule(FormModule):
    form_label = 'My Dashboard'
    FIELD_PATHS = { ... }        # logical name → KoboToolBox field path
    EXPORT_HEADERS = [ ... ]     # CSV/XLSX column headers

    def parse_structure(self, schema): ...
    def parse_submission_detail(self, submission, structure): ...
```

Modules are **auto-discovered** at startup — drop a file in `form_modules/` and it registers itself. No other changes needed.

Modules can be **uploaded and downloaded** from the Settings page without touching the server filesystem directly.

---

## Setup (development)

### Requirements

- Python 3.10+
- A KoboToolBox account with API token

### Install

```bash
git clone https://github.com/vmalep/koboDashBoard.git
cd koboDashBoard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env and set SECRET_KEY, DEBUG=True, ALLOWED_HOSTS=localhost
```

### Run

```bash
source .venv/bin/activate
python3 manage.py migrate
python3 manage.py createsuperuser
python3 manage.py runserver
```

Open http://localhost:8000/ and log in with your superuser email and password.

Go to **Paramètres** to enter your KoboToolBox server URL and API token, then add forms.

---

## Environment variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | Django secret key (required) |
| `DEBUG` | `False` | Set `True` in development |
| `ALLOWED_HOSTS` | — | Comma-separated hostnames |
| `CSRF_TRUSTED_ORIGINS` | — | Required in production behind a proxy |
| `EMAIL_BACKEND` | `console` | Django email backend |
| `EMAIL_HOST` | — | SMTP host (production) |
| `EMAIL_PORT` | `587` | SMTP port |
| `EMAIL_HOST_USER` | — | SMTP username |
| `EMAIL_HOST_PASSWORD` | — | SMTP password |
| `EMAIL_USE_TLS` | `True` | Use TLS for SMTP |
| `DEFAULT_FROM_EMAIL` | — | From address for password reset emails |

---

## Production deployment

The reference deployment runs on an Ubuntu server alongside a Nextcloud snap. The Nextcloud snap owns ports 80/443, so Django runs on a separate port behind a system nginx reverse proxy.

### First-time setup

```bash
# 1. Copy project
sudo cp -r . /srv/kobodashboard/
cd /srv/kobodashboard

# 2. Create virtualenv and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env: DEBUG=False, ALLOWED_HOSTS, SECRET_KEY, CSRF_TRUSTED_ORIGINS

# 4. Initialise database and static files
python3 manage.py migrate
python3 manage.py createsuperuser
python3 manage.py collectstatic --no-input

# 5. Create log directory
sudo mkdir -p /var/log/kobodashboard
sudo chown www-data: /var/log/kobodashboard

# 6. Install systemd service
sudo cp deploy/kobodashboard.service /etc/systemd/system/
sudo systemctl enable --now kobodashboard

# 7. Install nginx config and obtain TLS certificate
sudo cp deploy/nginx-kobodash.conf /etc/nginx/sites-available/kobodash
sudo ln -s /etc/nginx/sites-available/kobodash /etc/nginx/sites-enabled/
sudo certbot --nginx -d kobodash.vmalep.eu
sudo systemctl reload nginx
```

### Update

```bash
cd /srv/kobodashboard
git pull
source .venv/bin/activate
pip install -r requirements.txt   # if dependencies changed
python3 manage.py migrate
sudo systemctl restart kobodashboard
```

---

## Modules included

| Module file | Form | Description |
|---|---|---|
| `form_modules/dnh.py` | CheckList Do Not Harm | Coverage matrix showing which Do Not Harm activities are covered per country, with risk analysis drill-down |
| `form_modules/amopah3.py` | FORMULAIRE_DASHBOARD_AMOPAH III | Indicator monitoring dashboard for the AMOPAH III program (5 countries, 4 results, 48 indicators). Charts by country/result/period, disaggregation breakdowns (age/sex, disability, population status), data table, CSV/XLSX export |

---

## License

MIT
