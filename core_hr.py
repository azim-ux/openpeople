"""Process-selected product scope, enforced before API dispatch or replay."""
import re

PROFILES = ('full', 'core-hr')
ROLES = ('employee', 'manager', 'hr', 'auditor')
PAGES = ('overview', 'people', 'organization', 'leave', 'attendance', 'onboarding',
         'reports', 'notifications', 'security', 'audit', 'settings', 'backup')
DISABLED_STATE = ('goals', 'expenses', 'candidates', 'benefit_plans', 'benefit_enrollments',
                  'courses', 'course_assignments', 'pay_runs', 'payroll_access', 'payslips',
                  'legal_entities', 'cost_centers', 'employee_assignments', 'filing_packets',
                  'pay_groups', 'pay_group_members')
POLICIES = {'leave_policy', 'leave_accrual', 'leave_limits', 'require_mfa'}
EXACT = {'GET': {'session', 'state', 'countries', 'changes', 'health/live', 'security',
                 'sessions', 'audit/export', 'audit/verify', 'reports', 'backup/status', 'operations',
                 'sso/start', 'sso/callback'},
         'POST': {'setup', 'login', 'logout', 'activity', 'employees', 'leave', 'attendance',
                  'attendance_corrections', 'holidays', 'leave_allocations', 'policies',
                  'password', 'mfa/begin', 'mfa/confirm', 'mfa/verify', 'mfa/recovery-codes', 'backup/run'}}


def enabled(store):
    return getattr(store, 'product_profile', 'full') == 'core-hr'


def contract(store):
    if not enabled(store):return {'profile': 'full', 'label': 'Full feature preview'}
    return {'profile': 'core-hr', 'label': 'Core HR', 'pages': list(PAGES), 'roles': list(ROLES),
            'payroll_mode': 'External payroll system', 'scope': 'One organisation, one authoritative server',
            'production_acceptance_required': True}


def enforce(store, path, method, data, query):
    from server import APIError
    if not enabled(store):return
    route = path.removeprefix('/api/')
    allowed = route in EXACT.get(method, set()) or method == 'PATCH' and bool(
        re.fullmatch(r'(employees|leave|tasks|notifications|attendance_corrections)/[0-9]{1,19}|sessions/[0-9a-f]{32}', route))
    if not allowed:raise APIError(404, 'This workflow is unavailable in the Core HR release.')
    if route == 'reports' and query.get('entity', ['employees'])[0] not in ('employees', 'leave', 'attendance'):
        raise APIError(404, 'This report is unavailable in the Core HR release.')
    if (route == 'employees' or route.startswith('employees/')) and 'role' in data and data['role'] not in ROLES:
        raise APIError(400, 'Choose an employee, manager, HR or auditor role for Core HR.')
    if route == 'policies' and set(data) - POLICIES:
        raise APIError(400, 'Only leave and MFA policies are available in Core HR.')
    if route == 'setup' and data.get('include_samples'):
        raise APIError(400, 'Use a separate full-profile workspace for fictional sample records.')


def project_state(store, result):
    result['product'] = contract(store)
    if enabled(store):
        for key in DISABLED_STATE:result[key] = []
        result['policies'] = {key: value for key, value in result['policies'].items() if key in POLICIES}
    return result
