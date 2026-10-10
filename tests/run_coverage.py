"""Measure backend line coverage using Python's standard-library trace module."""
import sys
import json
import re
import threading
import trace
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
modules=['server','workspace','identity','backup','serving','manage','localization','payroll','cloud_backup','statutory','statutory_uk','enterprise','access','audit_integrity','government_submission','service_config']
modules.extend(['pay_periods','operations'])
modules.append('service_runner')
modules.append('provisioning')
modules.extend(['core_hr','core_acceptance'])
included={root / (name+'.py') for name in modules}
included_filenames={str(path) for path in included}
tracer = trace.Trace(count=True, trace=False)


def trace_backend(frame,event,arg):
    # trace's default ignore cache uses basenames: app server.py can collide
    # with waitress/server.py. Trace only our exact files, including when the
    # source is extracted elsewhere from the installed Python environment.
    if event == 'call' and frame.f_code.co_filename in included_filenames:
        return tracer.localtrace
    return None


tracer.globaltrace=trace_backend


def run():
    suite = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern='test_*.py')
    return unittest.TextTestRunner(verbosity=1).run(suite)


threading.settrace(tracer.globaltrace)
result = tracer.runfunc(run)
threading.settrace(None)
measured=tracer.results()
assert all(Path(filename).resolve() in included for filename,_ in measured.counts), 'Coverage traced a file outside the backend allowlist.'
measured.counts={key:value for key,value in measured.counts.items() if Path(key[0]).resolve() in included}
measured.write_results(show_missing=True, summary=True, coverdir=str(root / 'coverage'))
report={}
for name in modules:
    lines=(root/'coverage'/(name+'.cover')).read_text().splitlines()
    hits=sum(bool(re.match(r'^\s*\d+:',line)) for line in lines)
    missing=sum(line.startswith('>>>>>>') for line in lines)
    report[name]={'covered_lines':hits,'executable_lines':hits+missing,'percent':round(100*hits/(hits+missing),2)}
total=sum(item['executable_lines'] for item in report.values())
covered=sum(item['covered_lines'] for item in report.values())
percent=round(100*covered/total,2)
(root/'coverage'/'summary.json').write_text(json.dumps({'backend':report,'total_percent':percent,'tests':result.testsRun,'passed':result.wasSuccessful()},indent=2)+'\n')
print(f'Combined backend line coverage: {percent}% ({covered}/{total})')
sys.exit(0 if result.wasSuccessful() and percent>=80 else 1)
