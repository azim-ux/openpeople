"""UK ordinary non-director Class 1 NI, exact percentage method, 2026/27.

PAYE income tax, directors, irregular periods, loans, pension and statutory pay
remain unsupported. HR must establish category eligibility; no category guessing.
"""
from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_DOWN

PACK='GB-CLASS1-NI-2026-27.1'
SOURCE='https://www.gov.uk/guidance/rates-and-thresholds-for-employers-2026-to-2027'
TECHNICAL='https://www.gov.uk/government/publications/payroll-technical-specifications-national-insurance'
# employee main rate, employer threshold group: normal/freeport/young.
CATEGORIES={
    'A':('.08','normal'),'B':('.0185','normal'),'C':('0','normal'),'J':('.02','normal'),
    'D':('.02','freeport'),'E':('.0185','freeport'),'F':('.08','freeport'),
    'I':('.0185','freeport'),'K':('0','freeport'),'L':('.02','freeport'),
    'N':('.08','freeport'),'S':('0','freeport'),
    'H':('.08','young'),'M':('.08','young'),'V':('.08','young'),'Z':('.02','young')}
FIELDS={'country','currency','pay_date','frequency','category','gross_minor','ni_earnings_minor','ordinary_non_director','category_eligibility_reviewed'}


def template():
    return {'country':'GB','currency':'GBP','pay_date':'2026-10-31','frequency':'monthly',
            'category':'A','gross_minor':500000,'ni_earnings_minor':500000,
            'ordinary_non_director':True,'category_eligibility_reviewed':True}


def descriptor():
    return {'id':PACK,'country':'GB','currency':'GBP','effective_from':'2026-04-06','effective_to':'2027-04-05',
            'sources':[SOURCE,TECHNICAL],'researched_on':'2026-10-09','scope':'Ordinary non-director Class 1 National Insurance, weekly or monthly exact-percentage method',
            'complete_statutory_supported':False,'independently_reviewed':False}


def calculate(value):
    if not isinstance(value,dict) or set(value)!=FIELDS:raise ValueError('Use the complete UK National Insurance template.')
    if value['country']!='GB' or value['currency']!='GBP' or value['ordinary_non_director'] is not True or value['category_eligibility_reviewed'] is not True:raise ValueError('Reviewed ordinary UK non-director earnings and category eligibility in GBP are required.')
    try:paid=date.fromisoformat(value['pay_date'])
    except (ValueError,TypeError):raise ValueError('Choose a valid supported UK pay date.') from None
    if not date(2026,4,6)<=paid<=date(2027,4,5):raise ValueError('No UK rule pack is available for this pay date.')
    if not isinstance(value['frequency'],str) or value['frequency'] not in ('weekly','monthly'):raise ValueError('Only ordinary weekly and monthly periods are supported.')
    if not isinstance(value['category'],str) or value['category'] not in CATEGORIES:raise ValueError('Choose a supported reviewed NI category.')
    for key in ('gross_minor','ni_earnings_minor'):
        if type(value[key]) is not int or not 0<=value[key]<=9000000000000:raise ValueError('Enter nonnegative integer GBP pence within the supported limit.')
    gross=value['gross_minor'];earnings=value['ni_earnings_minor']
    if earnings>gross:raise ValueError('NI earnings cannot exceed the supplied ordinary gross wages.')
    primary,upper,secondary,freeport=(24200,96700,9600,48100) if value['frequency']=='weekly' else (104800,418900,41700,208300)
    rate,group=CATEGORIES[value['category']]
    # Exact percentage method: calculate bands precisely, then round each total.
    # HMRC software guidance section 4.2: inspect only the third decimal
    # pound digit, ignoring later digits; 5 or less down, 6 or more up.
    def cents(amount):return round_contribution(amount)
    employee=cents(Decimal(max(0,min(earnings,upper)-primary))*Decimal(rate)+Decimal(max(0,earnings-upper))*(Decimal('.02') if rate!='0' else Decimal(0)))
    threshold={'normal':secondary,'freeport':freeport,'young':upper}[group]
    employer=cents(Decimal(max(0,earnings-threshold))*Decimal('.15'))
    return {'rule_pack':PACK,'sources':[SOURCE,TECHNICAL],'inputs':value,'gross_minor':gross,
            'deductions':[{'label':'Employee Class 1 National Insurance','amount_minor':employee}],
            'employer_contributions':[{'label':'Employer Class 1 National Insurance','amount_minor':employer}],
            'net_before_other_deductions_minor':gross-employee,'complete_statutory_supported':False,
            'government_filing_supported':False,'review_required':True,
            'limits':['PAYE income tax','Directors and irregular periods','Student loans','Pensions and benefits','Statutory pay','Government filing']}


def round_contribution(pence):
    return int(pence.quantize(Decimal('.1'),rounding=ROUND_DOWN).quantize(Decimal('1'),rounding=ROUND_HALF_DOWN))
