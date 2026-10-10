import copy
from pathlib import Path
import tempfile
import unittest

from government_submission import render,write_export


def fixture():
    address={'name':'FICTIONAL COMPANY','location':'','delivery':'123 TEST STREET','city':'TEST CITY','state':'CA','zip':'90210','zip_extension':'','contact':'FICTIONAL CONTACT','phone':'2025550123','email':'test@example.org'}
    submitter={**address,'ein':'120000001','bso_user_id':'TESTONLY','software_code':'98','vendor_code':'','preparer_code':'L'}
    employer={**address,'ein':'120000002','kind':'N','signature_pin':''}
    worker={'ssn':'001010001','first':'FICTIONAL','middle':'','last':'TEST','suffix':'','location':'','delivery':'456 TEST STREET','city':'TEST CITY','state':'CA','zip':'90210','zip_extension':'',
            'wages_minor':5000000,'federal_tax_minor':600000,'ss_wages_minor':5000000,'ss_tax_minor':310000,'medicare_wages_minor':5000000,'medicare_tax_minor':72500}
    return {'tax_year':2026,'annual_totals_reviewed':True,'no_optional_amounts':True,'original_domestic_regular':True,'submitter':submitter,'employer':employer,'employees':[worker]}


class FilingFormat(unittest.TestCase):
    def test_published_positions_sequence_and_annual_totals(self):
        value=fixture();value['employees'].append({**value['employees'][0],'ssn':'001010002','wages_minor':3000000,'federal_tax_minor':200000,'ss_wages_minor':3000000,'ss_tax_minor':186000,'medicare_wages_minor':3000000,'medicare_tax_minor':43500})
        data=render(value);rows=data.split(b'\r\n');self.assertEqual(rows[-1],b'');rows.pop()
        self.assertEqual([row[:2] for row in rows],[b'RA',b'RE',b'RW',b'RW',b'RT',b'RF'])
        self.assertTrue(all(len(row)==512 for row in rows))
        self.assertEqual(rows[0][2:19],b'120000001TESTONLY')
        self.assertEqual(rows[0][35:37],b'98');self.assertEqual(rows[0][499:500],b'L')
        self.assertEqual(rows[1][2:6],b'2026');self.assertEqual(rows[1][218:221],b'R 0')
        self.assertEqual(rows[2][2:11],b'001010001');self.assertEqual(rows[2][187:253],b'000050000000000060000000005000000000003100000000500000000000072500')
        self.assertEqual(rows[4][2:9],b'0000002')
        self.assertEqual(rows[4][9:99],b'000000008000000000000000800000000000008000000000000000496000000000008000000000000000116000')
        self.assertEqual(rows[5][7:16],b'000000002')
        self.assertEqual(rows[2][342:352],b' '*10)

    def test_bad_input_sensitive_identifiers_and_unsupported_scope_rejected(self):
        cases=[]
        for key,val in [('tax_year',2025),('annual_totals_reviewed',False),('no_optional_amounts',False),('original_domestic_regular',False),('employees',[]),('extra',1)]:
            v=fixture();v[key]=val;cases.append(v)
        for key,val in [('first','X'*16),('last','भारत'),('state',[]),('state','PR'),('ssn','666010001'),('ssn','001000001'),('ssn','001010000'),('wages_minor',True),('ss_wages_minor',18450001),('ss_tax_minor',1143901),('delivery','X\nY')]:
            v=fixture();v['employees'][0][key]=val;cases.append(v)
        for key,val in [('ein','070000001'),('signature_pin','S-123456-1'),('signature_pin','bad'),('phone','+1 2025550123'),('email','x..y@example.org')]:
            v=fixture();v['employer'][key]=val;cases.append(v)
        v=fixture();v['employees'].append(copy.deepcopy(v['employees'][0]));cases.append(v)
        v=fixture();v['submitter']['software_code']='99';cases.append(v)
        for v in cases:
            with self.subTest(value=v),self.assertRaises(ValueError):render(v)

    def test_export_private_exclusive_and_never_claims_authority_acceptance(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);path.chmod(0o700);target=path/'EFW2.txt'
            info=write_export(fixture(),target);self.assertFalse(info['authority_accepted']);self.assertFalse(info['online_submission_performed'])
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
            before=target.read_bytes()
            with self.assertRaises(FileExistsError):write_export(fixture(),target)
            self.assertEqual(target.read_bytes(),before)
            link=path/'link';link.symlink_to(target)
            with self.assertRaises(ValueError):write_export(fixture(),link)
            path.chmod(0o755)
            with self.assertRaises(ValueError):write_export(fixture(),path/'public.txt')


if __name__=='__main__':unittest.main()
