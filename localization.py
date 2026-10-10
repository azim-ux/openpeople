"""Offline country/region metadata; this module does not implement tax law."""
import json
from pathlib import Path
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError

CATALOG=json.loads(Path(__file__).with_name('countries.json').read_text())
COUNTRIES={row['code']:row for row in CATALOG['countries']}
CURRENCIES=sorted({row['currency'] for row in COUNTRIES.values()}-{'XXX'})

def currency_digits(currency):
    return CATALOG['currency_digits'].get(currency,CATALOG['currency_digits']['DEFAULT'])

def profile(data,fallback=None):
    from server import APIError
    fallback=dict(fallback or {})
    country=data.get('country',fallback.get('country','IN'))
    if not isinstance(country,str) or country not in COUNTRIES:raise APIError(400,'Choose a supported country or region.')
    currency=data.get('currency',fallback.get('currency',COUNTRIES[country]['currency']))
    if currency not in CURRENCIES:raise APIError(400,'Choose an operating currency for this country.')
    zone=data.get('timezone',fallback.get('timezone',COUNTRIES[country]['timezone']))
    if not isinstance(zone,str) or len(zone)>100:raise APIError(400,'Choose a valid IANA timezone.')
    try:ZoneInfo(zone)
    except (ZoneInfoNotFoundError,ValueError) as error:raise APIError(400,'Choose a valid IANA timezone.') from error
    return {'country':country,'currency':currency,'timezone':zone}


def zone(employee):
    return ZoneInfo(employee['timezone'] if 'timezone' in employee.keys() else 'Asia/Kolkata')

def validate_work_week(value):
    from server import APIError
    if not isinstance(value,list) or not value or len(value)>7 or any(type(day) is not int or not 0<=day<=6 for day in value) or len(set(value))!=len(value):raise APIError(400,'Choose one or more unique working weekdays.')
    return sorted(value)
