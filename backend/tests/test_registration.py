from sqlalchemy import select
from app.models import User, Grant, Organization


def test_registration_creates_isolated_read_only_identity(bank):
    client, factory = bank
    response = client.post('/api/v1/auth/register', json={'username': ' New_User ', 'password': 'private-test-password'})
    assert response.status_code == 201, response.text
    auth = {'Authorization': 'Bearer ' + response.json()['access_token']}
    me = client.get('/api/v1/auth/me', headers=auth).json()
    assert me['username'] == 'new_user'
    assert me['role'] == 'READ_ONLY_USER'
    assert me['organization_id'] not in ('ORG-DEMO', 'ORG-OTHER')
    assert client.get('/api/v1/accounts', headers=auth).json() == []
    assert client.get('/api/v1/accounts/ACC-0001/balance', headers=auth).status_code == 404
    assert client.get('/api/v1/audit/events', headers=auth).status_code == 403
    with factory() as db:
        user = db.scalar(select(User).where(User.username == 'new_user'))
        assert user.password_hash != 'private-test-password'
        assert db.scalar(select(Grant).where(Grant.user_id == user.id)) is None
    assert client.post('/api/v1/auth/login', json={'username': 'new_user', 'password': 'private-test-password'}).status_code == 200


def test_registration_validation_duplicates_and_reserved_names(bank):
    client, _ = bank
    path = '/api/v1/auth/register'
    body = {'username': 'new_user', 'password': 'private-test-password'}
    assert client.post(path, json=body | {'password': 'short'}).status_code == 422
    assert client.post(path, json=body | {'role': 'BANK_ADMIN'}).status_code == 422
    assert client.post(path, json=body | {'org_id': 'ORG-DEMO'}).status_code == 422
    assert client.post(path, json=body | {'username': 'maker'}).status_code == 409
    assert client.post(path, json=body).status_code == 201
    assert client.post(path, json=body | {'username': 'NEW_USER'}).status_code == 409


def test_registration_throttles_account_creation(bank):
    client, _ = bank
    for _ in range(5):
        assert client.post('/api/v1/auth/register', json={'username': 'maker', 'password': 'private-test-password'}).status_code == 409
    assert client.post('/api/v1/auth/register', json={'username': 'another_user', 'password': 'private-test-password'}).status_code == 429


def test_username_can_start_with_numbers_and_contain_spaces(bank):
    client, _ = bank
    body = {'username': '123 Jane.Doe', 'password': 'private-test-password'}
    assert client.post('/api/v1/auth/register', json=body).status_code == 201
    assert client.post('/api/v1/auth/login', json=body).status_code == 200
    assert client.post('/api/v1/auth/register', json=body | {'username': '   '}).status_code == 422


def test_new_account_workflow_denial_is_actionable(bank):
    client, _ = bank
    response = client.post('/api/v1/auth/register', json={'username': 'new-customer', 'password': 'private-test-password'})
    auth = {'Authorization': 'Bearer ' + response.json()['access_token']}
    assert client.get('/api/v1/customers', headers=auth).json() == []
    for operation, field, identifier in [('customer', 'customer_id', 'CUS-0001'), ('balance', 'account_id', 'ACC-0001')]:
        response = client.post('/api/v1/workflows', headers=auth, json={'operation': operation, field: identifier})
        assert response.status_code == 404
        assert 'assign customer access' in response.json()['detail']
        assert 'MCP operation failed' not in response.text
