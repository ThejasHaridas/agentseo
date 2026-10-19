"""Accounts and sessions: scrypt password hashes, opaque session tokens in an httpOnly cookie."""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import User, UserSession

COOKIE = "agentrank_session"
SESSION_DAYS = 30
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}

# Failed logins per email in the last 15 minutes; in memory, which is enough for one prototype process.
_failures: dict[str, list[float]] = defaultdict(list)
_MAX_FAILURES, _WINDOW_S = 5, 15 * 60


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), dklen=32, n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(session: Session, user: User, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    session.add(UserSession(token_hash=_token_hash(token), user=user,
                            expires_at=datetime.now(UTC) + timedelta(days=SESSION_DAYS)))
    session.commit()
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=settings.cookie_secure, path="/")


def end_session(session: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        row = session.get(UserSession, _token_hash(token))
        if row:
            session.delete(row)
            session.commit()
    response.delete_cookie(COOKIE, path="/")


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get(COOKIE)
    row = session.get(UserSession, _token_hash(token)) if token else None
    if row is None:
        raise HTTPException(401, "Sign in to continue.")
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        session.delete(row)
        session.commit()
        raise HTTPException(401, "Your session expired. Sign in again.")
    return row.user


def check_login_allowed(email: str) -> None:
    now = time.monotonic()
    recent = [t for t in _failures[email] if now - t < _WINDOW_S]
    _failures[email] = recent
    if len(recent) >= _MAX_FAILURES:
        raise HTTPException(429, "Too many failed sign-ins. Try again in 15 minutes.")


def record_failure(email: str) -> None:
    _failures[email].append(time.monotonic())


def find_user(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email))
