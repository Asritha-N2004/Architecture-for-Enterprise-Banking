"""Official SDK servers. STDIO credentials come from trusted process environment only."""
import os
import sys
import jwt
from fastapi import HTTPException
from sqlalchemy import select
from mcp.server.fastmcp import FastMCP
from app.core.config import settings
from app.database import Session
from app.models import User
from app.schemas import ToolEnvelope, PaymentRequest
from app.security.policy import require, customer_scope, account_scope
from app.payments.service import prepare, execute
from app.audit import record
from app.mcp.registry import TOOLS, SERVERS


def identity(db, name):
    try:
        claims = jwt.decode(os.environ.get('BANK_MCP_TICKET', ''), settings.jwt_secret,
                            algorithms=['HS256'], audience='banking-mcp', issuer=settings.issuer,
                            options={'require': ['exp', 'iat', 'sub', 'org', 'tool']})
        user = db.get(User, claims['sub'])
        if not user or not user.active or user.org_id != claims['org'] or claims['tool'] != name:
            raise ValueError('Delegation rejected')
        require(user, TOOLS[name]['permission'])
        return user
    except (jwt.PyJWTError, ValueError, HTTPException, KeyError):
        raise ValueError('Tool authorization denied') from None


def build_server(domain):
    if domain not in SERVERS:
        raise ValueError('Unapproved MCP server')
    server = FastMCP(f'banking-{domain}', json_response=True)

    def call(name, callback):
        with Session() as db:
            user = identity(db, name)
            try:
                data = callback(db, user)
                record(db, user, 'mcp.' + name, domain)
                db.commit()
                return ToolEnvelope(data=data, explanation='Authorized synthetic banking operation; simulation only.')
            except HTTPException as error:
                db.rollback()
                record(db, user, 'mcp.' + name, domain, 'DENY')
                db.commit()
                raise ValueError(f'Banking operation rejected ({error.status_code})') from None

    if domain == 'customer':
        @server.tool()
        def get_customer_profile(customer_id: str) -> ToolEnvelope:
            """Retrieve an explicitly granted synthetic customer profile, with minimized fields."""
            def retrieve(db, user):
                customer = customer_scope(db, user, customer_id)
                return {'customer_id': customer.id, 'display_name': customer.display_name, 'kyc_status': customer.kyc_status}
            return call('get_customer_profile', retrieve)
    if domain == 'account':
        @server.tool()
        def get_account_balance(account_id: str) -> ToolEnvelope:
            """Retrieve a granted synthetic account's decimal balance and observation timestamp."""
            def retrieve(db, user):
                from app.models import now
                account = account_scope(db, user, account_id)
                return {'account_id': account.id, 'masked_identifier': '****' + account.id[-4:], 'balance': format(account.balance, '.2f'), 'currency': account.currency, 'as_of': now()}
            return call('get_account_balance', retrieve)
    if domain == 'payment':
        @server.tool()
        def prepare_payment_instruction(request: PaymentRequest) -> ToolEnvelope:
            """Prepare a synthetic instruction for independent human approval. Does not execute."""
            return call('prepare_payment_instruction', lambda db, user: prepare(db, user, request))

        @server.tool()
        def execute_approved_payment(payment_id: str) -> ToolEnvelope:
            """Independently revalidate scope, approvals, policy and idempotency before simulation."""
            return call('execute_approved_payment', lambda db, user: execute(db, user, payment_id))

    @server.resource('banking://policy/simulation')
    def simulation_policy() -> str:
        """Public demonstration policy, contains no customer data."""
        return 'SIMULATION ONLY. Payments require independent approval. INR limit 1000000; dual approval at 100000; fee 5.'

    @server.prompt()
    def explain_simulation() -> str:
        """Fixed instruction template without untrusted data or credentials."""
        return 'Explain the structured result as a synthetic simulation. Human approval cannot be replaced by a model.'

    return server


if __name__ == '__main__':
    build_server(sys.argv[1]).run(transport='stdio')
