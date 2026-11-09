"""Closed registry. Names, schemas and permissions are not model configurable."""
TOOLS = {
    'get_customer_profile': {'server': 'customer', 'permission': 'customer.read', 'risk': 'LOW', 'approval': False},
    'get_account_balance': {'server': 'account', 'permission': 'account.read', 'risk': 'LOW', 'approval': False},
    'prepare_payment_instruction': {'server': 'payment', 'permission': 'payment.prepare', 'risk': 'MEDIUM', 'approval': True},
    'execute_approved_payment': {'server': 'payment', 'permission': 'payment.execute', 'risk': 'HIGH', 'approval': True},
}
SERVERS = ('customer', 'account', 'payment')


def registry():
    return [dict(name=name, description=name.replace('_', ' '), classification='CONFIDENTIAL', rate_limit='30/min/user/process', **value) for name, value in TOOLS.items()]
