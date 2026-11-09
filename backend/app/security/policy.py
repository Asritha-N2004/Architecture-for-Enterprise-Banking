from dataclasses import dataclass
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Customer, Account, Grant, User

ROLES = {
    'BANK_ADMIN': {'customer.read', 'account.read', 'payment.prepare', 'payment.execute', 'audit.read', 'registry.read'},
    'OPERATIONS_MANAGER': {'customer.read', 'account.read', 'payment.approve', 'payment.execute', 'registry.read'},
    'BANK_TELLER': {'customer.read', 'account.read', 'payment.prepare'},
    'CUSTOMER_SUPPORT': {'customer.read', 'account.read'},
    'COMPLIANCE_OFFICER': {'customer.read', 'compliance.review'},
    'FRAUD_ANALYST': {'account.read', 'fraud.review'},
    'FINANCIAL_CONTROLLER': {'account.read', 'payment.approve', 'payment.execute', 'audit.read'},
    'AUDITOR': {'audit.read', 'registry.read'},
    'READ_ONLY_USER': {'customer.read', 'account.read'},
}


@dataclass(frozen=True)
class Decision:
    decision: str
    permission: str
    reason: str
    policy: str = 'deny-by-default-v1'


def evaluate(user: User, permission: str) -> Decision:
    allowed = user.active and permission in ROLES.get(user.role, set())
    return Decision('ALLOW' if allowed else 'DENY', permission, 'Role permits operation' if allowed else 'Permission absent')


def require(user, permission):
    if evaluate(user, permission).decision != 'ALLOW':
        raise HTTPException(403, 'Operation not permitted')


def customer_scope(db, user, customer_id):
    customer = db.get(Customer, customer_id)
    grant = db.scalar(select(Grant).where(Grant.user_id == user.id, Grant.customer_id == customer_id))
    if not customer or customer.org_id != user.org_id or not grant:
        raise HTTPException(404, 'Resource unavailable')
    return customer


def account_scope(db, user, account_id):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, 'Resource unavailable')
    customer_scope(db, user, account.customer_id)
    return account
