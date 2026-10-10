"""SSA EFW2 2026 domestic regular-wage file adapter (not online submission).

Only a reviewed annual ordinary-wage dataset with no optional W-2 amounts is
supported. Never infer annual totals from one month's payroll. AccuWage/BSO
acceptance and identity verification require the authorized employer account.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

SPEC='https://www.ssa.gov/employer/efw/26efw2.pdf'
STATES=set('AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split())
ADDRESS={'name','location','delivery','city','state','zip','zip_extension','contact','phone','email'}
AMOUNTS=('wages_minor','federal_tax_minor','ss_wages_minor','ss_tax_minor','medicare_wages_minor','medicare_tax_minor')
EMPLOYEE={'ssn','first','middle','last','suffix','location','delivery','city','state','zip','zip_extension',*AMOUNTS}


def catalog():
    return {'id':'US-SSA-EFW2-2026-DOMESTIC-ORDINARY.1','country':'US','tax_year':2026,
            'scope':'RA/RE/RW/RT/RF domestic regular original W-2 wage file, no optional amounts',
            'specification':SPEC,'online_submission_supported':False,'authority_accepted':False,
            'limits':['State/local filing','Tips and optional boxes','Benefits/pension reporting','Territories and foreign addresses','Agents and corrections'],
            'acceptance_required':'Authorized employer must validate with AccuWage and submit through BSO.'}


def _text(value,width,required=True):
    if not isinstance(value,str) or value!=value.strip() or len(value)>width or (required and not value) or any(not 32<=ord(c)<=126 for c in value):
        raise ValueError('A filing text field is missing, too long, non-ASCII or contains control characters; nothing was truncated.')
    return value.ljust(width)


def _digits(value,width):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{'+str(width)+'}',value):raise ValueError('A filing identifier has an invalid digit count.')
    return value


def _money(value,width):
    if type(value) is not int or not 0<=value<10**width:raise ValueError('A filing amount must be a nonnegative integer number of cents within its field width.')
    return str(value).zfill(width)


def _record(kind):return list(kind+' '*510)


def _put(record,start,end,value):
    if len(value)!=end-start+1:raise ValueError('The filing adapter field width is inconsistent.')
    record[start-1:end]=list(value)


def _address(record,value,positions):
    if not isinstance(value['state'],str) or value['state'] not in STATES:raise ValueError('Only US states and DC domestic addresses are supported.')
    for key,start,width,required in positions:
        text=value[key]
        if key=='zip':text=_digits(text,5)
        if key=='zip_extension' and text:text=_digits(text,4)
        _put(record,start,start+width-1,_text(text,width,required))


def _contact(record,value,name,phone,email):
    _put(record,name,name+26,_text(value['contact'],27))
    if not isinstance(value['phone'],str) or not re.fullmatch(r'[0-9]{10}',value['phone']):raise ValueError('Use a ten-digit domestic contact telephone number.')
    _put(record,phone,phone+14,_text(value['phone'],15))
    address=value['email']
    if not isinstance(address,str) or '..' in address or not re.fullmatch(r'[A-Za-z0-9_+\-]+(?:\.[A-Za-z0-9_+\-]+)*@[A-Za-z0-9]+(?:[A-Za-z0-9\-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9]+(?:[A-Za-z0-9\-]*[A-Za-z0-9])?)+',address):raise ValueError('Use a supported valid ASCII contact email address.')
    _put(record,email,email+39,_text(address,40))


def _ein(value):
    value=_digits(value,9)
    if value[:2] in {'00','07','08','09','17','18','19','28','29','49','69','70','78','79','89'}:raise ValueError('The supplied EIN prefix is not supported by SSA.')
    return value


def render(value):
    if not isinstance(value,dict) or set(value)!={'tax_year','annual_totals_reviewed','no_optional_amounts','original_domestic_regular','submitter','employer','employees'}:raise ValueError('Use the complete annual SSA filing input structure.')
    if type(value['tax_year']) is not int or value['tax_year']!=2026 or any(value[key] is not True for key in ('annual_totals_reviewed','no_optional_amounts','original_domestic_regular')):
        raise ValueError('Reviewed original domestic regular 2026 annual data with no omitted optional amounts is required.')
    submitter=value['submitter'];employer=value['employer'];workers=value['employees']
    if not isinstance(submitter,dict) or set(submitter)!=ADDRESS|{'ein','bso_user_id','software_code','vendor_code','preparer_code'}:raise ValueError('Provide the complete submitter registration/contact record.')
    if not isinstance(employer,dict) or set(employer)!=ADDRESS|{'ein','kind','signature_pin'}:raise ValueError('Provide the complete employer registration/contact record.')
    if not isinstance(workers,list) or not 1<=len(workers)<=10000:raise ValueError('Supply between one and 10,000 reviewed employee records per file.')
    ra=_record('RA');_put(ra,3,11,_ein(submitter['ein']));_put(ra,12,19,_text(submitter['bso_user_id'],8))
    if not re.fullmatch(r'[A-Za-z0-9]{8}',submitter['bso_user_id']):raise ValueError('Supply the assigned eight-character BSO user identifier.')
    code=submitter['software_code']
    if code not in ('98','99'):raise ValueError('Review and explicitly select the SSA software classification.')
    vendor=_digits(submitter['vendor_code'],4) if code=='99' else _text(submitter['vendor_code'],4,False)
    if code=='98' and submitter['vendor_code']:raise ValueError('In-house classification must have a blank vendor code.')
    _put(ra,20,23,vendor);_put(ra,29,29,'0');_put(ra,36,37,code)
    _address(ra,submitter,[('name',38,57,True),('location',95,22,False),('delivery',117,22,True),('city',139,22,True),('state',161,2,True),('zip',163,5,True),('zip_extension',168,4,False)])
    _address(ra,submitter,[('name',217,57,True),('location',274,22,False),('delivery',296,22,True),('city',318,22,True),('state',340,2,True),('zip',342,5,True),('zip_extension',347,4,False)])
    _contact(ra,submitter,396,423,446)
    if submitter['preparer_code'] not in ('A','L','S','P','O'):raise ValueError('Choose a supported SSA preparer classification.')
    _put(ra,500,500,submitter['preparer_code'])
    re_record=_record('RE');_put(re_record,3,6,'2026');_put(re_record,8,16,_ein(employer['ein']));_put(re_record,26,26,'0')
    _address(re_record,employer,[('name',40,57,True),('location',97,22,False),('delivery',119,22,True),('city',141,22,True),('state',163,2,True),('zip',165,5,True),('zip_extension',170,4,False)])
    if employer['kind'] not in ('F','S','T','Y','N'):raise ValueError('Choose a supported domestic kind of employer.')
    _put(re_record,174,174,employer['kind']);_put(re_record,219,219,'R');_put(re_record,221,221,'0');_contact(re_record,employer,222,249,279)
    pin=employer['signature_pin']
    if pin:
        if not isinstance(pin,str) or not re.fullmatch(r'S-[0-9]{6}-[0-9]',pin):raise ValueError('The employer signature PIN format is invalid.')
        digits=pin[2:8]+pin[-1];total=0
        for i,c in enumerate(reversed(digits)):
            d=int(c)*(2 if i%2 else 1);total+=d-9 if d>9 else d
        if total%10:raise ValueError('The employer signature PIN checksum is invalid.')
    _put(re_record,319,328,_text(pin,10,False))
    records=[ra,re_record];totals=[0]*6;seen=set()
    for worker in workers:
        if not isinstance(worker,dict) or set(worker)!=EMPLOYEE:raise ValueError('Provide complete employee annual filing records without unsupported fields.')
        ssn=_digits(worker['ssn'],9)
        if ssn.startswith(('000','666','9')) or ssn[3:5]=='00' or ssn[5:]=='0000' or ssn in seen:raise ValueError('Missing, invalid or duplicate SSNs require external resolution before this export.')
        seen.add(ssn);rw=_record('RW');_put(rw,3,11,ssn)
        _address(rw,worker,[('first',12,15,True),('middle',27,15,False),('last',42,20,True),('suffix',62,4,False),('location',66,22,False),('delivery',88,22,True),('city',110,22,True),('state',132,2,True),('zip',134,5,True),('zip_extension',139,4,False)])
        for i,key in enumerate(AMOUNTS):
            amount=worker[key];_put(rw,188+i*11,198+i*11,_money(amount,11));totals[i]+=amount
        if worker['ss_wages_minor']>18450000 or worker['ss_tax_minor']>1143900:raise ValueError('The 2026 Social Security annual cap is exceeded.')
        # Unsupported optional monetary fields are zero, reserved fields blank.
        for start in (254,276,287,298,309,320,331,353,364,375,386,408,419,430,441,452,463,474):_put(rw,start,start+10,'0'*11)
        for start in (486,488,489):_put(rw,start,start,'0')
        records.append(rw)
    rt=_record('RT');_put(rt,3,9,_money(len(workers),7))
    for i,total in enumerate(totals):_put(rt,10+i*15,24+i*15,_money(total,15))
    for start in (100,130,145,160,175,190,205,235,250,265,280,295,310,325,340,355,370,385,400):_put(rt,start,start+14,'0'*15)
    rf=_record('RF');_put(rf,8,16,_money(len(workers),9));records.extend((rt,rf))
    result=('\r\n'.join(''.join(row) for row in records)+'\r\n').encode('ascii')
    assert all(len(row)==512 for row in result.splitlines())
    return result


def write_export(value,target):
    content=render(value);target=Path(target)
    if target.is_symlink() or not target.parent.is_dir() or target.parent.is_symlink():raise ValueError('Choose a private ordinary output directory.')
    if os.name=='posix' and target.parent.stat().st_mode & 0o077:raise ValueError('The output directory must be private (0700).')
    descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(descriptor,'wb') as output:output.write(content);output.flush();os.fsync(output.fileno())
    return {'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),'employee_records':len(value['employees']),'authority_accepted':False,'online_submission_performed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    if args.input.is_symlink() or args.input.stat().st_size>20000000:raise SystemExit('Use a bounded ordinary private input file.')
    if os.name=='posix' and args.input.stat().st_mode & 0o077:raise SystemExit('Filing input must be private (0600).')
    try:result=write_export(json.loads(args.input.read_text()),args.output)
    except (ValueError,OSError):raise SystemExit('Export failed validation or private file checks. No government submission was attempted.') from None
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
