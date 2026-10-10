"""Effective-dated, partial payroll calculations; never a complete tax engine.

US 2026 ordinary periodic wages, modern W-4, IRS Publication 15-T worksheet 1A
and Publication 15 FICA. Exemptions, supplemental wages, legacy W-4, tips,
nonresident rules, unemployment, state/local tax and filings are unsupported.
Inputs are explicitly supplied by a reviewer, not inferred from annual salary.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

PACK = 'US-FEDERAL-PERIODIC-2026.1'
SOURCES = ['https://www.irs.gov/publications/p15t', 'https://www.irs.gov/publications/p15']
# (lower adjusted annual wage, base annual tax, marginal rate), dollars.
TABLES = {
    ('married', False): [(0,0,0),(19300,0,.10),(44100,2480,.12),(120100,11600,.22),(230700,35932,.24),(422850,82048,.32),(531750,116896,.35),(788000,206583.50,.37)],
    ('married', True): [(0,0,0),(16100,0,.10),(28500,1240,.12),(66500,5800,.22),(121800,17966,.24),(217875,41024,.32),(272325,58448,.35),(400450,103291.75,.37)],
    ('single', False): [(0,0,0),(7500,0,.10),(19900,1240,.12),(57900,5800,.22),(113200,17966,.24),(209275,41024,.32),(263725,58448,.35),(648100,192979.25,.37)],
    ('single', True): [(0,0,0),(8050,0,.10),(14250,620,.12),(33250,2900,.22),(60900,8983,.24),(108938,20512,.32),(136163,29224,.35),(328350,96489.63,.37)],
    ('household', False): [(0,0,0),(15550,0,.10),(33250,1770,.12),(83000,7740,.22),(121250,16155,.24),(217300,39207,.32),(271750,56631,.35),(656150,191171,.37)],
    ('household', True): [(0,0,0),(12075,0,.10),(20925,885,.12),(45800,3870,.22),(64925,8077.50,.24),(112950,19603.50,.32),(140175,28315.50,.35),(332375,95585.50,.37)],
}
FIELDS = {'country','currency','pay_date','periods_per_year','w4_status','w4_step2',
          'gross_minor','federal_taxable_minor','ss_taxable_minor','medicare_taxable_minor',
          'prior_ss_wages_minor','prior_medicare_wages_minor','w4_other_income_minor',
          'w4_deductions_minor','w4_credits_minor','extra_withholding_minor','ordinary_resident_wages'}


def catalog():
    from statutory_uk import descriptor
    return {'packs':[{'id':PACK,'country':'US','currency':'USD','effective_from':'2026-01-01',
                     'effective_to':'2026-12-31','sources':SOURCES,'researched_on':'2026-10-09',
                     'scope':'Federal periodic withholding and FICA for ordinary resident wages with a 2020+ W-4',
                     'complete_statutory_supported':False,'independently_reviewed':False},descriptor()],
            'unsupported':['State/local tax','FUTA/SUTA','Supplemental wages and tips','Exemptions and nonresident rules','Legacy W-4','Payments and government filing'],
            'complete_statutory_supported':False}


def input_template():
    return {'country':'US','currency':'USD','pay_date':'2026-10-31','periods_per_year':12,
            'w4_status':'single','w4_step2':False,'gross_minor':500000,
            'federal_taxable_minor':500000,'ss_taxable_minor':500000,'medicare_taxable_minor':500000,
            'prior_ss_wages_minor':0,'prior_medicare_wages_minor':0,'w4_other_income_minor':0,
            'w4_deductions_minor':0,'w4_credits_minor':0,'extra_withholding_minor':0,
            'ordinary_resident_wages':True}


def calculate(value):
    if isinstance(value,dict) and value.get('country')=='GB':
        from statutory_uk import calculate as calculate_uk
        return calculate_uk(value)
    if not isinstance(value,dict) or set(value)!=FIELDS:
        raise ValueError('Use the complete statutory input template without additional fields.')
    if value['country']!='US' or value['currency']!='USD' or value['ordinary_resident_wages'] is not True:
        raise ValueError('Only ordinary US resident periodic wages in USD are supported by this partial pack.')
    try:
        paid = date.fromisoformat(value['pay_date'])
    except (ValueError,TypeError):
        raise ValueError('Choose a valid pay date in the supported rule year.') from None
    if paid.year!=2026:
        raise ValueError('No rule pack is available for this pay date; do not reuse expired rates.')
    if type(value['periods_per_year']) is not int or value['periods_per_year'] not in (2,4,12,24,26,52,260):
        raise ValueError('Choose a supported regular payroll frequency.')
    if value['w4_status'] not in ('single','married','household') or type(value['w4_step2']) is not bool:
        raise ValueError('Choose the modern W-4 filing status and an explicit Step 2 checkbox.')
    for key in FIELDS:
        if key.endswith('_minor') and (type(value[key]) is not int or not 0<=value[key]<=9000000000000):
            raise ValueError('Money and year-to-date bases must be nonnegative integer USD cents within the supported limit.')
    gross=value['gross_minor']
    if any(value[key]>gross for key in ('federal_taxable_minor','ss_taxable_minor','medicare_taxable_minor')):
        raise ValueError('Each current taxable wage base must be at most the current gross wages.')
    periods=Decimal(value['periods_per_year'])
    adjustment=0 if value['w4_step2'] else 1290000 if value['w4_status']=='married' else 860000
    annual=max(Decimal(0),Decimal(value['federal_taxable_minor'])*periods+value['w4_other_income_minor']-value['w4_deductions_minor']-adjustment)
    bracket=TABLES[(value['w4_status'],value['w4_step2'])][0]
    for row in TABLES[(value['w4_status'],value['w4_step2'])]:
        if annual>=Decimal(str(row[0]))*100:bracket=row
    lower,base,rate=(Decimal(str(item)) for item in bracket)
    federal=max(Decimal(0),(base*100+(annual-lower*100)*rate-value['w4_credits_minor'])/periods)+value['extra_withholding_minor']
    ss_base=min(value['ss_taxable_minor'],max(0,18450000-value['prior_ss_wages_minor']))
    additional_base=max(0,value['prior_medicare_wages_minor']+value['medicare_taxable_minor']-20000000)-max(0,value['prior_medicare_wages_minor']-20000000)
    def cents(amount):return int(Decimal(amount).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    def line(label,amount):return {'label':label,'amount_minor':cents(amount)}
    employee=[line('Federal income tax',federal),line('Social Security',Decimal(ss_base)*Decimal('.062')),
              line('Medicare',Decimal(value['medicare_taxable_minor'])*Decimal('.0145')),
              line('Additional Medicare',Decimal(additional_base)*Decimal('.009'))]
    employer=[line('Employer Social Security',Decimal(ss_base)*Decimal('.062')),
              line('Employer Medicare',Decimal(value['medicare_taxable_minor'])*Decimal('.0145'))]
    deduction=sum(item['amount_minor'] for item in employee)
    if deduction>gross:
        raise ValueError('Calculated withholding exceeds gross wages; this needs external payroll review.')
    return {'rule_pack':PACK,'sources':SOURCES,'inputs':value,'deductions':employee,
            'employer_contributions':employer,'gross_minor':gross,'net_before_other_deductions_minor':gross-deduction,
            'complete_statutory_supported':False,'government_filing_supported':False,'review_required':True,
            'limits':catalog()['unsupported']}
