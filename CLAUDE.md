# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Django dashboard (v1.0, GPL v3) that pulls form submission data from a KoboToolBox server via the v2 REST API and displays it to authenticated users. Generic: any KoboToolBox server, any number of forms, each with its own dashboard module.

## Commands

```bash
source .venv/bin/activate          # required for all commands

python3 manage.py migrate
python3 manage.py runserver
python3 manage.py collectstatic --no-input   # production only
python3 manage.py compilemessages            # after editing .po files
python3 manage.py init_admin                 # first-run or locked-out recovery
```

## Architecture

```
kobodashboard/
  __init__.py           __version__ = '1.0'
  settings.py           .env via python-decouple; i18n; whitenoise; POWER_USER_EMAILS
  urls.py               includes i18n/ for language switcher

kobo/
  models.py             KoboConfig (singleton: server, token, org_name, logo, brand_color)
                        ConfiguredForm (one row per active form)
                        DashboardGroup (groups: members M2M, admins M2M, forms M2M)
  api_client.py         requests wrapper for /api/v2/assets/ and /data/
  cache_helpers.py      File-based cache keyed by form UID

accounts/
  backends.py           EmailBackend — login by email not username
  context_processors.py user_roles: is_power_user, is_group_admin, site_config,
                        current_lang, current_lang_name, all_languages, app_version
  management/commands/init_admin.py   SSH recovery — prints one-time login URL

dashboard/
  views.py              All views (see View reference)
  urls.py               URL routing
  static/dashboard/favicon.svg
  templates/dashboard/base.html     Bootstrap 5, RTL, i18n, responsive navbar

form_modules/           Not included in git — create your own per-form modules
  __init__.py           Registry + auto-discovery of *.py files
  base.py               FormModule base class

locale/                 Translation files (en, es, ar, ru) — fr is default
  <lang>/LC_MESSAGES/django.po / django.mo
```

## Key design decisions

**Roles**: Three tiers defined in `settings.py` and `accounts/context_processors.py`:
- *Power user*: email in `POWER_USER_EMAILS` — full access to everything
- *Group admin*: admin of ≥1 `DashboardGroup` — manages their group's members and module uploads
- *User*: active account, member of ≥1 group — sees only their groups' forms

**KoboConfig singleton**: `KoboConfig.get()` always returns pk=1. Stores server URL, API token, `org_name`, `logo` (FileField), `brand_color` (hex). Deletion is a no-op. The context processor wraps it in try/except so a missing DB column silently returns None — but direct `KoboConfig.get()` in views will raise a 500 if migrations are missing.

**Branding**: `brand_color` overrides Bootstrap danger classes via a `<style>` block in `base.html`. Logo and org name displayed in navbar center (desktop only — hidden on mobile). "Your logo here" dashed placeholder shown when no logo set. Org name appears next to logo if both are set.

**i18n**: `LocaleMiddleware` + `{% trans %}` tags + `.po`/`.mo` files. Language switcher in navbar posts to `{% url 'set_language' %}`. Arabic triggers `dir="rtl"` and Bootstrap RTL CSS.

**Form module plugin system**: `form_modules/__init__.py` auto-discovers all `.py` files. `@register('kobo-uid')` decorator links a class to a form UID. Two patterns:
- Has `parse_submissions()` → `module_dashboard` view (indicator charts + disaggregation)
- No `parse_submissions()` → `coverage` view (activity × country matrix)
- No module at all → `form_detail` (generic group/tab view)

**Caching**: `cache_helpers.get_cached(key, fetch_fn, ttl)` uses Django file-based cache (`.cache/`). Keys: `kobo_schema_{uid}`, `kobo_submissions_{uid}`, `kobo_structure_{uid}`, `kobo_asset_list`. Invalidated by Refresh button. TTL per form (`ConfiguredForm.cache_ttl_seconds`, default 300 s).

**Static files**: WhiteNoise `CompressedManifestStaticFilesStorage`. App static files in `dashboard/static/dashboard/`. Always run `collectstatic` after adding new static files in production.

**Export**: CSV (`StreamingHttpResponse`) and XLSX (`openpyxl`). Indicator modules: one row per indicator per submission with disaggregation columns. Coverage-matrix modules: one row per risk per submission.

## View reference

| URL | View | Purpose |
|---|---|---|
| `/dashboard/` | `form_list` | Landing; shows accessible forms |
| `/dashboard/manual/` | `manual` | Help page (mode d'emploi) |
| `/dashboard/settings/` | `settings_view` | Power user: server config, forms, groups, branding |
| `/dashboard/settings/module-download/<uid>/` | `module_download` | Download module .py |
| `/dashboard/settings/module-upload/<uid>/` | `module_upload` | Upload module .py |
| `/dashboard/users/` | `user_list` | Power user: approve/deactivate/delete users |
| `/dashboard/groups/<id>/` | `group_edit` | Power user: edit group members/forms/admins |
| `/dashboard/my-group/` | `my_group` | Group admin: manage their group |
| `/dashboard/<uid>/` | `coverage` | Form entry point — routes by module type |
| `/dashboard/<uid>/submissions/` | `submission_list` | Filtered submission list |
| `/dashboard/<uid>/submission/<id>/` | `submission_detail` | Single submission |
| `/dashboard/<uid>/refresh/` | `refresh_form` | Invalidate caches |
| `/dashboard/<uid>/export/csv/` | `export_csv` | CSV export |
| `/dashboard/<uid>/export/xlsx/` | `export_xlsx` | XLSX export |

## Adding a new form module

1. Create `form_modules/<slug>.py`, subclass `FormModule`, decorate with `@register('<uid>')`
2. Set `form_label`, `FIELD_PATHS`, `EXPORT_HEADERS`
3. Implement `parse_structure(schema)` and `parse_submission_detail(submission, structure)`
4. For indicator-style: also implement `parse_submissions(submissions)`
5. Add the form in Settings UI (gunicorn restart required in production)

## Environment (`.env`)

```
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=your.domain.example,localhost
CSRF_TRUSTED_ORIGINS=https://your.domain.example   # required in production, not in git

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=...  EMAIL_PORT=587  EMAIL_HOST_USER=...  EMAIL_HOST_PASSWORD=...
EMAIL_USE_TLS=True  DEFAULT_FROM_EMAIL=noreply@your.domain.example
```

## Deployment

**Always use the deploy script** — running steps manually risks forgetting `migrate` (causes silent 500s):

```bash
bash /srv/kobodashboard/deploy/update.sh
# runs: git pull → migrate → collectstatic → systemctl restart kobodashboard
```

Django runs on port 8001 behind a system nginx reverse proxy. See `deploy/` for service and nginx configs.

Admin recovery (SSH to server):
```bash
cd /srv/kobodashboard && source .venv/bin/activate && python3 manage.py init_admin
```

**Debugging 500s in production**: gunicorn error log may not show Django tracebacks for DB errors. Check `python3 manage.py showmigrations` first — unapplied migrations are the most common cause.
