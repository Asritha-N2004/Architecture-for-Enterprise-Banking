from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import String, ForeignKey, Numeric, JSON, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


class Organization(Base):
    __tablename__ = 'organizations'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str]


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str]
    role: Mapped[str]
    active: Mapped[bool] = mapped_column(default=True)


class UserSession(Base):
    __tablename__ = 'user_sessions'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires: Mapped[int]
    revoked: Mapped[bool] = mapped_column(default=False)


class Customer(Base):
    __tablename__ = 'customers'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    display_name: Mapped[str]
    kyc_status: Mapped[str] = mapped_column(default='REVIEW_REQUIRED')


class Grant(Base):
    __tablename__ = 'customer_access_grants'
    __table_args__ = (UniqueConstraint('user_id', 'customer_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    customer_id: Mapped[str] = mapped_column(ForeignKey('customers.id'))


class Account(Base):
    __tablename__ = 'bank_accounts'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey('customers.id'), index=True)
    currency: Mapped[str] = mapped_column(String(3), default='INR')
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(default='ACTIVE')


class Beneficiary(Base):
    __tablename__ = 'beneficiaries'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey('customers.id'))
    name: Mapped[str]
    verified: Mapped[bool] = mapped_column(default=True)


class Payment(Base):
    __tablename__ = 'payment_instructions'
    __table_args__ = (UniqueConstraint('org_id', 'maker_id', 'idempotency_key'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    maker_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    account_id: Mapped[str] = mapped_column(ForeignKey('bank_accounts.id'))
    beneficiary_id: Mapped[str] = mapped_column(ForeignKey('beneficiaries.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    fee: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    idempotency_key: Mapped[str]
    fingerprint: Mapped[str]
    policy_version: Mapped[str]
    status: Mapped[str] = mapped_column(default='PENDING_APPROVAL')
    required_approvals: Mapped[int]
    expires: Mapped[int]
    created_at: Mapped[str] = mapped_column(default=now)


class Approval(Base):
    __tablename__ = 'payment_approvals'
    __table_args__ = (UniqueConstraint('payment_id', 'approver_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    payment_id: Mapped[str] = mapped_column(ForeignKey('payment_instructions.id'))
    approver_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    fingerprint: Mapped[str]
    decision: Mapped[str]
    comment: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)


class Execution(Base):
    __tablename__ = 'payment_execution_records'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    payment_id: Mapped[str] = mapped_column(ForeignKey('payment_instructions.id'), unique=True)
    mode: Mapped[str] = mapped_column(default='SIMULATION')
    created_at: Mapped[str] = mapped_column(default=now)


class AuditHead(Base):
    __tablename__ = 'audit_head'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sequence: Mapped[int] = mapped_column(default=0)
    digest: Mapped[str] = mapped_column(default='0' * 64)


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    org_id: Mapped[str] = mapped_column(String, index=True)
    actor_id: Mapped[str]
    action: Mapped[str]
    resource: Mapped[str]
    result: Mapped[str]
    correlation_id: Mapped[str]
    created_at: Mapped[str]
    previous_hash: Mapped[str]
    digest: Mapped[str]


class Workflow(Base):
    __tablename__ = 'banking_workflows'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    kind: Mapped[str]
    status: Mapped[str]
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)
