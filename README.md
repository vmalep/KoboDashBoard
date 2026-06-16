# KoboDashBoard

**v1.0** — A Django web application that connects to a [KoboToolBox](https://www.kobotoolbox.org/) server, pulls form submission data via the v2 REST API, and displays it to authenticated users through customisable dashboards.

The app is generic: it can connect to any KoboToolBox server and display any number of forms. Each form can have its own **dashboard module** — a single Python file that defines how submissions are parsed, visualised, and exported. Forms without a module fall back to a generic group/tab table view.

---

## Features

- Connect to any KoboToolBox server (IFRC, Humanitarian, or self-hosted)
- Manage multiple forms simultaneously, each with its own module and cache TTL
- Per-form dashboard modules: upload/download via the web UI, no server restart needed
- **User groups**: partition forms by group — users only see the forms assigned to their group(s)
- **Group admins**: delegate member management and module uploads to a group-level admin
- **Multilingual UI**: French (default), English, Spanish, Arabic (RTL), Russian — switchable per session
- **Org branding**: set your organisation name, logo, and primary colour from the Settings page
- Email-based authentication, self-registration with admin approval, password reset
- Admin recovery via SSH management command (`init_admin`) — no email server needed
- File-based cache with configurable TTL per form
- CSV and XLSX export

---

## Architecture

```
kobodashboard/          Django project config
  __init__.py           App version (__version__)
  settings.py           Reads .env via python-decouple; i18n; whitenoise

kobo/                   KoboToolBox integration
  models.py             KoboConfig (singleton: server URL, API token, branding)
                        ConfiguredForm (one row per active form)
                        DashboardGroup (groups with members, admins, forms)
  api_client.py         requests wrapper for /api/v2/assets/ and /data/
  cache_helpers.py      File-based cache layer keyed by form UID

accounts/               Email-based login, registration, password reset
  backends.py           EmailBackend — authenticate by email not username
  context_processors.py is_power_user, is_group_admin, site_config,
                        language info — injected into all templates
  management/commands/
    init_admin.py       First-access / locked-out recovery command

dashboard/              UI views and Bootstrap 5 templates
  views.py              form_list, settings_view, coverage, module_dashboard,
                        submission_list, submission_detail, export_csv/xlsx,
                        module_download/upload, group_edit, my_group, aide

form_modules/           Dashboard module plugin system (not included — create your own)
  __init__.py           Registry + auto-discovery of *.py files
  base.py               FormModule base class

locale/                 Translation files (en, es, ar, ru)
  <lang>/LC_MESSAGES/django.po / django.mo
```

---

## Access control

Three roles:

| Role | How identified | Access |
|---|---|---|
| **Power user** (admin) | Email in `POWER_USER_EMAILS` (settings.py) | Everything |
| **Group admin** | Listed as admin of a `DashboardGroup` | Their group's forms + member management |
| **User** | Active account, member of ≥1 group | Their group's forms only |

Forms not assigned to any group are only visible to the power user.

---

## Module system

Each form type has a **module** — a Python file in `form_modules/` decorated with `@register('form-uid')`. Two patterns exist:

**Coverage-matrix modules**: implement `parse_structure` and `parse_submission_detail`. The dashboard shows an activity × country matrix with submission drill-down.

```python
from form_modules import register
from form_modules.base import FormModule

@register('your-form-uid-here')
class MyFormModule(FormModule):
    form_label = 'My Dashboard'
    FIELD_PATHS = { ... }
    EXPORT_HEADERS = [ ... ]

    def parse_structure(self, schema): ...
    def parse_submission_detail(self, sub, structure): ...
```

**Indicator-monitoring modules**: also implement `parse_submissions`. The dashboard shows summary charts, disaggregation breakdowns, and a data table.

```python
    def parse_submissions(self, submissions): ...
```

Modules are **auto-discovered** at startup and can be **uploaded/downloaded** from the Settings page.

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
# Edit .env: set SECRET_KEY, DEBUG=True, ALLOWED_HOSTS=localhost
```

### Run

```bash
source .venv/bin/activate
python3 manage.py migrate
python3 manage.py runserver
```

Open http://localhost:8000/ — on first run, create the admin account via:

```bash
python3 manage.py init_admin
```

This prints a one-time login link valid for 3 days. Open it, set a password, then log in.

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
| `EMAIL_HOST` | — | SMTP host (optional — password reset works without email via `init_admin`) |
| `EMAIL_PORT` | `587` | SMTP port |
| `EMAIL_HOST_USER` | — | SMTP username |
| `EMAIL_HOST_PASSWORD` | — | SMTP password |
| `EMAIL_USE_TLS` | `True` | Use TLS for SMTP |
| `DEFAULT_FROM_EMAIL` | — | From address for password reset emails |

---

## Production deployment

The reference deployment runs on an Ubuntu server alongside a Nextcloud snap. The Nextcloud snap owns ports 80/443, so Django runs behind a system nginx reverse proxy.

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
sudo certbot --nginx -d your.domain.example
sudo systemctl reload nginx

# 8. Create the first admin account
python3 manage.py init_admin
# Open the printed URL, set a password, log in.
```

### Update

```bash
bash /srv/kobodashboard/deploy/update.sh
```

### Admin recovery (locked out)

```bash
cd /srv/kobodashboard
source .venv/bin/activate
python3 manage.py init_admin
# Open the printed one-time link in a browser.
```

---

## Modules included

| Module | Form type | Description |
|---|---|---|
| `form_modules/dnh.py` | Coverage matrix | Do Not Harm checklist — activity × country matrix with risk drill-down |
| `form_modules/amopah3.py` | Indicator monitoring | AMOPAH III program — charts by country/result/period, disaggregation, data table, CSV/XLSX export |

---

## Licence

[GNU General Public Licence v3.0](LICENSE) — you may use, modify, and redistribute this software freely, but any derivative work must also be released under the GPL v3. You may not relicence it as proprietary software.
