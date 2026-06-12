from kobo.program_structure import (
    parse_program_structure,
    extract_main_activity as _ema,
    extract_result as _er,
)
from form_modules import register
from form_modules.base import FormModule


@register('ahBScuJA3HBMxg4S7X3MgV')
class DoNotHarmModule(FormModule):
    form_label = 'Matrice de couverture Do Not Harm'

    FIELD_PATHS = {
        'activity_code':        'group_ActivityDetails/activity_code',
        'country':              'group_ActivityDetails/country',
        'activity_responsible': 'group_ActivityDetails/activity_responsible',
        'activity_location':    'group_ActivityDetails/activity_location',
        'activity_start_date':  'group_ActivityDetails/start_date',
        'activity_end_date':    'group_ActivityDetails/end_date',
        'activity_description': 'group_ActivityDetails/activity_description',
        'risks_group':          'group_identified_risks',
        'risk_category':        'group_identified_risks/risk-category',
        'risk_description':     'group_identified_risks/risk_description',
        'mitigation_group':     'group_identified_risks/group_mitigation_measures',
        'mitigation_measure':   'group_identified_risks/group_mitigation_measures/mitigation_measure',
    }

    EXPORT_HEADERS = [
        '#', 'Pays', 'Lieu', 'Code activité', 'Description activité',
        'Responsable', 'Date début', 'Date fin',
        'Catégorie du risque', 'Description du risque', 'Mesures de mitigation',
    ]

    def parse_structure(self, schema):
        return parse_program_structure(schema)

    def extract_main_activity(self, code):
        return _ema(code)

    def extract_result(self, code):
        return _er(code)
