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


# ── Generic form detail (fallback for forms with no module) ───────────────────

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


@login_required
def export_xlsx(request, uid):
    try:
        schema, submissions, structure, module = _load(uid)
    except api_client.KoboAPIError as exc:
        return HttpResponse(f'API error: {exc}', status=502)

    if module is None:
        return HttpResponse('Export non disponible sans module de formulaire.', status=400)

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
