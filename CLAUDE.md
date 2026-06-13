# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Django dashboard that pulls form submission data from a KoboToolBox server (default: https://kobo.ifrc.org) via the v2 REST API and displays it to authenticated users. KoboToolBox stores surveys as "assets"; each asset has a schema (question groups) and a data endpoint (submissions).

Currently deployed for the AMOPAH III humanitarian programme (IFRC/Red Cross), serving two form types:
- **AMOPAH III** — indicator monitoring with beneficiary disaggregation (age/sex, disability, displacement status)
- **Do Not Harm** — activity coverage matrix with risk identification

## Commands

```bash
# Activate the virtual environment first (required for all commands)
source .venv/bin/activate

# Apply migrations
python3 manage.py migrate

# Create the first admin user
python3 manage.py createsuperuser

# Run development server
python3 manage.py runserver

# Collect static files (production only)
python3 manage.py collectstatic --no-input
```

## Architecture

```
kobodashboard/          Django project config
  settings.py           Reads .env via python-decouple; whitenoise for static files
kobo/                   KoboToolBox integration
  models.py             KoboConfig (singleton) + ConfiguredForm (multi-form registry)
  api_client.py         requests-based wrapper for /api/v2/assets/ and /api/v2/assets/{uid}/data/
  cache_helpers.py      Django file-based cache layer keyed by asset UID
  program_structure.py  Parses XLSForm choices into results/activities/countries structure (DNH)
accounts/               Custom user system
  backends.py           EmailBackend — authenticate by email instead of username
  forms.py              RegistrationForm — self-registration with staff approval workflow
  models.py             UserProfile (full_name, country) linked OneToOne to User
dashboard/              UI views and Bootstrap 5 templates
  views.py              All dashboard views (see View reference below)
  urls.py               URL routing
form_modules/           Plugin system for form-specific logic
  __init__.py           Auto-discovery registry; @register('uid') decorator
  base.py               FormModule base class
  amopah3.py            AMOPAH III indicator module (registered to its Kobo UID)
  dnh.py                Do Not Harm module (registered to its Kobo UID)
```

## Key design decisions

**KoboConfig singleton**: `KoboConfig.get()` always returns the one config row (pk=1). Stores the server URL and API token. Deletion is a no-op — it cannot be removed.

**ConfiguredForm**: Multiple forms can be registered in the DB (`kobo/models.py`). Each has its own `cache_ttl_seconds`, `order`, and KoboToolBox `uid`. Staff manage these from `/dashboard/settings/`.

**Form module plugin system**: `form_modules/__init__.py` auto-discovers all `.py` files in the directory (except `__init__` and `base`) and imports them. Each file registers itself via `@register('kobo-asset-uid')`. `get_module(uid)` returns the registered instance or `None`. Two module types exist:
- Modules with `parse_submissions()` → routed to `amopah_dashboard` view (indicator monitoring)
- Modules without `parse_submissions()` → routed to `coverage` view (activity/risk matrix)

**Module upload**: Staff can upload a new `.py` module file via the settings UI (`/dashboard/settings/module-upload/<uid>/`). The file is written directly to `form_modules/`, which hot-reloads it in dev (gunicorn requires a restart in production). Only valid Python identifiers are accepted as filenames.

**Group navigation** (generic fallback view): KoboToolBox XLSForm surveys use `begin_group`/`end_group` rows in `content.survey`. `api_client.parse_groups()` walks this array and returns an ordered dict of `{group_key: {label, questions[]}}`. The dashboard renders one Bootstrap tab per group with full-page navigation.

**Caching**: `cache_helpers.get_cached(key, fetch_fn, ttl)` checks Django's file-based cache (`.cache/` dir) first. Cache keys:
- `kobo_schema_{uid}` — form schema
- `kobo_submissions_{uid}` — all submissions
- `kobo_structure_{uid}` — parsed program structure (from module)
- `kobo_asset_list` — asset list from KoboToolBox API

Cache is invalidated per-form by the Refresh button (`/dashboard/{uid}/refresh/`). TTL is per-form (`ConfiguredForm.cache_ttl_seconds`, default 300 s).

**User registration**: New users self-register (`/accounts/register/`) and are created with `is_active=False`. Staff approve/deactivate/delete from `/dashboard/users/`. Login is by email (not username) via `accounts.backends.EmailBackend`. Password reset is email-based.

**Export**: Both CSV (`StreamingHttpResponse`) and XLSX (`openpyxl`) exports exist. AMOPAH-style exports flatten one row per indicator-per-submission with full disaggregation columns. DNH-style exports flatten one row per risk-per-submission.

**Program structure** (DNH): `kobo/program_structure.py` parses XLSForm `choices` to extract the logical program hierarchy: results → activities → countries + applicable pairs. This is cached as `kobo_structure_{uid}`.

**Static files**: Served by WhiteNoise in both dev and production (`CompressedManifestStaticFilesStorage`).

## View reference

| URL pattern | View | Purpose |
|---|---|---|
| `/dashboard/` | `form_list` | Landing page; shows configured forms with cached sub count |
| `/dashboard/settings/` | `settings_view` | Staff: manage server config + add/remove forms |
| `/dashboard/settings/module-download/<uid>/` | `module_download` | Staff: download current module .py |
| `/dashboard/settings/module-upload/<uid>/` | `module_upload` | Staff: upload replacement module .py |
| `/dashboard/users/` | `user_list` | Staff: approve/deactivate/delete users |
| `/dashboard/<uid>/` | `coverage` | Primary form view — routes to amopah_dashboard or coverage matrix |
| `/dashboard/<uid>/submissions/` | `submission_list` | Filtered submission list (activity/country/responsible) |
| `/dashboard/<uid>/submission/<sub_id>/` | `submission_detail` | Single submission detail |
| `/dashboard/<uid>/refresh/` | `refresh_form` | Invalidate all caches for this form |
| `/dashboard/<uid>/export/csv/` | `export_csv` | CSV export |
| `/dashboard/<uid>/export/xlsx/` | `export_xlsx` | XLSX export |

`coverage` is the entry point for all form UIDs. If the module has `parse_submissions`, it delegates to `amopah_dashboard`. If there's no module at all, it falls back to `form_detail` (generic group-tab view).

## Adding a new form module

1. Create `form_modules/<slug>.py`
2. Subclass `FormModule` from `form_modules.base`
3. Decorate the class with `@register('<kobo-asset-uid>')`
4. Set `form_label`, `FIELD_PATHS`, `EXPORT_HEADERS`
5. Implement `parse_structure(schema)` → structure dict
6. Implement `parse_submission_detail(submission, structure)` → `{'activity': {...}, 'risks': [...]}`
7. For indicator-style forms: also implement `parse_submissions(submissions)` → list of parsed dicts
8. Add the form in the Settings UI (the module auto-loads; gunicorn needs restart in production)

## Environment

`.env` file (copy from `.env.example`):
```
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=kobodash.vmalep.eu,localhost
CSRF_TRUSTED_ORIGINS=https://kobodash.vmalep.eu

# Optional email (for password reset)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=user@example.com
EMAIL_HOST_PASSWORD=...
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@kobodash.vmalep.eu
```

## Deployment (on the Ubuntu home server, alongside Nextcloud snap)

> Development on laptop: just `python3 manage.py runserver` and open http://localhost:8000/

For production, copy the project to the Ubuntu server that hosts Nextcloud (nextcloud.vmalep.eu). The Nextcloud snap owns port 80/443 via its internal nginx, so Django runs on a separate port behind a system nginx reverse proxy:

1. Copy project to `/srv/kobodashboard/`
2. Create log directory: `sudo mkdir -p /var/log/kobodashboard && sudo chown www-data: /var/log/kobodashboard`
3. Install systemd service: `sudo cp deploy/kobodashboard.service /etc/systemd/system/ && sudo systemctl enable --now kobodashboard`
4. Install nginx config: `sudo cp deploy/nginx-kobodash.conf /etc/nginx/sites-available/kobodash && sudo ln -s /etc/nginx/sites-available/kobodash /etc/nginx/sites-enabled/`
5. Obtain TLS cert: `sudo certbot --nginx -d kobodash.vmalep.eu`
6. `sudo systemctl reload nginx`

`CSRF_TRUSTED_ORIGINS=https://kobodash.vmalep.eu` must be set in `.env` in production (not committed to git — add it manually after each pull).
