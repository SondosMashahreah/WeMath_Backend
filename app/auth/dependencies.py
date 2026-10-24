from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.jwt import decode_access_token
from app.db.database import get_db
from app.models.user import User
from app.services.auth_service import (
    get_user_by_id,
    get_user_roles,
)


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/token"
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    subject = decode_access_token(token)

    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(subject)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )

    user = get_user_by_id(db, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not available",
        )

    return user


def require_roles(*allowed_roles: str):
    def checker(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        roles = get_user_roles(db, user.id)

        if not set(roles).intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return user

    return checker