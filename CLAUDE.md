# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Django dashboard that pulls form submission data from a KoboToolBox server (default: https://kobo.ifrc.org) via the v2 REST API and displays it to authenticated users. KoboToolBox stores surveys as "assets"; each asset has a schema (question groups) and a data endpoint (submissions).

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
kobodashboard/   Django project config (settings.py reads .env via python-decouple)
kobo/            KoboToolBox integration
  models.py      KoboConfig — singleton storing server URL, API token, cache TTL
  api_client.py  requests-based wrapper for /api/v2/assets/ and /api/v2/assets/{uid}/data/
  cache_helpers.py  Django file-based cache layer keyed by asset UID
accounts/        Login/logout (Django built-in views, no OAuth)
dashboard/       UI views and Bootstrap 5 templates
  views.py       form_list, form_detail, refresh_form, export_csv, export_xlsx
```

## Key design decisions

**KoboConfig singleton**: `KoboConfig.get()` always returns the one config row (pk=1). The admin sets the API token and server URL there. Views fail gracefully when no token is set.

**Group navigation**: KoboToolBox XLSForm surveys use `begin_group`/`end_group` rows in `content.survey`. `api_client.parse_groups()` walks this array and returns an ordered dict of `{group_key: {label, questions[]}}`. The dashboard renders one Bootstrap tab per group; switching tabs is a full page navigation (no JS required).

**Caching**: `cache_helpers.get_cached(key, fetch_fn)` checks Django's file-based cache first. Cache is invalidated per-form by the Refresh button (`/dashboard/{uid}/refresh/`). TTL is configurable in `KoboConfig.cache_ttl_seconds` (default 300 s).

**Export**: CSV uses `StreamingHttpResponse` with `csv.writer`. XLSX uses `openpyxl` with one worksheet per group. Both export the full unfiltered dataset from cache.

## Environment

`.env` file (copy from `.env.example`):
```
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=kobodash.vmalep.eu,localhost
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

Add `CSRF_TRUSTED_ORIGINS=https://kobodash.vmalep.eu` to `.env` in production.
