import unittest

from statutory import calculate, input_template
from test_app import HRFlows


class StatutoryMath(unittest.TestCase):
    def test_independently_worked_monthly_examples(self):
        value=input_template()
        result=calculate(value)
        self.assertEqual([r['amount_minor'] for r in result['deductions']],[41833,31000,7250,0])
        self.assertEqual(result['net_before_other_deductions_minor'],419917)
        self.assertEqual([r['amount_minor'] for r in result['employer_contributions']],[31000,7250])
        for key in ('gross_minor','federal_taxable_minor','ss_taxable_minor','medicare_taxable_minor'):value[key]=700000
        self.assertEqual(calculate(value)['deductions'][0]['amount_minor'],80417)
        value=input_template();value['w4_credits_minor']=240000;value['extra_withholding_minor']=5000
        self.assertEqual(calculate(value)['deductions'][0]['amount_minor'],26833)

    def test_wage_caps_and_additional_medicare_crossing(self):
        value=input_template()
        for key in ('gross_minor','federal_taxable_minor','ss_taxable_minor','medicare_taxable_minor'):value[key]=100000
        value.update(prior_ss_wages_minor=18400000,prior_medicare_wages_minor=19950000)
        self.assertEqual([r['amount_minor'] for r in calculate(value)['deductions']],[0,3100,1450,450])
        value.update(prior_ss_wages_minor=18450000,prior_medicare_wages_minor=21000000)
        self.assertEqual([r['amount_minor'] for r in calculate(value)['deductions']],[0,0,1450,900])

    def test_independently_worked_all_status_and_step2_examples(self):
        # $5,000 monthly; expected cents hand-calculated from the published
        # worksheet/schedules, never read back from implementation constants.
        cases=[('single',False,41833),('single',True,73208),
               ('married',False,23667),('married',True,41833),
               ('household',False,32900),('household',True,58283)]
        for status,step2,expected in cases:
            with self.subTest(status=status,step2=step2):
                self.assertEqual(calculate({**input_template(),'w4_status':status,'w4_step2':step2})['deductions'][0]['amount_minor'],expected)
        value={**input_template(),'periods_per_year':4,'gross_minor':1000000,'federal_taxable_minor':0,'ss_taxable_minor':0,'medicare_taxable_minor':0,'w4_other_income_minor':2850000}
        # Adjusted annual wage exactly $19,900 after the $8,600 adjustment.
        self.assertEqual(calculate(value)['deductions'][0]['amount_minor'],31000)
        self.assertEqual(calculate({**value,'w4_other_income_minor':2850100})['deductions'][0]['amount_minor'],31003)

    def test_rejects_unknown_or_expired_rules_and_ambiguous_inputs(self):
        template=input_template()
        invalid=[None,{},[],{**template,'country':'GB'},{**template,'currency':'INR'},
                 {**template,'pay_date':'2027-01-01'},{**template,'pay_date':'bad'},
                 {**template,'ordinary_resident_wages':False},{**template,'legacy_w4':True},
                 {**template,'w4_step2':1},{**template,'w4_status':[]},{**template,'periods_per_year':13},
                 {**template,'gross_minor':True},{**template,'ss_taxable_minor':500001},
                 {**template,'prior_ss_wages_minor':-1},{**template,'extra_withholding_minor':9000000000000}]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):calculate(value)


class StatutoryAccess(HRFlows):
    def test_access_csrf_and_preview_never_changes_payroll(self):
        self.assertEqual(self.request('GET','/api/statutory')[0],401)
        self.setup_admin();self.add_employee()
        self.assertEqual(self.request('GET','/api/statutory')[1]['input_template'],input_template())
        self.assertEqual(self.request('POST','/api/statutory/preview',input_template(),csrf=False)[0],403)
        self.assertEqual(self.request('POST','/api/statutory/preview',input_template())[0],200)
        self.assertEqual(self.request('GET','/api/state')[1]['pay_runs'],[])
        self.login('person@example.org','EmployeePass123!')
        self.assertEqual(self.request('GET','/api/statutory')[0],403)
        self.assertEqual(self.request('POST','/api/statutory/preview',input_template())[0],403)


def load_tests(loader,tests,pattern):
    return unittest.TestSuite([loader.loadTestsFromTestCase(StatutoryMath),StatutoryAccess('test_access_csrf_and_preview_never_changes_payroll')])
