from form_modules import register
from form_modules.base import FormModule

UID = 'aGYR58K9en2z8mnsrsEwLq'

COUNTRY_LABELS = {
    'burkina': 'Burkina Faso',
    'niger': 'Niger',
    'mali': 'Mali',
    'burundi': 'Burundi',
    'rdc': 'RD Congo',
}

RESULT_LABELS = {
    'result1': 'R1 — Réponse aux menaces',
    'result2': 'R2 — Réduction des vulnérabilités',
    'result3': 'R3 — Capacités des Sociétés Nationales',
    'result4': 'R4 — Crisis Modifier',
}

INDICATOR_LABELS = {
    'OS_1': '[OS] Bénéficiaires déclarant aide fournie de manière digne et sûre',
    'R1.A': '[R1] Personnes ayant bénéficié de services spécialisés',
    'R1.B': '[R1] Personnes assistées via TM/distributions',
    'R1.1': '[R1.1] Personnes identifiées',
    'R1.2': '[R1.2] Personnes ayant bénéficié de prise en charge',
    'R1.3': '[R1.3] Personnes référées vers d\'autres services',
    'R1.4': '[R1.4] PSH mis en place ou appuyés',
    'R1.5': '[R1.5] Personnes assistées au PSH',
    'R1.6': '[R1.6] Personnes ayant bénéficié de soutien PSS',
    'R1.7': '[R1.7] Personnes ayant bénéficié de documents d\'état civil',
    'R1.8': '[R1.8] Personnes assistées (alimentaire, abri, wash, etc.)',
    'R1.9': '[R1.9] Personnes ayant bénéficié d\'un service PLF',
    'R2.B': '[R2] Personnes déclarant amélioration de cohésion sociale',
    'R2.C': '[R2] Personnes formées/sensibilisées en PGI, DH, cohésion',
    'R2.1': '[R2.1] Personnes ayant participé aux activités de mobilisation',
    'R2.2': '[R2.2] Personnes participant aux activités de cohésion sociale',
    'R2.3': '[R2.3] Personnes déclarant amélioration de cohésion sociale',
    'R2.4': '[R2.4] Personnes assistées (alimentaire, abri, wash, etc.)',
    'R2.5': '[R2.5] Personnes ayant reçu ressources pour moyens d\'existence',
    'R2.6': '[R2.6] Groupements ayant bénéficié d\'un appui en AGR',
    'R2.7': '[R2.7] Mécanismes communautaires mis en place/redynamisés',
    'R2.8': '[R2.8] Actions mises en œuvre pour réduction des risques',
    'R2.9': '[R2.9] Personnes ayant accès à l\'eau potable',
    'R2.10': '[R2.10] Personnes ayant accès à des installations sanitaires',
    'R2.11': '[R2.11] Leaders et autorités formés',
    'R3.A': '[R3] Staff/volontaires formés ayant amélioré leurs connaissances',
    'R3.B': '[R3] Plaintes enregistrées par la SNH',
    'R3.1': '[R3.1] Personnel et volontaires formés sur thématiques transversales',
    'R3.2': '[R3.2] Bénéficiaires formés déclarant amélioration des connaissances',
    'R3.3': '[R3.3] Clubs de redevabilité fonctionnels',
    'R3.4': '[R3.4] Personnes connaissant le mécanisme CEA',
    'R3.5': '[R3.5] Personnes satisfaites des réponses de la Hotline',
    'R3.6': '[R3.6] Personnes ayant recours au service hotline',
    'R3.7': '[R3.7] Plaintes enregistrées par la SNH',
    'R3.8': '[R3.8] Stratégies/procédures de protection mises à jour',
    'R3.9': '[R3.9] Ateliers ou visites d\'échanges organisés',
    'R4.A': '[R4] Personnes assistées via Crisis Modifier',
    'R4.1': '[R4.1] Personnes assistées via Crisis Modifier',
}

RESULT_KEYS = ['result1', 'result2', 'result3', 'result4']


def _safe_int(v):
    try:
        f = float(v)
        if f != f:  # NaN check
            return 0
        return int(f)
    except (TypeError, ValueError):
        return 0


def _parse_indicator_item(rkey, item):
    """Parse one repeat instance from result{N} list."""
    n = rkey[-1]  # '1'..'4'
    prefix = f'{rkey}/Indicator_r{n}/Indicator_r{n}'

    code = item.get(f'{rkey}/{rkey}_calculation_02', '')
    total = _safe_int(item.get(f'{prefix}_total'))

    age_yn = item.get(f'{prefix}_age_yesno', '') == 'yes'
    disability_yn = item.get(f'{prefix}_handicap_yesno', '') == 'yes'
    status_yn = item.get(f'{prefix}_status_yesno', '') == 'yes'

    age = {}
    if age_yn:
        age = {
            'male_0_5':   _safe_int(item.get(f'{prefix}_age_0-5_male')),
            'male_6_18':  _safe_int(item.get(f'{prefix}_age_6-18_male')),
            'male_19_49': _safe_int(item.get(f'{prefix}_age_19-49_male')),
            'male_50p':   _safe_int(item.get(f'{prefix}_age_50_male')),
            'fem_0_5':    _safe_int(item.get(f'{prefix}_age_0-5_female')),
            'fem_6_18':   _safe_int(item.get(f'{prefix}_age_6-18_female')),
            'fem_19_49':  _safe_int(item.get(f'{prefix}_age_19-49_female')),
            'fem_50p':    _safe_int(item.get(f'{prefix}_age_50_female')),
            'male_total': _safe_int(item.get(f'{prefix}_male_total')),
            'fem_total':  _safe_int(item.get(f'{prefix}_female_total')),
        }

    disability = {}
    if disability_yn:
        disability = {
            'with':    _safe_int(item.get(f'{prefix}_handicap_yes')),
            'without': _safe_int(item.get(f'{prefix}_handicap_no')),
        }

    status = {}
    if status_yn:
        status = {
            'pdi':        _safe_int(item.get(f'{prefix}_status_pdi')),
            'host':       _safe_int(item.get(f'{prefix}_status_host')),
            'refugee':    _safe_int(item.get(f'{prefix}_status_refugee')),
            'returnees':  _safe_int(item.get(f'{prefix}_status_returnees')),
            'stateless':  _safe_int(item.get(f'{prefix}_status_stateless')),
            'other':      _safe_int(item.get(f'{prefix}_status_other')),
        }

    return {
        'code': code,
        'label': INDICATOR_LABELS.get(code, code),
        'result_key': rkey,
        'result_label': RESULT_LABELS.get(rkey, rkey),
        'total': total,
        'age': age,
        'disability': disability,
        'status': status,
    }


def parse_submission(sub):
    """Return structured dict from a raw KoboToolBox submission."""
    country = sub.get('intro/country', '')
    year = sub.get('intro/reported_period_year', '')
    quarter = sub.get('intro/reported_period_semester_quarter', '')
    reporter = sub.get('intro/reported_reporter', '')

    indicators = []
    for rkey in RESULT_KEYS:
        for item in (sub.get(rkey) or []):
            ind = _parse_indicator_item(rkey, item)
            if ind['code']:
                indicators.append(ind)

    return {
        'id': sub.get('_id', ''),
        'country': country,
        'country_label': COUNTRY_LABELS.get(country, country),
        'year': year,
        'quarter': quarter,
        'period': f'{year} {quarter}' if year and quarter else year or quarter,
        'reporter': reporter,
        'indicators': indicators,
    }


def aggregate(parsed_submissions):
    """
    Aggregate a list of parsed submissions into:
      {indicator_code: {country: total, ...}, ...}
    and meta info.
    """
    by_indicator = {}  # code → {country → total}
    by_result = {}     # rkey → total
    by_country = {}    # country → total
    by_period = {}     # 'YYYY QN' → total

    for ps in parsed_submissions:
        country = ps['country']
        period = ps['period']
        for ind in ps['indicators']:
            code = ind['code']
            total = ind['total']
            rkey = ind['result_key']

            by_indicator.setdefault(code, {})
            by_indicator[code][country] = by_indicator[code].get(country, 0) + total

            by_result[rkey] = by_result.get(rkey, 0) + total
            by_country[country] = by_country.get(country, 0) + total
            by_period[period] = by_period.get(period, 0) + total

    return {
        'by_indicator': by_indicator,
        'by_result': by_result,
        'by_country': by_country,
        'by_period': by_period,
    }


@register(UID)
class Amopah3Module(FormModule):
    form_label = 'AMOPAH III — Suivi des indicateurs'
    FIELD_PATHS = {}
    EXPORT_HEADERS = [
        '#', 'Pays', 'Année', 'Trimestre', 'Rapporteur',
        'Résultat', 'Code indicateur', 'Libellé indicateur', 'Valeur rapportée',
        'Hommes total', 'Femmes total',
        'H 0-5', 'H 6-18', 'H 19-49', 'H 50+',
        'F 0-5', 'F 6-18', 'F 19-49', 'F 50+',
        'Avec handicap', 'Sans handicap',
        'PDI', 'Communauté hôte', 'Réfugiés', 'Rapatriés', 'Migrants', 'Autres',
    ]

    def parse_structure(self, schema):
        return {
            'countries': COUNTRY_LABELS,
            'results': RESULT_LABELS,
            'indicators': INDICATOR_LABELS,
        }

    def parse_submission_detail(self, submission, structure):
        ps = parse_submission(submission)
        return {'activity': ps, 'risks': []}

    def parse_submissions(self, submissions):
        return [parse_submission(s) for s in submissions]
