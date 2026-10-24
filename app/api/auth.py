from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.jwt import create_access_token
from app.db.database import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.auth_service import (
    authenticate_user,
    get_user_roles,
    register_student,
)


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db),
):
    try:
        user = register_student(
            db=db,
            full_name=data.full_name,
            email=data.email,
            password=data.password,
        )

        return {
            "success": True,
            "user": {
                "id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "roles": ["student"],
            },
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    user = authenticate_user(
        db,
        data.email,
        data.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return TokenResponse(
        access_token=create_access_token(
            subject=str(user.id)
        )
    )


@router.post(
    "/token",
    response_model=TokenResponse,
)
def swagger_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(
        db,
        form_data.username,
        form_data.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return TokenResponse(
        access_token=create_access_token(
            subject=str(user.id)
        )
    )


@router.get("/me")
def me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "roles": get_user_roles(
            db,
            user.id,
        ),
        "created_at": user.created_at,
    }