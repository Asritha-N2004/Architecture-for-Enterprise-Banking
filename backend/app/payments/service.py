import time
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, update
from app.models import Payment, Approval, Execution, Beneficiary, Account
from app.schemas import PaymentRequest
from app.security.policy import require, account_scope, customer_scope
from app.audit import digest, record
from app.core.config import settings


def fingerprint(payment):
    return digest({'account_id': payment.account_id, 'beneficiary_id': payment.beneficiary_id,
                   'amount': format(Decimal(payment.amount), '.2f'), 'currency': payment.currency,
                   'fee': format(Decimal(payment.fee), '.2f'), 'policy': payment.policy_version,
                   'maker': payment.maker_id, 'org': payment.org_id,
                   'required_approvals': payment.required_approvals, 'expires': payment.expires})


def view(payment):
    return {key: str(getattr(payment, key)) for key in ('id', 'account_id', 'beneficiary_id', 'amount', 'fee', 'currency', 'status', 'maker_id', 'required_approvals', 'created_at')} | {'mode': 'SIMULATION'}


def validate(db, user, request):
    account = account_scope(db, user, request.account_id)
    beneficiary = db.get(Beneficiary, request.beneficiary_id)
    if not beneficiary or beneficiary.customer_id != account.customer_id or not beneficiary.verified:
        raise HTTPException(422, 'Beneficiary unavailable or unverified')
    if account.status != 'ACTIVE' or account.currency != request.currency:
        raise HTTPException(422, 'Account status or currency invalid')
    if request.amount > Decimal('1000000'):
        raise HTTPException(422, 'Transaction limit exceeded')
    fee = Decimal('5.00')
    if account.balance < request.amount + fee:
        raise HTTPException(409, 'Insufficient simulation balance')
    return account, fee


def prepare(db, user, request: PaymentRequest):
    require(user, 'payment.prepare')
    # Lock the maker row: concurrent requests with the same key must serialize.
    from app.models import User
    db.execute(update(User).where(User.id == user.id).values(active=User.active))
    existing = db.scalar(select(Payment).where(Payment.org_id == user.org_id, Payment.maker_id == user.id, Payment.idempotency_key == request.idempotency_key))
    if existing:
        if (existing.account_id, existing.beneficiary_id, existing.amount, existing.currency) != (request.account_id, request.beneficiary_id, request.amount, request.currency):
            raise HTTPException(409, 'Idempotency key already used for different instruction')
        account_scope(db, user, existing.account_id)
        return view(existing)
    _, fee = validate(db, user, request)
    payment = Payment(org_id=user.org_id, maker_id=user.id, account_id=request.account_id,
                      beneficiary_id=request.beneficiary_id, amount=request.amount, fee=fee,
                      currency=request.currency, idempotency_key=request.idempotency_key,
                      policy_version=settings.policy_version,
                      required_approvals=2 if request.amount >= Decimal('100000') else 1,
                      expires=int(time.time()) + 3600, fingerprint='')
    payment.fingerprint = fingerprint(payment)
    db.add(payment)
    db.flush()
    record(db, user, 'payment.prepared', payment.id, 'REQUIRE_APPROVAL')
    return view(payment)


def scoped_payment(db, user, payment_id, lock=False):
    if lock:
        db.execute(update(Payment).where(Payment.id == payment_id, Payment.org_id == user.org_id).values(status=Payment.status))
    payment = db.scalar(select(Payment).where(Payment.id == payment_id, Payment.org_id == user.org_id).execution_options(populate_existing=True))
    if not payment:
        raise HTTPException(404, 'Resource unavailable')
    account_scope(db, user, payment.account_id)
    return payment


def current_instruction(payment):
    expected_count = 2 if payment.amount >= Decimal('100000') else 1
    if payment.policy_version != settings.policy_version or payment.fingerprint != fingerprint(payment) or payment.required_approvals != expected_count:
        raise HTTPException(409, 'Instruction or policy changed; create a new approval request')
    if payment.expires <= time.time():
        raise HTTPException(409, 'Approval request expired')


def decide(db, user, payment_id, decision, comment):
    require(user, 'payment.approve')
    payment = scoped_payment(db, user, payment_id, lock=True)
    if payment.maker_id == user.id:
        raise HTTPException(403, 'Maker cannot approve or reject own instruction')
    current_instruction(payment)
    if payment.status != 'PENDING_APPROVAL':
        raise HTTPException(409, 'Payment is not pending approval')
    previous = db.scalar(select(Approval).where(Approval.payment_id == payment.id, Approval.approver_id == user.id))
    if previous:
        raise HTTPException(409, 'Approver already recorded a decision')
    db.add(Approval(payment_id=payment.id, approver_id=user.id, fingerprint=payment.fingerprint, decision=decision, comment=comment))
    db.flush()
    approvals = list(db.scalars(select(Approval).where(Approval.payment_id == payment.id, Approval.decision == 'APPROVED')))
    if decision == 'REJECTED':
        payment.status = 'REJECTED'
    elif len(approvals) >= payment.required_approvals:
        payment.status = 'APPROVED'
    record(db, user, 'payment.' + decision.lower(), payment.id)
    return view(payment)


def execute(db, user, payment_id):
    require(user, 'payment.execute')
    payment = scoped_payment(db, user, payment_id, lock=True)
    current_instruction(payment)
    # Approval permissions and grants are rechecked at execution time.
    from app.models import User
    approvals = list(db.scalars(select(Approval).where(Approval.payment_id == payment.id, Approval.decision == 'APPROVED', Approval.fingerprint == payment.fingerprint)))
    valid = set()
    for approval in approvals:
        approver = db.get(User, approval.approver_id)
        if approver and approver.org_id == payment.org_id and approver.id != payment.maker_id:
            try:
                require(approver, 'payment.approve')
                account_scope(db, approver, payment.account_id)
                valid.add(approver.id)
            except HTTPException:
                pass
    if len(valid) < payment.required_approvals:
        raise HTTPException(409, 'Valid independent approvals required')
    existing = db.scalar(select(Execution).where(Execution.payment_id == payment.id))
    if existing:
        record(db, user, 'payment.replay_prevented', payment.id)
        return view(payment) | {'receipt_id': existing.id}
    if payment.status != 'APPROVED':
        raise HTTPException(409, 'Payment is not approved')
    request = PaymentRequest(account_id=payment.account_id, beneficiary_id=payment.beneficiary_id,
                             amount=payment.amount, currency=payment.currency, idempotency_key=payment.idempotency_key)
    validate(db, user, request)
    total = payment.amount + payment.fee
    changed = db.execute(update(Account).where(Account.id == payment.account_id, Account.status == 'ACTIVE', Account.currency == payment.currency, Account.balance >= total).values(balance=Account.balance - total))
    if changed.rowcount != 1:
        raise HTTPException(409, 'Account changed or insufficient balance')
    execution = Execution(payment_id=payment.id)
    db.add(execution)
    payment.status = 'SIMULATED'
    db.flush()
    record(db, user, 'payment.simulated', payment.id)
    return view(payment) | {'receipt_id': execution.id}
