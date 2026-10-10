"""Payroll capability guidance and validation of externally calculated results.

Only the separately scoped US 2026 federal preview is implemented internally.
Government submission and payment execution are not implemented.
Country requirements are a dated implementation checklist, not legal advice or
an assertion that imported results comply with a country's law.
"""
import json

from localization import COUNTRIES, currency_digits

WORKDAY_GUIDE = 'https://doc.workday.com/admin-guide/en-us/payroll/payroll.html'
RESEARCHED_ON = '2026-10-09'
COUNTRY_REQUIREMENTS = {
    'AU': {'topics': ['PAYG withholding', 'Superannuation', 'Single Touch Payroll'], 'authority': 'Australian Taxation Office', 'url': 'https://softwaredevelopers.ato.gov.au/STP'},
    'CA': {'topics': ['Income tax withholding', 'CPP/QPP and EI', 'Province-specific deductions', 'T4 and Record of Employment'], 'authority': 'Canada Revenue Agency', 'url': 'https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/t4001/employers-guide-payroll-deductions-remittances.html'},
    'FR': {'topics': ['Employee and employer social contributions', 'DSN reporting', 'Income tax withholding'], 'authority': 'Urssaf', 'url': 'https://www.urssaf.fr/accueil/employeur/gerer-entreprise/declaration-sociale-nominative.html'},
    'IE': {'topics': ['PAYE, USC and PRSI', 'Revenue Payroll Notifications', 'Revenue payroll submissions', 'Pension auto-enrolment'], 'authority': 'Revenue', 'url': 'https://www.revenue.ie/en/employing-people/becoming-an-employer-and-ongoing-obligations/employer-obligations-from-01-01-2019/index.aspx'},
    'GB': {'topics': ['PAYE and National Insurance', 'Statutory payments', 'FPS/EPS reporting', 'Pension auto-enrolment'], 'authority': 'HMRC', 'url': 'https://www.gov.uk/running-payroll'},
    'US': {'topics': ['Federal withholding', 'Social Security and Medicare', 'State and local requirements', 'Employment tax returns and W-2'], 'authority': 'Internal Revenue Service', 'url': 'https://www.irs.gov/publications/p15'},
}


def capabilities():
    from statutory import catalog
    return {'researched_on': RESEARCHED_ON, 'comparison_source': WORKDAY_GUIDE,
            'partial_statutory_packs': catalog(),
            'automatic_statutory_supported': False, 'government_filing_supported': False,
            'available_modes': ['manual_review', 'external_results'],
            'countries': [{'code': code, 'name': COUNTRIES[code]['name'], **requirements,
                           'workday_native_documented': True, 'automatic_statutory_supported': False}
                          for code, requirements in COUNTRY_REQUIREMENTS.items()]}


def template(row, month, run=None):
    row = dict(row)
    result = {'format': 'openpeople.external-payroll.v1', 'employee_id': row['employee_id'],
            'month': month, 'country': row['country'], 'currency': row['currency'],
            'provider': '', 'reference': '', 'jurisdiction': '', 'rules_effective_date': '',
            'earnings': [{'label': 'Reviewed gross pay', 'amount_minor': row['gross_paise']}],
            'deductions': [{'label': 'Reviewed total deductions', 'amount_minor': row['deductions_paise']}],
            'employer_contributions': [], 'net_minor': row['gross_paise'] - row['deductions_paise'],
            'review_note': ''}
    if run is not None:
        from pay_periods import period_contract
        period=period_contract(run)
        if period:
            result['format']='openpeople.external-payroll.v2'
            result['period']=period
    if row.get('external_result'):
        previous = json.loads(row['external_result'])
        result.update({key: previous[key] for key in result})
    return result


def validate_external(value, row, month, run=None):
    from server import APIError, date_field, integer, text_field
    expected_template=template(row,month,run)
    required = set(expected_template)
    if not isinstance(value, dict) or set(value) != required:
        raise APIError(400, 'Use the external payroll template with all required fields and no additional fields.')
    if value['format'] != expected_template['format']:
        raise APIError(400, 'Choose the supported external payroll format.')
    if type(value['employee_id']) is not int or value['employee_id'] != row['employee_id'] or any(value[key] != expected for key, expected in (('month', month), ('country', row['country']), ('currency', row['currency']))):
        raise APIError(400, 'The result must match this employee, pay month, country and currency.')
    result = {key: value[key] for key in ('format', 'employee_id', 'month', 'country', 'currency')}
    if 'period' in expected_template:
        period=value['period'];expected=expected_template['period']
        if not isinstance(period,dict) or set(period)!=set(expected) or any(type(period[key]) is not type(expected[key]) or period[key]!=expected[key] for key in expected):raise APIError(400,'The external result must match the immutable payroll period and group snapshot.')
        result['period']=dict(expected)
    for key, limit in (('provider', 100), ('reference', 200), ('jurisdiction', 100), ('review_note', 500)):
        result[key] = text_field(value, key, limit, optional=key == 'jurisdiction')
    result['rules_effective_date'] = date_field(value, 'rules_effective_date').isoformat()
    totals = {}
    for group in ('earnings', 'deductions', 'employer_contributions'):
        lines = value[group]
        if not isinstance(lines, list) or len(lines) > 40 or (group == 'earnings' and not lines):
            raise APIError(400, 'Provide earnings and at most 40 components in each payroll section.')
        result[group] = []
        for line in lines:
            if not isinstance(line, dict) or set(line) != {'label', 'amount_minor'}:
                raise APIError(400, 'Each payroll component needs a label and an integer amount in currency minor units.')
            result[group].append({'label': text_field(line, 'label', 100), 'amount_minor': integer(line, 'amount_minor', 0, 9000000000000)})
        totals[group] = sum(line['amount_minor'] for line in result[group])
        if totals[group] > 9000000000000:
            raise APIError(400, 'The payroll section total exceeds the supported amount.')
    net = integer(value, 'net_minor', 0, 9000000000000)
    if totals['earnings'] - totals['deductions'] != net:
        raise APIError(400, 'Gross earnings minus employee deductions must equal net pay; employer contributions are separate.')
    result['net_minor'] = net
    result['currency_digits'] = currency_digits(row['currency'])
    return result, totals
