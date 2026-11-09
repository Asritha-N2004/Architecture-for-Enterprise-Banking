import time
import secrets
from datetime import datetime, timezone, timedelta
import jwt
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from app.core.config import settings
from app.database import get_db
from app.models import User, UserSession

passwords = PasswordHash.recommended()
dummy_hash = passwords.hash(secrets.token_urlsafe(24))
bearer = HTTPBearer(auto_error=False)


def issue(db, user):
    expires = int(time.time()) + settings.token_minutes * 60
    session = UserSession(user_id=user.id, expires=expires)
    db.add(session)
    db.flush()
    token = jwt.encode({'sub': user.id, 'sid': session.id, 'iss': settings.issuer,
                        'aud': settings.audience, 'iat': datetime.now(timezone.utc),
                        'exp': expires}, settings.jwt_secret, algorithm='HS256')
    return {'access_token': token, 'token_type': 'bearer', 'expires_in': settings.token_minutes * 60}


def authenticate(db, token):
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'],
                            issuer=settings.issuer, audience=settings.audience,
                            options={'require': ['exp', 'iat', 'iss', 'aud', 'sub', 'sid']})
        session = db.get(UserSession, claims['sid'])
        user = db.get(User, claims['sub'])
        if not session or session.revoked or session.expires <= time.time() or session.user_id != claims['sub'] or not user or not user.active:
            raise ValueError('Invalid session')
        return user, session
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise HTTPException(401, 'Invalid or expired session', headers={'WWW-Authenticate': 'Bearer'})


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(get_db)):
    if not credentials:
        raise HTTPException(401, 'Authentication required', headers={'WWW-Authenticate': 'Bearer'})
    return authenticate(db, credentials.credentials)[0]
