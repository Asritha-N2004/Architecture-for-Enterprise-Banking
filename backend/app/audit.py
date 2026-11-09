import hashlib
import json
from contextvars import ContextVar
from sqlalchemy import select, update
from app.models import AuditHead, AuditEvent, now, uid

correlation = ContextVar('correlation', default='local')


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def payload(event):
    return {key: getattr(event, key) for key in ('id', 'org_id', 'actor_id', 'action', 'resource', 'result', 'correlation_id', 'created_at', 'previous_hash')}


def record(db, user, action, resource, result='ALLOW'):
    # Updating the singleton serializes append operations on PostgreSQL and SQLite.
    db.execute(update(AuditHead).where(AuditHead.id == 1).values(sequence=AuditHead.sequence + 1))
    head = db.scalar(select(AuditHead).where(AuditHead.id == 1).execution_options(populate_existing=True))
    event = AuditEvent(id=head.sequence, org_id=user.org_id, actor_id=user.id, action=action,
                       resource=resource, result=result, correlation_id=correlation.get(),
                       created_at=now(), previous_hash=head.digest)
    event.digest = digest(payload(event))
    head.digest = event.digest
    db.add(event)
    db.flush()
    return event.id


def verify(db):
    previous = '0' * 64
    count = 0
    for event in db.scalars(select(AuditEvent).order_by(AuditEvent.id)):
        count += 1
        if event.id != count or event.previous_hash != previous or event.digest != digest(payload(event)):
            return False
        previous = event.digest
    head = db.get(AuditHead, 1)
    return bool(head and head.digest == previous and head.sequence == count)
