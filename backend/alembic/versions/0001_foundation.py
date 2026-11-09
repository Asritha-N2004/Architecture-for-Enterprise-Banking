"""Initial simulation schema. Migration freezes a copy of v1 metadata below."""
from alembic import op
from sqlalchemy import Column, String, Integer, Numeric, Boolean, JSON, ForeignKey, UniqueConstraint

revision = '0001'
down_revision = None


def upgrade():
    op.create_table('organizations', Column('id', String, primary_key=True), Column('name', String, nullable=False))
    op.create_table('users', Column('id', String, primary_key=True), Column('org_id', String, ForeignKey('organizations.id'), nullable=False, index=True), Column('username', String, nullable=False, unique=True), Column('password_hash', String, nullable=False), Column('role', String, nullable=False), Column('active', Boolean, nullable=False))
    op.create_table('user_sessions', Column('id', String, primary_key=True), Column('user_id', String, ForeignKey('users.id'), nullable=False), Column('expires', Integer, nullable=False), Column('revoked', Boolean, nullable=False))
    op.create_table('customers', Column('id', String, primary_key=True), Column('org_id', String, ForeignKey('organizations.id'), nullable=False, index=True), Column('display_name', String, nullable=False), Column('kyc_status', String, nullable=False))
    op.create_table('customer_access_grants', Column('id', String, primary_key=True), Column('user_id', String, ForeignKey('users.id'), nullable=False), Column('customer_id', String, ForeignKey('customers.id'), nullable=False), UniqueConstraint('user_id', 'customer_id'))
    op.create_table('bank_accounts', Column('id', String, primary_key=True), Column('customer_id', String, ForeignKey('customers.id'), nullable=False, index=True), Column('currency', String(3), nullable=False), Column('balance', Numeric(18,2), nullable=False), Column('status', String, nullable=False))
    op.create_table('beneficiaries', Column('id', String, primary_key=True), Column('customer_id', String, ForeignKey('customers.id'), nullable=False), Column('name', String, nullable=False), Column('verified', Boolean, nullable=False))
    op.create_table('payment_instructions', Column('id', String, primary_key=True), Column('org_id', String, ForeignKey('organizations.id'), nullable=False, index=True), Column('maker_id', String, ForeignKey('users.id'), nullable=False), Column('account_id', String, ForeignKey('bank_accounts.id'), nullable=False), Column('beneficiary_id', String, ForeignKey('beneficiaries.id'), nullable=False), Column('amount', Numeric(18,2), nullable=False), Column('fee', Numeric(18,2), nullable=False), Column('currency', String(3), nullable=False), Column('idempotency_key', String, nullable=False), Column('fingerprint', String, nullable=False), Column('policy_version', String, nullable=False), Column('status', String, nullable=False), Column('required_approvals', Integer, nullable=False), Column('expires', Integer, nullable=False), Column('created_at', String, nullable=False), UniqueConstraint('org_id', 'maker_id', 'idempotency_key'))
    op.create_table('payment_approvals', Column('id', String, primary_key=True), Column('payment_id', String, ForeignKey('payment_instructions.id'), nullable=False), Column('approver_id', String, ForeignKey('users.id'), nullable=False), Column('fingerprint', String, nullable=False), Column('decision', String, nullable=False), Column('comment', String, nullable=False), Column('created_at', String, nullable=False), UniqueConstraint('payment_id', 'approver_id'))
    op.create_table('payment_execution_records', Column('id', String, primary_key=True), Column('payment_id', String, ForeignKey('payment_instructions.id'), nullable=False, unique=True), Column('mode', String, nullable=False), Column('created_at', String, nullable=False))
    op.create_table('audit_head', Column('id', Integer, primary_key=True), Column('sequence', Integer, nullable=False), Column('digest', String, nullable=False))
    from sqlalchemy import table, column
    op.bulk_insert(table('audit_head', column('id', Integer), column('sequence', Integer), column('digest', String)), [{'id': 1, 'sequence': 0, 'digest': '0' * 64}])
    op.create_table('audit_events', Column('id', Integer, primary_key=True, autoincrement=False), *[Column(name, String, nullable=False, index=name == 'org_id') for name in ['org_id','actor_id','action','resource','result','correlation_id','created_at','previous_hash','digest']])
    op.create_table('banking_workflows', Column('id', String, primary_key=True), Column('org_id', String, ForeignKey('organizations.id'), nullable=False, index=True), Column('user_id', String, ForeignKey('users.id'), nullable=False), Column('kind', String, nullable=False), Column('status', String, nullable=False), Column('result', JSON, nullable=False), Column('created_at', String, nullable=False))
    # The application has no audit update/delete API. DB triggers also reject mutations.
    dialect = op.get_bind().dialect.name
    if dialect == 'sqlite':
        for verb in ['UPDATE', 'DELETE']:
            op.execute(f"CREATE TRIGGER audit_no_{verb.lower()} BEFORE {verb} ON audit_events BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END")
    elif dialect == 'postgresql':
        op.execute("CREATE FUNCTION reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit events are append-only'; END; $$")
        op.execute('CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()')


def downgrade():
    raise RuntimeError('Destructive audit downgrade is intentionally unsupported; restore a protected backup')
