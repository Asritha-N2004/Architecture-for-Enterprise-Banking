import secrets
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'sqlite:///./banking.db'
    jwt_secret: str = ''
    issuer: str = 'secure-banking-local'
    audience: str = 'banking-portal'
    simulation_only: bool = True
    policy_version: str = 'simulation-v1'
    token_minutes: int = 15

    @model_validator(mode='after')
    def safe_defaults(self):
        if self.database_url.startswith('postgres://'):
            self.database_url = self.database_url.replace('postgres://', 'postgresql+psycopg://', 1)
        elif self.database_url.startswith('postgresql://'):
            self.database_url = self.database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
        if os.environ.get('VERCEL') and (not self.database_url.startswith('postgresql+psycopg://') or not self.jwt_secret):
            raise ValueError('Vercel requires an external DATABASE_URL and a persistent JWT_SECRET')
        if not self.simulation_only:
            raise ValueError('Live execution is not implemented; simulation_only must remain true')
        if not self.jwt_secret:
            self.jwt_secret = secrets.token_urlsafe(48)
        if len(self.jwt_secret) < 32:
            raise ValueError('JWT_SECRET must contain at least 32 characters')
        return self


settings = Settings()
