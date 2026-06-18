import requests
from .models import KoboConfig


class KoboAPIError(Exception):
    pass


def _get_config():
    return KoboConfig.get()


def _headers(config):
    return {'Authorization': f'Token {config.api_token}'}


def list_assets(config=None):
    """Return list of survey assets from /api/v2/assets/."""
    if config is None:
        config = _get_config()
    url = f'{config.server_url.rstrip("/")}/api/v2/assets/'
    results = []
    params = {'asset_type': 'survey', 'limit': 100}
    while url:
        try:
            resp = requests.get(url, headers=_headers(config), params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise KoboAPIError(str(exc)) from exc
        data = resp.json()
        results.extend(data.get('results', []))
        url = data.get('next')
        params = {}  # next URL already includes params
    return results


def get_schema(uid, config=None):
    """Return form schema dict for asset uid."""
    if config is None:
        config = _get_config()
    url = f'{config.server_url.rstrip("/")}/api/v2/assets/{uid}/'
    try:
        resp = requests.get(url, headers=_headers(config), timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise KoboAPIError(str(exc)) from exc
    return resp.json()


def get_submissions(uid, config=None):
    """Return all submission records for asset uid as a list of dicts."""
    if config is None:
        config = _get_config()
    base_url = f'{config.server_url.rstrip("/")}/api/v2/assets/{uid}/data/'
    results = []
    url = base_url
    params = {'limit': 100, 'format': 'json'}
    while url:
        try:
            resp = requests.get(url, headers=_headers(config), params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise KoboAPIError(str(exc)) from exc
        data = resp.json()
        results.extend(data.get('results', []))
        url = data.get('next')
        params = {}
    return results


def parse_groups(schema):
    """
    Parse the form schema and return (group_order, groups).

    groups maps key -> {
      'label': str,
      'questions': [full_path, ...],
      'is_repeat': bool,
      'full_key': str,           # slash-path from submission root for this group
      'parent_repeat_key': str,  # full_key of innermost enclosing repeat, or None
    }

    full_path for questions is the slash-path KoboToolBox uses in submission data.
    Repeat group data is stored as arrays in submissions; parent_repeat_key and
    full_key are needed to traverse the nesting when building table rows.
    """
    survey = schema.get('content', {}).get('survey', [])
    groups = {'_general': {
        'label': 'General', 'questions': [],
        'is_repeat': False, 'full_key': None, 'parent_repeat_key': None,
    }}
    group_order = ['_general']
    name_stack = []    # schema names of currently open groups/repeats
    is_rpt_stack = []  # parallel: True when that level is a begin_repeat

    for row in survey:
        row_type = row.get('type', '')
        name = row.get('name') or row.get('$autoname', '')

        if row_type in ('begin_group', 'begin_repeat'):
            label = _extract_label(row)
            is_rpt = row_type == 'begin_repeat'
            full_key = '/'.join(name_stack + [name])

            # Full key of the innermost enclosing repeat (for data traversal)
            parent_rpt_key = None
            for i in range(len(is_rpt_stack) - 1, -1, -1):
                if is_rpt_stack[i]:
                    parent_rpt_key = '/'.join(name_stack[:i + 1])
                    break

            groups[name] = {
                'label': label or name,
                'questions': [],
                'is_repeat': is_rpt,
                'full_key': full_key,
                'parent_repeat_key': parent_rpt_key,
            }
            group_order.append(name)
            name_stack.append(name)
            is_rpt_stack.append(is_rpt)

        elif row_type in ('end_group', 'end_repeat'):
            if name_stack:
                name_stack.pop()
                is_rpt_stack.pop()

        elif row_type not in ('note',) and name:
            current = name_stack[-1] if name_stack else '_general'
            full_path = '/'.join(name_stack + [name]) if name_stack else name
            groups[current]['questions'].append(full_path)

    group_order = [g for g in group_order if groups[g]['questions']]
    return group_order, {k: groups[k] for k in group_order if k in groups}


def get_question_labels(schema):
    """Return {full_path: label_string} for all questions.
    Paths match parse_groups: full slash-path from submission root."""
    survey = schema.get('content', {}).get('survey', [])
    labels = {}
    name_stack = []
    for row in survey:
        row_type = row.get('type', '')
        name = row.get('name') or row.get('$autoname', '')
        if row_type in ('begin_group', 'begin_repeat'):
            name_stack.append(name)
        elif row_type in ('end_group', 'end_repeat'):
            if name_stack:
                name_stack.pop()
        elif name:
            full_path = '/'.join(name_stack + [name]) if name_stack else name
            labels[full_path] = _extract_label(row) or name
    return labels


def parse_submission_detail(submission, risk_labels, activity_specific_labels=None, country_labels=None):
    """
    Parse a raw submission dict into a structured dict with:
      - activity: flat dict of activity details
      - risks: list of {category_code, category_label, description, measures: [str]}
    """
    if activity_specific_labels is None:
        activity_specific_labels = {}
    if country_labels is None:
        country_labels = {}

    activity_code = submission.get('group_ActivityDetails/activity_code', '')
    country_code = submission.get('group_ActivityDetails/country', '')

    activity = {
        'submission_id': submission.get('_id', ''),
        'submission_time': submission.get('_submission_time', ''),
        'country_code': country_code,
        'country_label': country_labels.get(country_code, country_code),
        'activity_code': activity_code,
        'activity_label': activity_specific_labels.get(activity_code, activity_code),
        'activity_location': submission.get('group_ActivityDetails/activity_location', ''),
        'activity_responsible': submission.get('group_ActivityDetails/activity_responsible', ''),
        'activity_description': submission.get('group_ActivityDetails/activity_description', ''),
        'start_date': submission.get('group_ActivityDetails/start_date', ''),
        'end_date': submission.get('group_ActivityDetails/end_date', ''),
    }

    risks = []
    for risk_item in submission.get('group_identified_risks', []):
        category_code = risk_item.get('group_identified_risks/risk-category', '')
        measures = [
            m.get('group_identified_risks/group_mitigation_measures/mitigation_measure', '')
            for m in risk_item.get('group_identified_risks/group_mitigation_measures', [])
            if m.get('group_identified_risks/group_mitigation_measures/mitigation_measure')
        ]
        risks.append({
            'category_code': category_code,
            'category_label': risk_labels.get(category_code, category_code),
            'description': risk_item.get('group_identified_risks/risk_description', ''),
            'measures': measures,
        })

    return {'activity': activity, 'risks': risks}


def get_field_choices(schema):
    """Return [(path, label, type), ...] for all user-answerable fields.
    Fields inside repeat groups are excluded (arrays not supported in v1 editor)."""
    survey = schema.get('content', {}).get('survey', [])
    fields = []
    group_stack = []
    in_repeat = 0

    for row in survey:
        row_type = row.get('type', '')
        name = row.get('name') or row.get('$autoname', '')

        if row_type == 'begin_repeat':
            in_repeat += 1
        elif row_type == 'end_repeat':
            in_repeat = max(0, in_repeat - 1)
        elif row_type == 'begin_group':
            if name:
                group_stack.append(name)
        elif row_type == 'end_group':
            if group_stack:
                group_stack.pop()
        elif row_type not in ('note',) and name and in_repeat == 0:
            path = '/'.join(group_stack + [name]) if group_stack else name
            label = _extract_label(row) or name
            fields.append((path, label, row_type))

    return fields


def get_choice_labels(schema, field_path):
    """Return {value: label} for a select_one/select_multiple field by its full path.
    Returns empty dict if the field is not a choice field or not found."""
    survey = schema.get('content', {}).get('survey', [])
    choices = schema.get('content', {}).get('choices', [])

    field_name = field_path.rsplit('/', 1)[-1]
    list_name = None
    for row in survey:
        if (row.get('name') or row.get('$autoname', '')) == field_name:
            list_name = row.get('list_name') or row.get('select_from_list_name')
            break

    if not list_name:
        return {}

    return {
        c['name']: _extract_label(c) or c['name']
        for c in choices
        if c.get('list_name') == list_name and c.get('name')
    }


def _extract_label(row):
    label = row.get('label', '')
    if isinstance(label, list):
        return label[0] if label else ''
    return label or ''


def parse_group_tree(schema, valid_keys):
    """Return flat list of nav nodes for sidebar tree.

    valid_keys: set of group keys returned by parse_groups (have questions).
    Each node: {key, label, depth, is_repeat, has_data, indent}
      has_data=True  → clickable link
      has_data=False → structural section header (non-clickable)
    Section headers with no clickable descendant are pruned.
    indent is a precomputed CSS padding-left string.
    """
    survey = schema.get('content', {}).get('survey', [])
    raw = []
    stack = []

    if '_general' in valid_keys:
        raw.append({'key': '_general', 'label': 'General', 'depth': 0,
                    'is_repeat': False, 'has_data': True})

    for row in survey:
        row_type = row.get('type', '')
        name = row.get('name') or row.get('$autoname', '')
        label = _extract_label(row) or name

        if row_type in ('begin_group', 'begin_repeat'):
            raw.append({'key': name, 'label': label, 'depth': len(stack),
                        'is_repeat': row_type == 'begin_repeat',
                        'has_data': name in valid_keys})
            stack.append(name)
        elif row_type in ('end_group', 'end_repeat'):
            if stack:
                stack.pop()

    # Prune header-only nodes that have no clickable descendant
    result = []
    for i, node in enumerate(raw):
        if node['has_data']:
            result.append(node)
        else:
            for j in range(i + 1, len(raw)):
                if raw[j]['depth'] <= node['depth']:
                    break
                if raw[j]['has_data']:
                    result.append(node)
                    break

    # Precompute indent style (1.25rem per depth level + 0.75rem base)
    for node in result:
        node['indent'] = f'{node["depth"] * 1.25 + 0.75}rem'

    return result
