"""Explicit local provisioning. Passwords are supplied through the environment."""
import os
from sqlalchemy import select
from app.database import Session
from app.models import Organization, User, Customer, Grant, Account, Beneficiary, AuditHead
from app.security.auth import passwords


def seed(db, password):
    if db.get(Organization, 'ORG-DEMO'):
        return
    db.add_all([Organization(id='ORG-DEMO', name='Synthetic Bank'), Organization(id='ORG-OTHER', name='Other Synthetic Bank')])
    db.flush()
    for username, role, org in [('maker', 'BANK_ADMIN', 'ORG-DEMO'), ('checker', 'OPERATIONS_MANAGER', 'ORG-DEMO'), ('controller', 'FINANCIAL_CONTROLLER', 'ORG-DEMO'), ('reader', 'READ_ONLY_USER', 'ORG-DEMO'), ('auditor', 'AUDITOR', 'ORG-DEMO'), ('outsider', 'BANK_ADMIN', 'ORG-OTHER')]:
        db.add(User(id=username, username=username, org_id=org, role=role, password_hash=passwords.hash(password)))
    db.add_all([Customer(id='CUS-0001', org_id='ORG-DEMO', display_name='Synthetic Customer 001'), Customer(id='CUS-0002', org_id='ORG-OTHER', display_name='Synthetic Customer 002')])
    db.flush()
    for username in ['maker', 'checker', 'controller', 'reader']:
        db.add(Grant(user_id=username, customer_id='CUS-0001'))
    db.add(Grant(user_id='outsider', customer_id='CUS-0002'))
    db.add_all([Account(id='ACC-0001', customer_id='CUS-0001', balance=2000000), Account(id='ACC-0002', customer_id='CUS-0002', balance=1000000), Beneficiary(id='BEN-0001', customer_id='CUS-0001', name='Synthetic Supplier')])
    if not db.get(AuditHead, 1):
        db.add(AuditHead(id=1, sequence=0, digest='0' * 64))
    db.commit()


if __name__ == '__main__':
    password = os.environ.get('DEMO_PASSWORD', '')
    if len(password) < 12:
        raise SystemExit('Set DEMO_PASSWORD to at least 12 characters. No default password is provided.')
    with Session() as db:
        seed(db, password)
    print('Synthetic users provisioned. No real banking records used.')
