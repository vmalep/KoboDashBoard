class FormModule:
    """Base class for form-specific dashboard modules.

    Subclass this and decorate with @register('uid') to add support for a form.
    """

    form_label = ''       # subtitle shown on the dashboard
    FIELD_PATHS = {}      # logical name → KoboToolBox field path
    EXPORT_HEADERS = []   # CSV/XLSX column headers

    def parse_structure(self, schema):
        """Parse the KoboToolBox schema into a structure dict.

        Must return a dict with at least:
          results, countries, applicable, activity_labels,
          activity_specific_labels, risk_labels, country_labels
        """
        raise NotImplementedError

    def extract_main_activity(self, activity_code):
        """Extract the main activity code from a full code (e.g. R1A1BFA02 → R1A1)."""
        return None

    def extract_result(self, activity_code):
        """Extract the result code from a full code (e.g. R1A1BFA02 → R1)."""
        return None

    def parse_submission_detail(self, submission, structure):
        """Convert a raw submission dict into {'activity': {...}, 'risks': [...]}.

        Default implementation uses self.FIELD_PATHS and structure dicts.
        Override for forms with a completely different structure.
        """
        fp = self.FIELD_PATHS
        activity_specific_labels = structure.get('activity_specific_labels', {})
        country_labels = structure.get('country_labels', {})
        risk_labels = structure.get('risk_labels', {})

        activity_code = submission.get(fp.get('activity_code', ''), '')
        country_code = submission.get(fp.get('country', ''), '')

        activity = {
            'submission_id': submission.get('_id', ''),
            'submission_time': submission.get('_submission_time', ''),
            'country_code': country_code,
            'country_label': country_labels.get(country_code, country_code),
            'activity_code': activity_code,
            'activity_label': activity_specific_labels.get(activity_code, activity_code),
            'activity_location': submission.get(fp.get('activity_location', ''), ''),
            'activity_responsible': submission.get(fp.get('activity_responsible', ''), ''),
            'activity_description': submission.get(fp.get('activity_description', ''), ''),
            'start_date': submission.get(fp.get('activity_start_date', ''), ''),
            'end_date': submission.get(fp.get('activity_end_date', ''), ''),
        }

        risks = []
        for risk_item in submission.get(fp.get('risks_group', ''), []):
            category_code = risk_item.get(fp.get('risk_category', ''), '')
            measures = [
                m.get(fp.get('mitigation_measure', ''), '')
                for m in risk_item.get(fp.get('mitigation_group', ''), [])
                if m.get(fp.get('mitigation_measure', ''))
            ]
            risks.append({
                'category_code': category_code,
                'category_label': risk_labels.get(category_code, category_code),
                'description': risk_item.get(fp.get('risk_description', ''), ''),
                'measures': measures,
            })

        return {'activity': activity, 'risks': risks}
