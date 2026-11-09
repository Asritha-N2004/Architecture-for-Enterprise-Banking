from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)

    @field_validator('username', mode='before')
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class Register(StrictModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=12, max_length=256)

    @field_validator('username', mode='before')
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class PaymentRequest(StrictModel):
    account_id: str = Field(pattern=r'^ACC-[0-9]{4}$')
    beneficiary_id: str = Field(pattern=r'^BEN-[0-9]{4}$')
    amount: Decimal = Field(gt=0, le=1000000, max_digits=12, decimal_places=2)
    currency: Literal['INR'] = 'INR'
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')


class ApprovalRequest(StrictModel):
    comment: str = Field(min_length=3, max_length=500)


class WorkflowRequest(StrictModel):
    operation: Literal['customer', 'balance', 'payment']
    customer_id: str | None = Field(default=None, pattern=r'^CUS-[0-9]{4}$')
    account_id: str | None = Field(default=None, pattern=r'^ACC-[0-9]{4}$')
    payment: PaymentRequest | None = None


class ToolEnvelope(StrictModel):
    mode: Literal['SIMULATION'] = 'SIMULATION'
    data: dict
    explanation: str
