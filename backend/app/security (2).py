"""Password hashing and signed bearer tokens for the Phase 3 auth layer."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = encoded.split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 310_000)
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (ValueError, TypeError):
        return False

def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="ace-canteen-auth-v1")

def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return _serializer().dumps({"sub": str(user.id), "role": user.role.value, "ver": user.token_version, "iat": int(now.timestamp())})

def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Valid bearer token required", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized
    try:
        payload = _serializer().loads(credentials.credentials, max_age=get_settings().access_token_minutes * 60)
        if not isinstance(payload, dict):
            raise ValueError("Invalid token payload")
        user_id = int(payload.get("sub", ""))
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        raise unauthorized
    user = db.get(User, user_id)
    if user is None or not user.is_active or payload.get("ver", 0) != user.token_version:
        raise unauthorized
    return user

def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to perform this action")
        return user
    return dependency
