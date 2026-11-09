from concurrent.futures import ThreadPoolExecutor
from app.models import User, Account, Execution
from app.payments.service import prepare, decide, execute
from app.schemas import PaymentRequest
from sqlalchemy import select, func
from decimal import Decimal


def test_concurrent_execution_debits_exactly_once(bank):
    _, factory = bank
    with factory() as db:
        payment = prepare(db, db.get(User, 'maker'), PaymentRequest(account_id='ACC-0001', beneficiary_id='BEN-0001', amount='20.00', idempotency_key='concurrent-payment'))
        pid = payment['id']
        db.commit()
        decide(db, db.get(User, 'checker'), pid, 'APPROVED', 'Independent review')
        db.commit()

    def run():
        with factory() as db:
            result = execute(db, db.get(User, 'maker'), pid)
            db.commit()
            return result['receipt_id']

    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda _: run(), range(4)))
    assert len(set(receipts)) == 1
    with factory() as db:
        assert db.get(Account, 'ACC-0001').balance == Decimal('1999975.00')
        assert db.scalar(select(func.count()).select_from(Execution)) == 1
