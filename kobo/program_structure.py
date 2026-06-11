import re

RESULT_LABELS = {
    'R1': 'Protection individuelle',
    'R2': 'Cohésion sociale',
    'R3': 'Renforcement des capacités',
}

COUNTRY_LABELS = {
    'BFA': 'Burkina Faso',
    'BDI': 'Burundi',
    'MAL': 'Mali',
    'NIG': 'Niger',
    'RDC': 'RDC',
}

_MAIN_CODE_RE = re.compile(r'^(R\d+A\d+)')
_COUNTRY_RE = re.compile(r'^R\d+A\d+([A-Z]{3})')


def extract_main_activity(activity_code):
    """R1A1BFA02 → R1A1"""
    m = _MAIN_CODE_RE.match(activity_code or '')
    return m.group(1) if m else None


def extract_result(activity_code):
    """R1A1BFA02 → R1"""
    main = extract_main_activity(activity_code)
    if main:
        m = re.match(r'(R\d+)', main)
        return m.group(1) if m else None
    return None


def extract_country_from_code(activity_code):
    """R1A1BFA02 → BFA (fallback if choice has no country field)"""
    m = _COUNTRY_RE.match(activity_code or '')
    return m.group(1) if m else None


def _extract_label(choice):
    label = choice.get('label', '')
    if isinstance(label, list):
        label = label[0] if label else ''
    return label or ''


def _strip_code_prefix(label):
    """'R1A1-02. Some description' → 'Some description'"""
    return re.sub(r'^R\d+A\d+-\d+\.\s*', '', label).strip()


def parse_program_structure(schema):
    """
    Parse the form schema choices to build the full program structure.

    Returns a dict:
      {
        'results': [{'code': 'R1', 'label': '...', 'activities': [
            {'code': 'R1A1', 'label': '...', 'countries': ['BFA', ...]}, ...
        ]}],
        'countries': [{'code': 'BFA', 'label': 'Burkina Faso'}, ...],
        'applicable': {('R1A1', 'BFA'), ...},   # (main_code, country) pairs
        'activity_labels': {'R1A1': '...', ...},
        'activity_specific_labels': {'R1A1BFA02': '...', ...},
        'risk_labels': {'Sécu': '1. Risques de sécurité physique', ...},
        'country_labels': {'BFA': 'Burkina Faso', ...},
      }
    """
    choices = schema.get('content', {}).get('choices', [])

    activity_info = {}   # main_code → {label, countries: set, result}
    applicable = set()   # (main_code, country)
    specific_labels = {} # R1A1BFA02 → full label
    risk_labels = {}     # risk code → label
    country_codes = set()

    for choice in choices:
        list_name = choice.get('list_name', '')
        name = choice.get('name', '')
        label = _extract_label(choice)

        if list_name == 'countries':
            country_codes.add(name)

        elif list_name == 'acts':
            specific_labels[name] = label
            main_code = extract_main_activity(name)
            if not main_code:
                continue
            result_code = re.match(r'(R\d+)', main_code).group(1)

            # Country comes from the XLSForm 'country' filter column,
            # or falls back to extraction from the code itself.
            country = choice.get('country') or extract_country_from_code(name)
            if country:
                applicable.add((main_code, country))
                country_codes.add(country)

            if main_code not in activity_info:
                activity_info[main_code] = {
                    'label': _strip_code_prefix(label),
                    'countries': set(),
                    'result': result_code,
                }
            if country:
                activity_info[main_code]['countries'].add(country)

        elif list_name == 'risks':
            risk_labels[name] = label

    # Build ordered results list
    results_map = {}
    for main_code in sorted(activity_info):
        info = activity_info[main_code]
        r = info['result']
        if r not in results_map:
            results_map[r] = {
                'code': r,
                'label': RESULT_LABELS.get(r, r),
                'activities': [],
            }
        results_map[r]['activities'].append({
            'code': main_code,
            'label': info['label'],
            'countries': sorted(info['countries']),
        })

    results_list = [results_map[k] for k in sorted(results_map)]
    countries_list = [
        {'code': c, 'label': COUNTRY_LABELS.get(c, c)}
        for c in sorted(country_codes)
        if c in COUNTRY_LABELS
    ]
    activity_labels = {code: info['label'] for code, info in activity_info.items()}

    return {
        'results': results_list,
        'countries': countries_list,
        'applicable': applicable,
        'activity_labels': activity_labels,
        'activity_specific_labels': specific_labels,
        'risk_labels': risk_labels,
        'country_labels': {c['code']: c['label'] for c in countries_list},
    }
