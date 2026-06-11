import csv
import io
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

from kobo import api_client, cache_helpers
from kobo.models import KoboConfig
from kobo.program_structure import (
    parse_program_structure,
    extract_main_activity,
    extract_result,
    COUNTRY_LABELS,
)

PAGE_SIZE = 25


def _config():
    return KoboConfig.get()


def _load(uid):
    """Return (schema, submissions, program_structure) from cache."""
    config = _config()
    schema = cache_helpers.get_cached(
        cache_helpers.schema_key(uid),
        lambda: api_client.get_schema(uid, config),
    )
    submissions = cache_helpers.get_cached(
        cache_helpers.submissions_key(uid),
        lambda: api_client.get_submissions(uid, config),
    )
    structure = cache_helpers.get_cached(
        f'kobo_structure_{uid}',
        lambda: parse_program_structure(schema),
    )
    return schema, submissions, structure


# ── Form list / entry point ────────────────────────────────────────────────────

@login_required
def form_list(request):
    config = _config()
    if config.selected_form_uid:
        return redirect(f'/dashboard/{config.selected_form_uid}/')
    # No form selected yet — send staff to settings, others to a placeholder
    if request.user.is_staff:
        return redirect('/dashboard/settings/')
    return render(request, 'dashboard/no_form.html', {})


# ── Settings ───────────────────────────────────────────────────────────────────

@login_required
def settings_view(request):
    if not request.user.is_staff:
        return redirect('/dashboard/')

    config = _config()
    assets = []
    error = None
    success = False

    if request.method == 'POST':
        action = request.POST.get('action', '')
        server_url = request.POST.get('server_url', '').strip().rstrip('/')
        api_token = request.POST.get('api_token', '').strip()

        # Always persist server + token on any POST
        config.server_url = server_url or config.server_url
        if api_token:
            config.api_token = api_token
        config.save()
        cache_helpers.invalidate(cache_helpers.asset_list_key())

        if action == 'load':
            # Just reload the form list
            try:
                assets = api_client.list_assets(config)
            except api_client.KoboAPIError as exc:
                error = str(exc)

        elif action == 'save':
            selected_uid = request.POST.get('selected_form_uid', '').strip()
            selected_name = request.POST.get('selected_form_name', '').strip()
            cache_ttl = request.POST.get('cache_ttl_seconds', '300').strip()
            config.selected_form_uid = selected_uid
            config.selected_form_name = selected_name
            try:
                config.cache_ttl_seconds = int(cache_ttl)
            except ValueError:
                pass
            config.save()
            # Clear caches for old and new form
            for key in [
                cache_helpers.asset_list_key(),
                cache_helpers.schema_key(selected_uid),
                cache_helpers.submissions_key(selected_uid),
                f'kobo_structure_{selected_uid}',
            ]:
                cache_helpers.invalidate(key)
            if selected_uid:
                return redirect(f'/dashboard/{selected_uid}/')
            success = True
            try:
                assets = api_client.list_assets(config)
            except api_client.KoboAPIError as exc:
                error = str(exc)
    else:
        if config.api_token:
            try:
                assets = cache_helpers.get_cached(
                    cache_helpers.asset_list_key(),
                    lambda: api_client.list_assets(config),
                )
            except api_client.KoboAPIError as exc:
                error = str(exc)

    return render(request, 'dashboard/settings.html', {
        'config': config,
        'assets': assets,
        'error': error,
        'success': success,
    })


# ── Coverage matrix ────────────────────────────────────────────────────────────

@login_required
def coverage(request, uid):
    error = None
    structure = {}
    coverage_data = {}   # (main_code, country_code) → submission count
    responsibles = []    # unique responsible names for the filter

    # Active filters
    f_country = request.GET.get('country', '')
    f_result = request.GET.get('result', '')
    f_activity = request.GET.get('activity', '')
    f_responsible = request.GET.get('responsible', '')

    try:
        schema, submissions, structure = _load(uid)

        # Build coverage counts and collect responsible names
        resp_by_country = {}  # country_code → {name, ...}
        for sub in submissions:
            act_code = sub.get('group_ActivityDetails/activity_code', '')
            country = sub.get('group_ActivityDetails/country', '')
            main = extract_main_activity(act_code)
            responsible = sub.get('group_ActivityDetails/activity_responsible', '').strip()
            if main and country:
                key = (main, country)
                coverage_data[key] = coverage_data.get(key, 0) + 1
            if country and responsible:
                resp_by_country.setdefault(country, set()).add(responsible)

        # Responsibles for selected country (or all if no country filter)
        if f_country:
            resp_set = resp_by_country.get(f_country, set())
        else:
            resp_set = {name for names in resp_by_country.values() for name in names}
        responsibles = sorted(resp_set)

    except api_client.KoboAPIError as exc:
        error = str(exc)

    # Filter results/activities for display
    applicable = structure.get('applicable', set())
    results = structure.get('results', [])
    if f_result:
        results = [r for r in results if r['code'] == f_result]
    # When a country is selected, hide activities not applicable in that country
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

    # If a responsible filter is active, compute which (main, country) pairs match
    responsible_keys = set()
    if f_responsible and not error:
        _, submissions_raw, _ = _load(uid)
        for sub in submissions_raw:
            act_code = sub.get('group_ActivityDetails/activity_code', '')
            country = sub.get('group_ActivityDetails/country', '')
            responsible = sub.get('group_ActivityDetails/activity_responsible', '').strip()
            main = extract_main_activity(act_code)
            if responsible == f_responsible and main and country:
                responsible_keys.add((main, country))

    form_name = structure.get('form_name', uid)
    if not error:
        try:
            form_name = cache_helpers.get_cached(
                cache_helpers.schema_key(uid),
                lambda: api_client.get_schema(uid, _config()),
            ).get('name', uid)
        except Exception:
            pass

    # Build template-friendly matrix: list of {result, rows: [{code, label, cells: [...]}]}
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
    f_activity = request.GET.get('activity', '')   # main code e.g. R1A1
    f_responsible = request.GET.get('responsible', '')

    try:
        schema, submissions, structure = _load(uid)
        risk_labels = structure.get('risk_labels', {})
        activity_specific_labels = structure.get('activity_specific_labels', {})
        country_labels = structure.get('country_labels', {})

        for sub in submissions:
            act_code = sub.get('group_ActivityDetails/activity_code', '')
            country = sub.get('group_ActivityDetails/country', '')
            main = extract_main_activity(act_code)
            responsible = sub.get('group_ActivityDetails/activity_responsible', '').strip()

            if f_activity and main != f_activity:
                continue
            if f_country and country != f_country:
                continue
            if f_responsible and responsible != f_responsible:
                continue

            parsed_submissions.append(
                api_client.parse_submission_detail(
                    sub, risk_labels, activity_specific_labels, country_labels
                )
            )

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
        'country_label': COUNTRY_LABELS.get(f_country, f_country),
        'error': error,
    })


# ── Submission detail ───────────────────────────────────────────────────────────

@login_required
def submission_detail(request, uid, sub_id):
    error = None
    parsed = None

    try:
        schema, submissions, structure = _load(uid)
        risk_labels = structure.get('risk_labels', {})
        activity_specific_labels = structure.get('activity_specific_labels', {})
        country_labels = structure.get('country_labels', {})

        raw = next((s for s in submissions if s.get('_id') == sub_id), None)
        if raw is None:
            error = f'Submission #{sub_id} not found.'
        else:
            parsed = api_client.parse_submission_detail(
                raw, risk_labels, activity_specific_labels, country_labels
            )
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


@login_required
def export_csv(request, uid):
    try:
        schema, submissions, structure = _load(uid)
    except api_client.KoboAPIError as exc:
        return HttpResponse(f'API error: {exc}', status=502)

    risk_labels = structure.get('risk_labels', {})
    activity_specific_labels = structure.get('activity_specific_labels', {})
    country_labels = structure.get('country_labels', {})

    pseudo_buffer = _Echo()
    writer = csv.writer(pseudo_buffer)

    def rows():
        yield writer.writerow([
            '#', 'Pays', 'Lieu', 'Code activité', 'Activité',
            'Responsable', 'Date début', 'Date fin',
            'Catégorie risque', 'Description risque', 'Mesures de mitigation',
        ])
        i = 1
        for sub in submissions:
            p = api_client.parse_submission_detail(
                sub, risk_labels, activity_specific_labels, country_labels
            )
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


@login_required
def export_xlsx(request, uid):
    try:
        schema, submissions, structure = _load(uid)
    except api_client.KoboAPIError as exc:
        return HttpResponse(f'API error: {exc}', status=502)

    risk_labels = structure.get('risk_labels', {})
    activity_specific_labels = structure.get('activity_specific_labels', {})
    country_labels = structure.get('country_labels', {})

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Données'

    headers = [
        '#', 'Pays', 'Lieu', 'Code activité', 'Description activité',
        'Responsable', 'Date début', 'Date fin',
        'Catégorie du risque', 'Description du risque', 'Mesures de mitigation',
    ]
    ws.append(headers)
    header_fill = PatternFill('solid', fgColor='C00000')
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = header_fill
        cell.alignment = Alignment(wrap_text=True)

    i = 1
    for sub in submissions:
        p = api_client.parse_submission_detail(
            sub, risk_labels, activity_specific_labels, country_labels
        )
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

    # Auto-width (approximate)
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
