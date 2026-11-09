"""Run actual isolated control tests; emit observed counts, never baseline claims."""
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(__file__).resolve().parents[1]
output = root / 'evaluation' / 'results'
output.mkdir(exist_ok=True)
started = time.perf_counter()
report = output / 'controls.xml'
result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--basetemp=.test-tmp-evaluation', f'--junitxml={report}'], cwd=root)
observed = {'label': 'local control test suite, not E1–E6 comparison', 'elapsed_seconds': time.perf_counter() - started, 'exit_code': result.returncode}
if report.exists():
    cases = list(ET.parse(report).getroot().iter('testcase'))
    observed.update(tests=len(cases), failures=sum(case.find('failure') is not None for case in cases), errors=sum(case.find('error') is not None for case in cases), skipped=sum(case.find('skipped') is not None for case in cases))
(output / 'controls.json').write_text(json.dumps(observed, indent=2), encoding='utf-8')
print(json.dumps(observed, indent=2))
raise SystemExit(result.returncode)
