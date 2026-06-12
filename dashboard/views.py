import csv
import io
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

from kobo import api_client, cache_helpers
from kobo.models import KoboConfig, ConfiguredForm
from form_modules import get_module

PAGE_SIZE = 25
MODULES_DIR = Path(__file__).resolve().parent.parent / 'form_modules'


def _config():
    return KoboConfig.get()


def _get_form(uid):
    """Return ConfiguredForm for uid, or None."""
    try:
        return ConfiguredForm.objects.get(uid=uid)
    except ConfiguredForm.DoesNotExist:
        return None


def _load(uid):
    """Return (schema, submissions, structure, module) from cache."""
    config = _config()
    form = _get_form(uid)
    ttl = form.cache_ttl_seconds if form else 300

    schema = cache_helpers.get_cached(
        cache_helpers.schema_key(uid),
        lambda: api_client.get_schema(uid, config),
        ttl=ttl,
    )
    submissions = cache_helpers.get_cached(
        cache_helpers.submissions_key(uid),
        lambda: api_client.get_submissions(uid, config),
        ttl=ttl,
    )
    module = get_module(uid)
    if module is not None:
        structure = cache_helpers.get_cached(
            f'kobo_structure_{uid}',
            lambda: module.parse_structure(schema),
            ttl=ttl,
        )
    else:
        structure = {}
    return schema, submissions, structure, module


# ── Form list ──────────────────────────────────────────────────────────────────

@login_required
def form_list(request):
    forms = ConfiguredForm.objects.all()
    if not forms.exists():
        if request.user.is_staff:
            return redirect('/dashboard/settings/')
        return render(request, 'dashboard/no_form.html', {})

    form_cards = []
    for f in forms:
        module = get_module(f.uid)
        cached_subs = cache_helpers.get_if_cached(cache_helpers.submissions_key(f.uid))
        form_cards.append({
            'uid': f.uid,
            'name': f.name,
            'module_label': module.form_label if module else None,
            'sub_count': len(cached_subs) if cached_subs is not None else None,
        })

    return render(request, 'dashboard/form_list.html', {'form_cards': form_cards})


# ── Settings ───────────────────────────────────────────────────────────────────

@login_required
def settings_view(request):
    if not request.user.is_staff:
        return redirect('/dashboard/')

    config = _config()
    assets = []
    error = None
    success = None
    show_add_form = False

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'save_server':
            server_url = request.POST.get('server_url', '').strip().rstrip('/')
            api_token = request.POST.get('api_token', '').strip()
            if server_url:
                config.server_url = server_url
            if api_token:
                config.api_token = api_token
            config.save()
            cache_helpers.invalidate(cache_helpers.asset_list_key())
            success = 'Connexion enregistrée.'

        elif action == 'load_assets':
            server_url = request.POST.get('server_url', '').strip().rstrip('/')
            api_token = request.POST.get('api_token', '').strip()
            if server_url:
                config.server_url = server_url
            if api_token:
                config.api_token = api_token
            config.save()
            cache_helpers.invalidate(cache_helpers.asset_list_key())
            try:
                assets = api_client.list_assets(config)
                show_add_form = True
            except api_client.KoboAPIError as exc:
                error = str(exc)

        elif action == 'add_form':
            uid = request.POST.get('selected_form_uid', '').strip()
            name = request.POST.get('selected_form_name', '').strip()
            ttl = request.POST.get('cache_ttl_seconds', '300').strip()
            if uid and not ConfiguredForm.objects.filter(uid=uid).exists():
                ConfiguredForm.objects.create(
                    uid=uid,
                    name=name or uid,
                    cache_ttl_seconds=int(ttl) if ttl.isdigit() else 300,
                    order=ConfiguredForm.objects.count(),
                )
                success = f'Formulaire « {name} » ajouté.'
            elif uid:
                error = 'Ce formulaire est déjà configuré.'

        elif action == 'remove_form':
            uid = request.POST.get('form_uid', '').strip()
            ConfiguredForm.objects.filter(uid=uid).delete()
            for key in [cache_helpers.schema_key(uid),
                        cache_helpers.submissions_key(uid),
                        f'kobo_structure_{uid}']:
                cache_helpers.invalidate(key)
            success = 'Formulaire supprimé.'

        elif action == 'update_ttl':
            uid = request.POST.get('form_uid', '').strip()
            ttl = request.POST.get('cache_ttl_seconds', '300').strip()
            ConfiguredForm.objects.filter(uid=uid).update(
                cache_ttl_seconds=int(ttl) if ttl.isdigit() else 300
            )
            success = 'Durée du cache mise à jour.'

    configured_forms = []
    for f in ConfiguredForm.objects.all():
        module = get_module(f.uid)
        configured_forms.append({
            'uid': f.uid,
            'name': f.name,
            'cache_ttl_seconds': f.cache_ttl_seconds,
            'module_label': module.form_label if module else None,
            'has_module_file': module is not None,
        })

    return render(request, 'dashboard/settings.html', {
        'config': config,
        'configured_forms': configured_forms,
        'assets': assets,
        'show_add_form': show_add_form,
        'error': error,
        'success': success,
    })


# ── Module download / upload ───────────────────────────────────────────────────

@login_required
def module_download(request, uid):
    if not request.user.is_staff:
        return redirect('/dashboard/')
    module = get_module(uid)
    if module is None:
        return HttpResponse('Aucun module pour ce formulaire.', status=404)
    path = Path(module._source_file)
    return FileResponse(open(path, 'rb'), as_attachment=True, filename=path.name)


@login_required
def module_upload(request, uid):
    if not request.user.is_staff or request.method != 'POST':
        return redirect('/dashboard/settings/')

    uploaded = request.FILES.get('module_file')
    if not uploaded:
        return redirect('/dashboard/settings/')

    stem = Path(uploaded.name).stem
    if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', stem):
        return render(request, 'dashboard/settings.html',
                      {'error': 'Nom de fichier invalide (doit être un identifiant Python valide).',
                       'config': _config(), 'configured_forms': [], 'assets': [], 'show_add_form': False, 'success': None})

    dest = MODULES_DIR / f'{stem}.py'
    dest.write_bytes(uploaded.read())

    return render(request, 'dashboard/module_uploaded.html', {
        'filename': dest.name,
        'uid': uid,
    })


def _build_table_rows(filtered, f_result):
    """Return flat list of indicator rows for the data table."""
    rows = []
    for ps in filtered:
        for ind in ps['indicators']:
            if f_result and ind['result_key'] != f_result:
                continue
            rows.append({
                'country': ps['country_label'],
                'period': ps['period'],
                'reporter': ps['reporter'],
                'result': ind['result_label'],
                'code': ind['code'],
                'label': ind['label'],
                'total': ind['total'],
                'male': ind['age'].get('male_total', ''),
                'female': ind['age'].get('fem_total', ''),
                'disability': ind['disability'].get('with', ''),
                'pdi': ind['status'].get('pdi', ''),
            })
    return rows


# ── Generic form detail (fallback for forms with no module) ───────────────────

@login_required
def amopah_dashboard(request, uid):
    """Dashboard for AMOPAH III indicator monitoring form."""
    error = None
    chart_data = {}
    periods = []
    countries_used = []
    results_used = []
    parsed_all = []
    filtered = []
    total_beneficiaries = 0
    total_reports = 0

    f_country = request.GET.get('country', '')
    f_year = request.GET.get('year', '')
    f_quarter = request.GET.get('quarter', '')
    f_result = request.GET.get('result', '')

    try:
        schema, submissions, structure, module = _load(uid)
        if module is None or not hasattr(module, 'parse_submissions'):
            return form_detail(request, uid)

        parsed_all = module.parse_submissions(submissions)

        # Collect filter options from data
        periods_set = sorted({ps['period'] for ps in parsed_all if ps['period']})
        countries_used = sorted({ps['country'] for ps in parsed_all if ps['country']})
        results_used_set = set()
        for ps in parsed_all:
            for ind in ps['indicators']:
                results_used_set.add(ind['result_key'])
        results_used = [r for r in ['result1', 'result2', 'result3', 'result4']
                        if r in results_used_set]

        # Apply filters
        filtered = parsed_all
        if f_country:
            filtered = [ps for ps in filtered if ps['country'] == f_country]
        if f_year:
            filtered = [ps for ps in filtered if ps['year'] == f_year]
        if f_quarter:
            filtered = [ps for ps in filtered if ps['quarter'] == f_quarter]

        total_reports = len(filtered)

        # Build per-indicator aggregates for filtered set
        from form_modules.amopah3 import (
            COUNTRY_LABELS, RESULT_LABELS, INDICATOR_LABELS, aggregate
        )

        agg = aggregate(filtered)
        total_beneficiaries = sum(agg['by_country'].values())

        # Build Chart.js data: one chart per result, indicators on x-axis, countries stacked
        country_colors = {
            'burkina': '#c00000',
            'niger':   '#e97132',
            'mali':    '#156082',
            'burundi': '#196b24',
            'rdc':     '#7f7f7f',
        }
        country_list = [c for c in COUNTRY_LABELS if c in countries_used]
        if f_country:
            country_list = [f_country] if f_country in COUNTRY_LABELS else []

        # Group indicators by result
        from form_modules.amopah3 import RESULT_KEYS
        result_charts = []
        for rkey in RESULT_KEYS:
            if f_result and rkey != f_result:
                continue
            # Collect indicators that appear in this result in filtered data
            ind_codes = []
            for ps in filtered:
                for ind in ps['indicators']:
                    if ind['result_key'] == rkey and ind['code'] not in ind_codes:
                        ind_codes.append(ind['code'])

            if not ind_codes:
                continue

            ind_labels = [INDICATOR_LABELS.get(c, c) for c in ind_codes]
            datasets = []
            for country in country_list:
                data = []
                for code in ind_codes:
                    val = agg['by_indicator'].get(code, {}).get(country, 0)
                    data.append(val)
                datasets.append({
                    'label': COUNTRY_LABELS.get(country, country),
                    'data': data,
                    'backgroundColor': country_colors.get(country, '#999'),
                })

            result_charts.append({
                'result_key': rkey,
                'result_label': RESULT_LABELS.get(rkey, rkey),
                'indicator_labels': ind_labels,
                'indicator_codes': ind_codes,
                'datasets': datasets,
            })

        # Summary chart: total by country
        country_summary = {
            'labels': [COUNTRY_LABELS.get(c, c) for c in country_list],
            'data': [agg['by_country'].get(c, 0) for c in country_list],
            'colors': [country_colors.get(c, '#999') for c in country_list],
        }

        # Period trend chart
        period_labels = sorted({ps['period'] for ps in filtered if ps['period']})
        period_data = [agg['by_period'].get(p, 0) for p in period_labels]

        # Disaggregation chart: aggregate age/sex across all filtered indicators
        age_totals = {'male_0_5': 0, 'male_6_18': 0, 'male_19_49': 0, 'male_50p': 0,
                      'fem_0_5': 0, 'fem_6_18': 0, 'fem_19_49': 0, 'fem_50p': 0}
        disability_totals = {'with': 0, 'without': 0}
        status_totals = {'pdi': 0, 'host': 0, 'refugee': 0, 'returnees': 0,
                         'stateless': 0, 'other': 0}
        has_disagg = False
        for ps in filtered:
            for ind in ps['indicators']:
                if f_result and ind['result_key'] != f_result:
                    continue
                if ind['age']:
                    has_disagg = True
                    for k in age_totals:
                        age_totals[k] += ind['age'].get(k, 0)
                if ind['disability']:
                    for k in disability_totals:
                        disability_totals[k] += ind['disability'].get(k, 0)
                if ind['status']:
                    for k in status_totals:
                        status_totals[k] += ind['status'].get(k, 0)

        disagg_chart = None
        if has_disagg:
            age_labels = ['0–5 H', '6–18 H', '19–49 H', '50+ H',
                          '0–5 F', '6–18 F', '19–49 F', '50+ F']
            age_data = [age_totals[k] for k in age_totals]
            age_colors = (['#156082'] * 4) + (['#c00000'] * 4)

            status_labels = ['PDI', 'Hôte', 'Réfugié', 'Rapatrié', 'Migrant', 'Autre']
            status_data = [status_totals[k] for k in status_totals]

            disagg_chart = {
                'age': {'labels': age_labels, 'data': age_data, 'colors': age_colors},
                'disability': {
                    'labels': ['Avec handicap', 'Sans handicap'],
                    'data': [disability_totals['with'], disability_totals['without']],
                    'colors': ['#e97132', '#196b24'],
                },
                'status': {'labels': status_labels, 'data': status_data},
            }

        chart_data = {
            'country_summary': country_summary,
            'period_trend': {'labels': period_labels, 'data': period_data},
            'result_charts': result_charts,
            'disagg': disagg_chart,
        }

    except api_client.KoboAPIError as exc:
        error = str(exc)

    from form_modules.amopah3 import COUNTRY_LABELS, RESULT_LABELS
    import json as _json

    return render(request, 'dashboard/amopah_dashboard.html', {
        'uid': uid,
        'form_label': 'AMOPAH III — Suivi des indicateurs',
        'error': error,
        'total_beneficiaries': total_beneficiaries,
        'total_reports': total_reports,
        'countries_used': countries_used,
        'results_used': results_used,
        'periods': sorted({ps['period'] for ps in parsed_all if ps['period']}),
        'years': sorted({ps['year'] for ps in parsed_all if ps['year']}),
        'quarters': ['Q1', 'Q2', 'Q3', 'Q4'],
        'f_country': f_country,
        'f_year': f_year,
        'f_quarter': f_quarter,
        'f_result': f_result,
        'country_labels': COUNTRY_LABELS,
        'result_labels': RESULT_LABELS,
        'chart_data_json': _json.dumps(chart_data),
        'table_rows': _build_table_rows(filtered, f_result),
    })


@login_required
def form_detail(request, uid):
    error = None
    tabs = []
    columns = []
    page_obj = None
    form_name = uid
    total_submissions = 0
    active_group = ''

    try:
        config = _config()
        schema = cache_helpers.get_cached(
            cache_helpers.schema_key(uid),
            lambda: api_client.get_schema(uid, config),
        )
        submissions = cache_helpers.get_cached(
            cache_helpers.submissions_key(uid),
            lambda: api_client.get_submissions(uid, config),
        )
        form_name = schema.get('name', uid)
        total_submissions = len(submissions)

        group_order, groups = api_client.parse_groups(schema)
        question_labels = api_client.get_question_labels(schema)

        tabs = [{'key': k, 'label': groups[k]['label']} for k in group_order]
        active_group = request.GET.get('group', group_order[0] if group_order else '')

        if active_group and active_group in groups:
            questions = groups[active_group]['questions']
            columns = [{'label': question_labels.get(q, q)} for q in questions]
            rows = [
                {'id': sub.get('_id', ''), 'values': [sub.get(q, '') for q in questions]}
                for sub in submissions
            ]
            paginator = Paginator(rows, PAGE_SIZE)
            page_obj = paginator.get_page(request.GET.get('page'))

    except api_client.KoboAPIError as exc:
        error = str(exc)

    return render(request, 'dashboard/form_detail.html', {
        'uid': uid,
        'form_name': form_name,
        'total_submissions': total_submissions,
        'tabs': tabs,
        'active_group': active_group,
        'columns': columns,
        'page_obj': page_obj,
        'error': error,
    })


# ── Coverage matrix ────────────────────────────────────────────────────────────

@login_required
def coverage(request, uid):
    error = None
    structure = {}
    coverage_data = {}
    responsibles = []
    module = None

    f_country = request.GET.get('country', '')
    f_result = request.GET.get('result', '')
    f_activity = request.GET.get('activity', '')
    f_responsible = request.GET.get('responsible', '')

    try:
        schema, submissions, structure, module = _load(uid)
    except api_client.KoboAPIError as exc:
        error = str(exc)

    if module is None and not error:
        return form_detail(request, uid)

    # Route modules that have their own dashboard view
    if module is not None and hasattr(module, 'parse_submissions') and not error:
        return amopah_dashboard(request, uid)

    if not error:
        fp = module.FIELD_PATHS
        resp_by_country = {}
        for sub in submissions:
            act_code = sub.get(fp['activity_code'], '')
            country = sub.get(fp['country'], '')
            main = module.extract_main_activity(act_code)
            responsible = sub.get(fp['activity_responsible'], '').strip()
            if main and country:
                coverage_data[(main, country)] = coverage_data.get((main, country), 0) + 1
            if country and responsible:
                resp_by_country.setdefault(country, set()).add(responsible)

        if f_country:
            resp_set = resp_by_country.get(f_country, set())
        else:
            resp_set = {name for names in resp_by_country.values() for name in names}
        responsibles = sorted(resp_set)

    applicable = structure.get('applicable', set())
    results = structure.get('results', [])
    if f_result:
        results = [r for r in results if r['code'] == f_result]
    if f_country:
        results = [
            {**r, 'activities': [
                a for a in r['activities']
                if (a['code'], f_country) in applicable
            ]}
            for r in results
        ]
        results = [r for r in results if r['activities']]

    countries = structure.get('countries', [])
    display_countries = [c for c in countries if not f_country or c['code'] == f_country]

    responsible_keys = set()
    if f_responsible and not error:
        _, submissions_raw, _, _ = _load(uid)
        fp = module.FIELD_PATHS
        for sub in submissions_raw:
            act_code = sub.get(fp['activity_code'], '')
            country = sub.get(fp['country'], '')
            responsible = sub.get(fp['activity_responsible'], '').strip()
            main = module.extract_main_activity(act_code)
            if responsible == f_responsible and main and country:
                responsible_keys.add((main, country))

    form_name = uid
    try:
        form_name = cache_helpers.get_cached(
            cache_helpers.schema_key(uid),
            lambda: api_client.get_schema(uid, _config()),
        ).get('name', uid)
    except Exception:
        pass

    matrix = []
    for result in results:
        rows = []
        for activity in result['activities']:
            cells = []
            for c in display_countries:
                is_applicable = (activity['code'], c['code']) in applicable
                count = coverage_data.get((activity['code'], c['code']), 0)
                responsible_match = (
                    not f_responsible
                    or (activity['code'], c['code']) in responsible_keys
                )
                sub_url = (
                    f'/dashboard/{uid}/submissions/'
                    f'?activity={activity["code"]}&country={c["code"]}'
                    + (f'&responsible={f_responsible}' if f_responsible else '')
                )
                cells.append({
                    'country': c['code'],
                    'applicable': is_applicable,
                    'count': count,
                    'responsible_match': responsible_match,
                    'sub_url': sub_url,
                })
            rows.append({'code': activity['code'], 'label': activity['label'], 'cells': cells})
        matrix.append({'result': result, 'rows': rows})

    return render(request, 'dashboard/coverage.html', {
        'uid': uid,
        'form_name': form_name,
        'form_label': module.form_label if module else '',
        'matrix': matrix,
        'all_results': structure.get('results', []),
        'countries': countries,
        'display_countries': display_countries,
        'responsibles': responsibles,
        'f_country': f_country,
        'f_result': f_result,
        'f_activity': f_activity,
        'f_responsible': f_responsible,
        'error': error,
    })


# ── Submission list ─────────────────────────────────────────────────────────────

@login_required
def submission_list(request, uid):
    error = None
    parsed_submissions = []
    structure = {}

    f_country = request.GET.get('country', '')
    f_activity = request.GET.get('activity', '')
    f_responsible = request.GET.get('responsible', '')

    try:
        schema, submissions, structure, module = _load(uid)
        if module is None:
            return redirect(f'/dashboard/{uid}/')

        fp = module.FIELD_PATHS
        for sub in submissions:
            act_code = sub.get(fp['activity_code'], '')
            country = sub.get(fp['country'], '')
            main = module.extract_main_activity(act_code)
            responsible = sub.get(fp['activity_responsible'], '').strip()

            if f_activity and main != f_activity:
                continue
            if f_country and country != f_country:
                continue
            if f_responsible and responsible != f_responsible:
                continue

            parsed_submissions.append(module.parse_submission_detail(sub, structure))

    except api_client.KoboAPIError as exc:
        error = str(exc)

    paginator = Paginator(parsed_submissions, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))

    activity_label = ''
    if f_activity:
        activity_label = structure.get('activity_labels', {}).get(f_activity, f_activity)

    return render(request, 'dashboard/submission_list.html', {
        'uid': uid,
        'page_obj': page_obj,
        'total': len(parsed_submissions),
        'f_country': f_country,
        'f_activity': f_activity,
        'f_responsible': f_responsible,
        'activity_label': activity_label,
        'country_label': structure.get('country_labels', {}).get(f_country, f_country),
        'error': error,
    })


# ── Submission detail ───────────────────────────────────────────────────────────

@login_required
def submission_detail(request, uid, sub_id):
    error = None
    parsed = None

    try:
        schema, submissions, structure, module = _load(uid)
        if module is None:
            return redirect(f'/dashboard/{uid}/')

        raw = next((s for s in submissions if s.get('_id') == sub_id), None)
        if raw is None:
            error = f'Submission #{sub_id} not found.'
        else:
            parsed = module.parse_submission_detail(raw, structure)
    except api_client.KoboAPIError as exc:
        error = str(exc)

    back_url = request.GET.get('back', f'/dashboard/{uid}/')

    return render(request, 'dashboard/submission_detail.html', {
        'uid': uid,
        'parsed': parsed,
        'back_url': back_url,
        'error': error,
    })


# ── Refresh ────────────────────────────────────────────────────────────────────

@login_required
def refresh_form(request, uid):
    cache_helpers.invalidate(cache_helpers.schema_key(uid))
    cache_helpers.invalidate(cache_helpers.submissions_key(uid))
    cache_helpers.invalidate(f'kobo_structure_{uid}')
    return redirect(request.GET.get('next', f'/dashboard/{uid}/'))


# ── Exports ────────────────────────────────────────────────────────────────────

class _Echo:
    def write(self, value):
        return value


def _amopah_csv_rows(writer, submissions, module):
    yield writer.writerow(module.EXPORT_HEADERS)
    i = 1
    for sub in submissions:
        ps = module.parse_submissions([sub])[0]
        if not ps['indicators']:
            yield writer.writerow([
                i, ps['country_label'], ps['year'], ps['quarter'], ps['reporter'],
                '', '', '', 0,
                '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '',
            ])
            i += 1
        else:
            for ind in ps['indicators']:
                age = ind['age']
                dis = ind['disability']
                sta = ind['status']
                yield writer.writerow([
                    i, ps['country_label'], ps['year'], ps['quarter'], ps['reporter'],
                    ind['result_label'], ind['code'], ind['label'], ind['total'],
                    age.get('male_total', ''), age.get('fem_total', ''),
                    age.get('male_0_5', ''), age.get('male_6_18', ''),
                    age.get('male_19_49', ''), age.get('male_50p', ''),
                    age.get('fem_0_5', ''), age.get('fem_6_18', ''),
                    age.get('fem_19_49', ''), age.get('fem_50p', ''),
                    dis.get('with', ''), dis.get('without', ''),
                    sta.get('pdi', ''), sta.get('host', ''), sta.get('refugee', ''),
                    sta.get('returnees', ''), sta.get('stateless', ''), sta.get('other', ''),
                ])
                i += 1


@login_required
def export_csv(request, uid):
    try:
        schema, submissions, structure, module = _load(uid)
    except api_client.KoboAPIError as exc:
        return HttpResponse(f'API error: {exc}', status=502)

    if module is None:
        return HttpResponse('Export non disponible sans module de formulaire.', status=400)

    pseudo_buffer = _Echo()
    writer = csv.writer(pseudo_buffer)

    # AMOPAH-style export
    if hasattr(module, 'parse_submissions'):
        response = StreamingHttpResponse(
            _amopah_csv_rows(writer, submissions, module),
            content_type='text/csv; charset=utf-8-sig',
        )
        response['Content-Disposition'] = f'attachment; filename="{uid}_donnees.csv"'
        return response

    def rows():
        yield writer.writerow(module.EXPORT_HEADERS)
        i = 1
        for sub in submissions:
            p = module.parse_submission_detail(sub, structure)
            act = p['activity']
            if not p['risks']:
                yield writer.writerow([
                    i, act['country_label'], act['activity_location'],
                    act['activity_code'], act['activity_label'],
                    act['activity_responsible'], act['start_date'], act['end_date'],
                    '', '', '',
                ])
                i += 1
            else:
                for risk in p['risks']:
                    yield writer.writerow([
                        i, act['country_label'], act['activity_location'],
                        act['activity_code'], act['activity_label'],
                        act['activity_responsible'], act['start_date'], act['end_date'],
                        risk['category_label'], risk['description'],
                        ' | '.join(risk['measures']),
                    ])
                    i += 1

    response = StreamingHttpResponse(rows(), content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{uid}_donnees.csv"'
    return response


def _amopah_xlsx(submissions, module):
    """Build openpyxl Workbook for AMOPAH export."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Données'

    header_fill = PatternFill('solid', fgColor='C00000')
    ws.append(module.EXPORT_HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = header_fill
        cell.alignment = Alignment(wrap_text=True)

    i = 1
    for sub in submissions:
        ps = module.parse_submissions([sub])[0]
        if not ps['indicators']:
            ws.append([i, ps['country_label'], ps['year'], ps['quarter'], ps['reporter'],
                       '', '', '', 0, *([''] * 18)])
            i += 1
        else:
            for ind in ps['indicators']:
                age = ind['age']
                dis = ind['disability']
                sta = ind['status']
                ws.append([
                    i, ps['country_label'], ps['year'], ps['quarter'], ps['reporter'],
                    ind['result_label'], ind['code'], ind['label'], ind['total'],
                    age.get('male_total', ''), age.get('fem_total', ''),
                    age.get('male_0_5', ''), age.get('male_6_18', ''),
                    age.get('male_19_49', ''), age.get('male_50p', ''),
                    age.get('fem_0_5', ''), age.get('fem_6_18', ''),
                    age.get('fem_19_49', ''), age.get('fem_50p', ''),
                    dis.get('with', ''), dis.get('without', ''),
                    sta.get('pdi', ''), sta.get('host', ''), sta.get('refugee', ''),
                    sta.get('returnees', ''), sta.get('stateless', ''), sta.get('other', ''),
                ])
                i += 1

    for col in ws.columns:
        max_len = max((len(str(c.value or '')) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)
    return wb


@login_required
def export_xlsx(request, uid):
    try:
        schema, submissions, structure, module = _load(uid)
    except api_client.KoboAPIError as exc:
        return HttpResponse(f'API error: {exc}', status=502)

    if module is None:
        return HttpResponse('Export non disponible sans module de formulaire.', status=400)

    # AMOPAH-style export
    if hasattr(module, 'parse_submissions'):
        wb = _amopah_xlsx(submissions, module)
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{uid}_donnees.xlsx"'
        return response

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Données'

    ws.append(module.EXPORT_HEADERS)
    header_fill = PatternFill('solid', fgColor='C00000')
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = header_fill
        cell.alignment = Alignment(wrap_text=True)

    i = 1
    for sub in submissions:
        p = module.parse_submission_detail(sub, structure)
        act = p['activity']
        if not p['risks']:
            ws.append([
                i, act['country_label'], act['activity_location'],
                act['activity_code'], act['activity_label'],
                act['activity_responsible'], act['start_date'], act['end_date'],
                '', '', '',
            ])
            i += 1
        else:
            for risk in p['risks']:
                ws.append([
                    i, act['country_label'], act['activity_location'],
                    act['activity_code'], act['activity_label'],
                    act['activity_responsible'], act['start_date'], act['end_date'],
                    risk['category_label'], risk['description'],
                    '\n'.join(risk['measures']),
                ])
                i += 1

    for col in ws.columns:
        max_len = max((len(str(c.value or '')) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{uid}_donnees.xlsx"'
    return response


# ── User management (staff only) ───────────────────────────────────────────────

def _staff_required(view_fn):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect('/dashboard/')
        return view_fn(request, *args, **kwargs)
    wrapper.__name__ = view_fn.__name__
    return wrapper


@_staff_required
def user_list(request):
    User = get_user_model()
    pending = User.objects.filter(is_active=False).select_related('profile').order_by('date_joined')
    active = User.objects.filter(is_active=True, is_superuser=False).select_related('profile').order_by('date_joined')
    return render(request, 'dashboard/user_list.html', {
        'pending': pending,
        'active': active,
    })


@_staff_required
def user_activate(request, user_id):
    if request.method == 'POST':
        User = get_user_model()
        user = get_object_or_404(User, pk=user_id)
        user.is_active = True
        user.save()
    return redirect('/dashboard/users/')


@_staff_required
def user_deactivate(request, user_id):
    if request.method == 'POST':
        User = get_user_model()
        user = get_object_or_404(User, pk=user_id)
        if user != request.user:
            user.is_active = False
            user.save()
    return redirect('/dashboard/users/')


@_staff_required
def user_delete(request, user_id):
    if request.method == 'POST':
        User = get_user_model()
        user = get_object_or_404(User, pk=user_id)
        if user != request.user:
            user.delete()
    return redirect('/dashboard/users/')
