import unittest
from datetime import datetime
from unittest.mock import patch
from test_app import HRFlows

class CountryFlows(HRFlows):
    def country_employee(self,email,country,salary=1200000,timezone=None):
        data={'name':'International worker','email':email,'title':'Analyst','department':'Global','location':'Remote','annual_salary':salary,'start_date':'2026-10-01','country':country,'password':'EmployeePass123!'}
        if timezone:data['timezone']=timezone
        return self.request('POST','/api/employees',data)

    def test_offline_country_options_and_employee_currency(self):
        self.setup_admin()
        catalog=self.request('GET','/api/countries');self.assertEqual(catalog[0],200)
        self.assertGreaterEqual(len(catalog[1]['countries']),249)
        employee=self.country_employee('us@example.org','US')[1]['id']
        row=next(row for row in self.request('GET','/api/state')[1]['employees'] if row['id']==employee)
        self.assertEqual((row['country'],row['currency'],row['timezone']),('US','USD','America/New_York'))
        self.assertEqual(self.country_employee('invalid@example.org','INVALID')[0],400)
        self.assertEqual(self.country_employee('invalid-zone@example.org','US',timezone='../../private')[0],400)
        self.assertEqual(self.request('PATCH',f'/api/employees/{employee}',{'currency':'EUR'})[0],409)

    def test_multi_currency_payroll_is_not_added_as_one_amount(self):
        self.setup_admin()
        us=self.country_employee('us@example.org','US')[1]['id']
        jp=self.country_employee('jp@example.org','JP')[1]['id']
        bh=self.country_employee('bh@example.org','BH')[1]['id']
        preview=self.request('GET','/api/payroll?month=2026-10')[1]
        rows={row['id']:row for row in preview['rows']}
        self.assertEqual(rows[us]['gross_paise'],10000000)
        self.assertEqual(rows[jp]['gross_paise'],100000)
        self.assertEqual(rows[bh]['gross_paise'],100000000)
        self.assertIsNone(preview['total']);self.assertIn('USD',preview['totals_by_currency'])
        run=self.request('POST','/api/pay_runs',{'month':'2026-10'})[1]['id']
        results=self.request('GET',f'/api/pay_runs/{run}')[1]['rows']
        self.assertEqual(next(row for row in results if row['employee_id']==jp)['currency'],'JPY')
        self.assertTrue(all(row['country'] in ('IN','US','JP','BH') for row in results))
        self.assertTrue(all(row['statutory_status']=='Manual review required' for row in preview['rows']))

    def test_local_work_date_and_zero_decimal_expense_validation(self):
        self.setup_admin();self.country_employee('us@example.org','US');self.country_employee('jp@example.org','JP')
        self.login('us@example.org','EmployeePass123!')
        with patch('server.datetime') as clock:
            clock.now.return_value=datetime.fromisoformat('2026-10-10T02:00:00+05:30')
            record=self.request('POST','/api/attendance',{'action':'in'})[1]['id']
            row=next(row for row in self.request('GET','/api/state')[1]['attendance'] if row['id']==record)
        self.assertEqual(row['work_date'],'2026-10-09')
        self.login('jp@example.org','EmployeePass123!')
        claim={'description':'Train','amount':100.5,'category':'Travel','expense_date':'2026-10-09'}
        self.assertEqual(self.request('POST','/api/expenses',claim)[0],400)
        status,result=self.request('POST','/api/expenses',{**claim,'amount':100});self.assertEqual(status,201)
        row=next(row for row in self.request('GET','/api/state')[1]['expenses'] if row['id']==result['id'])
        self.assertEqual(row['amount_paise'],100);self.assertEqual(row['currency'],'JPY')

    def test_country_holidays_and_employee_workweeks_are_separate(self):
        self.setup_admin();us=self.country_employee('us@example.org','US')[1]['id']
        employee=self.add_employee()
        self.assertEqual(self.request('POST','/api/holidays',{'date':'2026-11-02','name':'Reviewed India holiday','country':'IN'})[0],201)
        self.assertEqual(self.request('POST','/api/leave',{'employee_id':employee,'type':'Annual','start_date':'2026-11-02','end_date':'2026-11-02','reason':'Holiday'})[0],400)
        self.assertEqual(self.request('POST','/api/leave',{'employee_id':us,'type':'Annual','start_date':'2026-11-02','end_date':'2026-11-02','reason':'Working day'})[0],201)
        self.assertEqual(self.request('PATCH',f'/api/employees/{us}',{'work_week':[0,1,2,3,6]})[0],200)
        self.assertEqual(self.request('POST','/api/leave',{'employee_id':us,'type':'Annual','start_date':'2026-11-01','end_date':'2026-11-01','reason':'Scheduled Sunday'})[0],201)
        self.assertEqual(self.request('PATCH',f'/api/employees/{us}',{'work_week':[7]})[0],400)


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(CountryFlows(name) for name in CountryFlows.__dict__ if name.startswith('test_'))
