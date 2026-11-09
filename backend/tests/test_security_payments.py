from decimal import Decimal
import time
import jwt
import pytest
from sqlalchemy import select, text
from app.models import Account, Payment, Approval, User, AuditEvent
from app.core.config import settings
from conftest import headers

REQUEST = {'account_id': 'ACC-0001', 'beneficiary_id': 'BEN-0001', 'amount': '1250.00', 'currency': 'INR', 'idempotency_key': 'test-payment-001'}


def test_auth_scope_and_revocation(bank):
    client, _ = bank
    assert client.get('/api/v1/accounts').status_code == 401
    auth = headers(client)
    assert client.get('/api/v1/accounts/ACC-0002/balance', headers=auth).status_code == 404
    assert len(client.get('/api/v1/accounts', headers=auth).json()) == 1
    assert client.post('/api/v1/auth/logout', headers=auth).status_code == 200
    assert client.get('/api/v1/auth/me', headers=auth).status_code == 401


@pytest.mark.parametrize('claim,value', [('aud', 'wrong'), ('iss', 'wrong'), ('exp', 1)])
def test_jwt_claim_validation(bank, claim, value):
    client, _ = bank
    auth = headers(client)
    token = auth['Authorization'].split()[1]
    payload = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'], audience=settings.audience)
    payload[claim] = value
    forged = jwt.encode(payload, settings.jwt_secret, algorithm='HS256')
    assert client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + forged}).status_code == 401


def test_invalid_signature_and_privilege_escalation(bank):
    client, _ = bank
    assert client.get('/api/v1/accounts', headers={'Authorization': 'Bearer invalid'}).status_code == 401
    auth = headers(client, 'reader')
    assert client.post('/api/v1/payments/prepare', headers=auth, json=REQUEST).status_code == 403
    assert client.get('/api/v1/audit/events', headers=auth).status_code == 403


def test_payment_lifecycle_and_idempotency(bank):
    client, factory = bank
    maker, checker = headers(client), headers(client, 'checker')
    prepared = client.post('/api/v1/payments/prepare', headers=maker, json=REQUEST)
    assert prepared.status_code == 200, prepared.text
    pid = prepared.json()['id']
    assert client.post('/api/v1/payments/prepare', headers=maker, json=REQUEST).json()['id'] == pid
    assert client.post('/api/v1/payments/prepare', headers=maker, json=REQUEST | {'amount': '2.00'}).status_code == 409
    assert client.post(f'/api/v1/payments/{pid}/execute', headers=maker).status_code == 409
    assert client.post(f'/api/v1/approvals/{pid}/approve', headers=maker, json={'comment': 'Self approval'}).status_code == 403
    assert client.post(f'/api/v1/approvals/{pid}/approve', headers=checker, json={'comment': 'Reviewed synthetic evidence'}).json()['status'] == 'APPROVED'
    first = client.post(f'/api/v1/payments/{pid}/execute', headers=maker)
    second = client.post(f'/api/v1/payments/{pid}/execute', headers=maker)
    assert first.status_code == second.status_code == 200
    assert first.json()['receipt_id'] == second.json()['receipt_id']
    with factory() as db:
        assert db.get(Account, 'ACC-0001').balance == Decimal('1998745.00')
    assert client.get('/api/v1/audit/verify', headers=maker).json()['valid'] is True


def test_dual_approval_and_distinct_checkers(bank):
    client, _ = bank
    maker, checker, controller = headers(client), headers(client, 'checker'), headers(client, 'controller')
    pid = client.post('/api/v1/payments/prepare', headers=maker, json=REQUEST | {'amount': '100000.00'}).json()['id']
    path = f'/api/v1/approvals/{pid}/approve'
    assert client.post(path, headers=checker, json={'comment': 'First review'}).json()['status'] == 'PENDING_APPROVAL'
    assert client.post(path, headers=checker, json={'comment': 'Duplicate review'}).status_code == 409
    assert client.post(f'/api/v1/payments/{pid}/execute', headers=maker).status_code == 409
    assert client.post(path, headers=controller, json={'comment': 'Second review'}).json()['status'] == 'APPROVED'
    assert client.post(f'/api/v1/payments/{pid}/execute', headers=maker).json()['mode'] == 'SIMULATION'


@pytest.mark.parametrize('field,value', [('amount', Decimal('50.00')), ('beneficiary_id', 'BEN-9999'), ('policy_version', 'altered'), ('expires', 1)])
def test_approval_bound_to_exact_instruction(bank, field, value):
    client, factory = bank
    maker, checker = headers(client), headers(client, 'checker')
    pid = client.post('/api/v1/payments/prepare', headers=maker, json=REQUEST).json()['id']
    client.post(f'/api/v1/approvals/{pid}/approve', headers=checker, json={'comment': 'Reviewed evidence'})
    # Represent a privileged or compromised persistence-layer mutation.
    with factory() as db:
        if field == 'beneficiary_id':
            value = 'BEN-0001'  # alter to a different valid target via account id below
            setattr(db.get(Payment, pid), 'account_id', 'ACC-0002')
        else:
            setattr(db.get(Payment, pid), field, value)
        db.commit()
    assert client.post(f'/api/v1/payments/{pid}/execute', headers=maker).status_code in (404, 409)


def test_current_approver_permissions_rechecked(bank):
    client, factory = bank
    maker, checker = headers(client), headers(client, 'checker')
    pid = client.post('/api/v1/payments/prepare', headers=maker, json=REQUEST).json()['id']
    client.post(f'/api/v1/approvals/{pid}/approve', headers=checker, json={'comment': 'Reviewed evidence'})
    with factory() as db:
        db.get(User, 'checker').active = False
        db.commit()
    assert client.post(f'/api/v1/payments/{pid}/execute', headers=maker).status_code == 409


@pytest.mark.parametrize('amount', ['0', '-1', '0.001', '1000000.01', 'NaN', 'Infinity'])
def test_malformed_financial_values(bank, amount):
    client, _ = bank
    assert client.post('/api/v1/payments/prepare', headers=headers(client), json=REQUEST | {'amount': amount}).status_code == 422


def test_audit_append_only_and_tamper_detection(bank):
    client, factory = bank
    auth = headers(client)
    with factory() as db:
        with pytest.raises(Exception):
            db.execute(text("UPDATE audit_events SET result='changed'"))
        db.rollback()
        with pytest.raises(Exception):
            db.execute(text('DELETE FROM audit_events'))
        db.rollback()
    assert client.get('/api/v1/audit/verify', headers=auth).json()['valid']


def test_refresh_rotates_and_rejects_old_session(bank):
    client, _ = bank
    auth = headers(client)
    refreshed = client.post('/api/v1/auth/refresh', headers=auth)
    assert refreshed.status_code == 200
    assert client.get('/api/v1/auth/me', headers=auth).status_code == 401
    assert client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + refreshed.json()['access_token']}).status_code == 200
