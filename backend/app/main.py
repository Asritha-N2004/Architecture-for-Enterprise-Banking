import time
from collections import defaultdict, deque
from uuid import uuid4
from dataclasses import asdict
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from app.database import get_db
from app.models import User, Organization, Account, Customer, Payment, Approval, Execution, Workflow, AuditEvent
from app.schemas import Login, Register, PaymentRequest, ApprovalRequest, WorkflowRequest
from app.security.auth import current_user, authenticate, issue, passwords, dummy_hash, bearer
from app.security.policy import require, customer_scope, account_scope, ROLES
from app.audit import record, verify, correlation
from app.payments.service import prepare, view, scoped_payment, decide, execute
from app.mcp.registry import registry, SERVERS

app = FastAPI(title='Secure MCP Banking — simulation', version='0.1.0')
login_attempts = defaultdict(deque)
registration_attempts = defaultdict(deque)


@app.middleware('http')
async def request_context(request: Request, call_next):
    request_id = str(uuid4())
    token = correlation.set(request_id)
    try:
        response = await call_next(request)
        response.headers['X-Correlation-ID'] = request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        return response
    finally:
        correlation.reset(token)


@app.exception_handler(HTTPException)
async def handled(request, error):
    # The transaction that failed has already rolled back. Record metadata only.
    from app.database import Session
    from types import SimpleNamespace
    with Session() as db:
        actor = SimpleNamespace(id='unauthenticated', org_id='unknown')
        credentials = request.headers.get('authorization', '').split(' ', 1)
        if len(credentials) == 2 and credentials[0].lower() == 'bearer':
            try:
                actor = authenticate(db, credentials[1])[0]
            except HTTPException:
                pass
        record(db, actor, 'request.rejected', request.url.path[:200], str(error.status_code))
        db.commit()
    return JSONResponse(status_code=error.status_code, content={'detail': error.detail, 'correlation_id': correlation.get()}, headers=error.headers)


@app.get('/api/v1/health')
def health():
    return {'status': 'ok', 'mode': 'SIMULATION', 'version': '0.1.0'}


@app.get('/api/v1/health/database')
def database_health(db=Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status': 'ok'}


@app.post('/api/v1/auth/login')
def login(body: Login, request: Request, db=Depends(get_db)):
    address = request.client.host if request.client else 'local'
    bucket = login_attempts[address]
    current = time.monotonic()
    while bucket and bucket[0] < current - 60:
        bucket.popleft()
    if len(bucket) >= 10:
        raise HTTPException(429, 'Login rate limit exceeded')
    bucket.append(current)
    user = db.scalar(select(User).where(User.username == body.username))
    valid = passwords.verify(body.password, user.password_hash if user else dummy_hash)
    if not user or not valid or not user.active:
        raise HTTPException(401, 'Invalid credentials')
    response = issue(db, user)
    record(db, user, 'auth.login', 'session')
    db.commit()
    return response


@app.post('/api/v1/auth/register', status_code=201)
def register(body: Register, request: Request, db=Depends(get_db)):
    from sqlalchemy.exc import IntegrityError
    address = request.client.host if request.client else 'local'
    bucket = registration_attempts[address]
    current = time.monotonic()
    while bucket and bucket[0] < current - 60:
        bucket.popleft()
    if len(bucket) >= 5:
        raise HTTPException(429, 'Account creation rate limit exceeded')
    bucket.append(current)
    reserved = {'maker', 'checker', 'controller', 'reader', 'auditor', 'outsider'}
    if body.username in reserved or db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(409, 'Username unavailable')
    # Public registration cannot join an existing organization or grant privileges.
    organization = Organization(id=str(uuid4()), name='Personal simulation workspace')
    user = User(id=str(uuid4()), org_id=organization.id, username=body.username,
                password_hash=passwords.hash(body.password), role='READ_ONLY_USER')
    try:
        db.add(organization)
        db.flush()
        db.add(user)
        db.flush()
        response = issue(db, user)
        record(db, user, 'auth.register', 'user')
        db.commit()
        return response
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Username unavailable') from None


@app.get('/api/v1/auth/me')
def me(user=Depends(current_user)):
    return {'id': user.id, 'username': user.username, 'role': user.role, 'organization_id': user.org_id, 'permissions': sorted(ROLES.get(user.role, set()))}


@app.post('/api/v1/auth/logout')
def logout(credentials=Depends(bearer), user=Depends(current_user), db=Depends(get_db)):
    _, session = authenticate(db, credentials.credentials)
    session.revoked = True
    record(db, user, 'auth.logout', 'session')
    db.commit()
    return {'status': 'revoked'}


@app.post('/api/v1/auth/refresh')
def refresh(credentials=Depends(bearer), user=Depends(current_user), db=Depends(get_db)):
    _, session = authenticate(db, credentials.credentials)
    session.revoked = True
    response = issue(db, user)
    record(db, user, 'auth.refresh', 'session')
    db.commit()
    return response


@app.get('/api/v1/customers/{customer_id}')
def customer(customer_id: str, user=Depends(current_user), db=Depends(get_db)):
    require(user, 'customer.read')
    row = customer_scope(db, user, customer_id)
    record(db, user, 'customer.read', customer_id)
    db.commit()
    return {'id': row.id, 'display_name': row.display_name, 'kyc_status': row.kyc_status}


@app.get('/api/v1/customers')
def customers(user=Depends(current_user), db=Depends(get_db)):
    from app.models import Grant
    require(user, 'customer.read')
    rows = db.scalars(select(Customer).join(Grant, Grant.customer_id == Customer.id).where(
        Customer.org_id == user.org_id, Grant.user_id == user.id).limit(100))
    result = [{'id': row.id, 'display_name': row.display_name} for row in rows]
    record(db, user, 'customer.list', 'customers')
    db.commit()
    return result


@app.post('/api/v1/demo/provision')
def provision_demo(user=Depends(current_user), db=Depends(get_db)):
    from sqlalchemy import update
    from app.models import Grant, AuditHead
    from app.core.config import settings
    require(user, 'customer.read')
    require(user, 'account.read')
    if not settings.simulation_only:
        raise HTTPException(403, 'Sample records are available only in simulation')
    # Serialize global synthetic identifier allocation and repeated requests.
    db.execute(update(AuditHead).where(AuditHead.id == 1).values(sequence=AuditHead.sequence))
    existing = db.scalar(select(Customer).join(Grant, Grant.customer_id == Customer.id).where(
        Customer.org_id == user.org_id, Grant.user_id == user.id).limit(1))
    if existing:
        account = db.scalar(select(Account).where(Account.customer_id == existing.id).limit(1))
        db.commit()
        return {'mode': 'SIMULATION', 'customer_id': existing.id, 'account_id': account.id if account else None}
    used_customers = set(db.scalars(select(Customer.id)))
    used_accounts = set(db.scalars(select(Account.id)))
    number = next((n for n in range(1000, 10000) if f'CUS-{n:04d}' not in used_customers and f'ACC-{n:04d}' not in used_accounts), None)
    if number is None:
        raise HTTPException(409, 'Local sample record capacity reached')
    customer = Customer(id=f'CUS-{number:04d}', org_id=user.org_id,
                        display_name='Your synthetic sample customer', kyc_status='REVIEW_REQUIRED')
    db.add(customer)
    db.flush()
    account = Account(id=f'ACC-{number:04d}', customer_id=customer.id, currency='INR', balance='50000.00', status='ACTIVE')
    db.add_all([account, Grant(user_id=user.id, customer_id=customer.id)])
    record(db, user, 'demo.provisioned', customer.id)
    db.commit()
    return {'mode': 'SIMULATION', 'customer_id': customer.id, 'account_id': account.id}


@app.get('/api/v1/accounts')
def accounts(user=Depends(current_user), db=Depends(get_db)):
    from app.models import Grant
    require(user, 'account.read')
    rows = db.scalars(select(Account).join(Customer).join(Grant, Grant.customer_id == Customer.id).where(Customer.org_id == user.org_id, Grant.user_id == user.id).limit(100))
    result = [{'id': row.id, 'currency': row.currency, 'balance': str(row.balance), 'status': row.status} for row in rows]
    record(db, user, 'account.list', 'accounts')
    db.commit()
    return result


@app.get('/api/v1/accounts/{account_id}/balance')
def balance(account_id: str, user=Depends(current_user), db=Depends(get_db)):
    from app.models import now
    require(user, 'account.read')
    row = account_scope(db, user, account_id)
    record(db, user, 'account.balance', account_id)
    db.commit()
    return {'account_id': row.id, 'masked_identifier': '****' + row.id[-4:], 'balance': str(row.balance), 'currency': row.currency, 'as_of': now(), 'mode': 'SIMULATION'}


@app.post('/api/v1/payments/prepare')
def prepare_payment(body: PaymentRequest, user=Depends(current_user), db=Depends(get_db)):
    result = prepare(db, user, body)
    db.commit()
    return result


@app.get('/api/v1/payments')
def payments(offset: int = 0, user=Depends(current_user), db=Depends(get_db)):
    from app.models import Grant
    if offset < 0:
        raise HTTPException(422, 'Offset must be positive')
    if not ROLES.get(user.role, set()) & {'payment.prepare', 'payment.approve', 'payment.execute'}:
        raise HTTPException(403, 'Operation not permitted')
    rows = db.scalars(select(Payment).join(Account).join(Grant, Grant.customer_id == Account.customer_id).where(Payment.org_id == user.org_id, Grant.user_id == user.id).order_by(Payment.created_at.desc()).offset(offset).limit(100))
    return [view(row) for row in rows]


@app.get('/api/v1/payments/{payment_id}')
def get_payment(payment_id: str, user=Depends(current_user), db=Depends(get_db)):
    require(user, 'account.read')
    return view(scoped_payment(db, user, payment_id))


@app.post('/api/v1/payments/{payment_id}/execute')
def execute_payment(payment_id: str, user=Depends(current_user), db=Depends(get_db)):
    result = execute(db, user, payment_id)
    db.commit()
    return result


@app.get('/api/v1/payments/{payment_id}/receipt')
def receipt(payment_id: str, user=Depends(current_user), db=Depends(get_db)):
    require(user, 'account.read')
    payment = scoped_payment(db, user, payment_id)
    row = db.scalar(select(Execution).where(Execution.payment_id == payment.id))
    if not row:
        raise HTTPException(409, 'Not executed')
    return view(payment) | {'receipt_id': row.id, 'executed_at': row.created_at}


@app.get('/api/v1/approvals')
def approvals(user=Depends(current_user), db=Depends(get_db)):
    require(user, 'payment.approve')
    return [p for p in payments(0, user, db) if p['status'] == 'PENDING_APPROVAL']


@app.post('/api/v1/approvals/{payment_id}/approve')
def approve(payment_id: str, body: ApprovalRequest, user=Depends(current_user), db=Depends(get_db)):
    result = decide(db, user, payment_id, 'APPROVED', body.comment)
    db.commit()
    return result


@app.post('/api/v1/approvals/{payment_id}/reject')
def reject(payment_id: str, body: ApprovalRequest, user=Depends(current_user), db=Depends(get_db)):
    result = decide(db, user, payment_id, 'REJECTED', body.comment)
    db.commit()
    return result


@app.post('/api/v1/workflows')
async def create_workflow(body: WorkflowRequest, user=Depends(current_user), db=Depends(get_db)):
    from app.orchestration.workflow import run
    # Expected access/validation failures are user errors, not MCP transport errors.
    permission = {'customer': 'customer.read', 'balance': 'account.read', 'payment': 'payment.prepare'}[body.operation]
    require(user, permission)
    try:
        if body.operation == 'customer' and body.customer_id:
            customer_scope(db, user, body.customer_id)
        elif body.operation == 'balance' and body.account_id:
            account_scope(db, user, body.account_id)
        elif body.operation == 'payment' and body.payment:
            account_scope(db, user, body.payment.account_id)
        else:
            raise HTTPException(422, 'Required workflow fields absent')
    except HTTPException as error:
        if error.status_code == 404:
            raise HTTPException(404, 'This record is unavailable in your workspace. An administrator must assign customer access before you can run this workflow.') from None
        raise
    workflow = Workflow(org_id=user.org_id, user_id=user.id, kind=body.operation, status='RUNNING', result={})
    db.add(workflow)
    db.flush()
    record(db, user, 'workflow.started', workflow.id)
    db.commit()  # release DB locks before the MCP subprocess transaction
    try:
        result = await run(user, body, workflow.id)
        workflow.status = 'COMPLETED'
        workflow.result = result
    except HTTPException:
        workflow.status = 'FAILED'
        record(db, user, 'workflow.failed', workflow.id, 'ERROR')
        db.commit()
        raise
    record(db, user, 'workflow.completed', workflow.id)
    db.commit()
    return {'id': workflow.id, 'status': workflow.status, 'result': workflow.result}


@app.get('/api/v1/workflows')
def workflows(user=Depends(current_user), db=Depends(get_db)):
    rows = db.scalars(select(Workflow).where(Workflow.org_id == user.org_id, Workflow.user_id == user.id).order_by(Workflow.created_at.desc()).limit(100))
    return [{'id': row.id, 'kind': row.kind, 'status': row.status, 'created_at': row.created_at, 'result': row.result} for row in rows]


@app.get('/api/v1/mcp/tools')
def tools(user=Depends(current_user)):
    require(user, 'registry.read')
    return registry()


@app.get('/api/v1/mcp/servers')
def servers(user=Depends(current_user)):
    require(user, 'registry.read')
    return [{'name': name, 'transport': 'STDIO', 'trust': 'fixed local module', 'health': 'checked per invocation'} for name in SERVERS]


@app.get('/api/v1/audit/events')
def audit_events(offset: int = 0, user=Depends(current_user), db=Depends(get_db)):
    require(user, 'audit.read')
    if offset < 0:
        raise HTTPException(422, 'Offset must be positive')
    rows = db.scalars(select(AuditEvent).where(AuditEvent.org_id == user.org_id).order_by(AuditEvent.id.desc()).offset(offset).limit(100))
    return [{key: getattr(row, key) for key in ['id', 'actor_id', 'action', 'resource', 'result', 'created_at', 'correlation_id', 'digest']} for row in rows]


@app.get('/api/v1/audit/verify')
def verify_audit(user=Depends(current_user), db=Depends(get_db)):
    require(user, 'audit.read')
    return {'valid': verify(db), 'scope': 'global chain; no other-organization records returned', 'limitation': 'Hash chains require external checkpoints to detect privileged wholesale rewriting.'}
