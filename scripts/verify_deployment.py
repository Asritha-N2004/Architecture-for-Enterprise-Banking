"""Exercise the hosted simulation without printing generated credentials or tokens."""
import json
import secrets
import sys
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4
import httpx

base = sys.argv[1].rstrip('/')
if not base.startswith('https://'):
    raise SystemExit('HTTPS deployment URL required')
observed = {'url': base}
with httpx.Client(base_url=base, timeout=90) as client:
    def checked(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            # Only sanitized server detail is reported, never request credentials.
            raise RuntimeError(f'{path}: HTTP {response.status_code}; {response.text[:300]}')
        return response
    class Assets(HTMLParser):
        paths = []
        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            if tag == 'script' and attrs.get('src', '').startswith('/'):
                self.paths.append(attrs['src'])
            if tag == 'link' and attrs.get('rel') == 'stylesheet' and attrs.get('href', '').startswith('/'):
                self.paths.append(attrs['href'])
    assets = Assets()
    assets.feed(checked('GET', '/').text)
    for path in assets.paths:
        response = checked('GET', path)
        expected = 'javascript' if path.endswith('.js') else 'text/css'
        content_type = response.headers.get('content-type', '')
        if expected not in content_type:
            raise RuntimeError(f'Asset {path}: unexpected content type {content_type}')
    observed['frontend_assets'] = 'passed'
    assert checked('GET', '/api/v1/health').json()['mode'] == 'SIMULATION'
    assert checked('GET', '/api/v1/health/database').json()['status'] == 'ok'
    observed['database_health'] = 'ok'
    identity = {'username': 'deploy-check-' + uuid4().hex[:12], 'password': secrets.token_urlsafe(24)}
    token = checked('POST', '/api/v1/auth/register', json=identity).json()['access_token']
    client.headers['Authorization'] = 'Bearer ' + token
    assert checked('GET', '/api/v1/auth/me').json()['role'] == 'READ_ONLY_USER'
    observed['registration_and_authentication'] = 'passed'
    records = checked('POST', '/api/v1/demo/provision').json()
    assert checked('POST', '/api/v1/demo/provision').json() == records
    observed['sample_provisioning_and_idempotency'] = 'passed'
    workflow = checked('POST', '/api/v1/workflows', json={'operation': 'balance', 'account_id': records['account_id']}).json()
    assert workflow['status'] == 'COMPLETED'
    data = workflow['result']['execution_result']['data']
    assert data['balance'] == '50000.00' and data['currency'] == 'INR'
    observed['real_mcp_balance_inquiry'] = 'passed'
    observed['workflow_id'] = workflow['id']
    observed['synthetic_balance'] = data['balance']
    observed['currency'] = data['currency']
    checked('POST', '/api/v1/auth/logout')
    assert client.get('/api/v1/auth/me').status_code == 401
    observed['session_revocation'] = 'passed'
    # The explicit synthetic smoke identity and its immutable audit history remain.
output = Path(__file__).resolve().parents[1] / 'evaluation/results/vercel_smoke.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(observed, indent=2), encoding='utf-8')
print(json.dumps(observed, indent=2))
