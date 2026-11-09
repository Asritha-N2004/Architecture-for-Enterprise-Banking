from sqlalchemy import select, func
from app.models import Grant, Customer, Account


def test_personal_sample_records_are_scoped_and_idempotent(bank):
    client, factory = bank
    def register(name):
        result = client.post('/api/v1/auth/register', json={'username': name, 'password': 'private-test-password'})
        return {'Authorization': 'Bearer ' + result.json()['access_token']}
    first, second = register('sample-user-one'), register('sample-user-two')
    result = client.post('/api/v1/demo/provision', headers=first)
    assert result.status_code == 200, result.text
    ids = result.json()
    assert ids['mode'] == 'SIMULATION'
    assert client.post('/api/v1/demo/provision', headers=first).json() == ids
    assert client.get('/api/v1/accounts', headers=first).json()[0]['id'] == ids['account_id']
    assert client.get('/api/v1/customers', headers=first).json()[0]['id'] == ids['customer_id']
    assert client.get('/api/v1/accounts', headers=second).json() == []
    assert client.get(f"/api/v1/accounts/{ids['account_id']}/balance", headers=second).status_code == 404
    inquiry = client.post('/api/v1/workflows', headers=first, json={'operation': 'balance', 'account_id': ids['account_id']})
    assert inquiry.status_code == 200, inquiry.text
    assert inquiry.json()['result']['execution_result']['data']['balance'] == '50000.00'
    assert client.post('/api/v1/payments/prepare', headers=first, json={'account_id': ids['account_id'], 'beneficiary_id': 'BEN-0001', 'amount': '10.00', 'currency': 'INR', 'idempotency_key': 'not-permitted-payment'}).status_code == 403


def test_sample_provision_requires_authentication(bank):
    client, _ = bank
    assert client.post('/api/v1/demo/provision').status_code == 401
