from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user, require_roles
from app.auth.jwt import create_access_token
from app.db.database import get_db
from app.models.user import User
from app.models.learning import StudentProfile
from app.schemas.auth import LoginRequest, RegisterRequest, StudentDetails, TokenResponse
from app.services.auth_service import authenticate_user, create_account, user_payload

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def token_for(user):
    return TokenResponse(access_token=create_access_token(str(user.id), user.token_version))


@router.post("/register", status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    try:
        user = create_account(db, data)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        detail = str(exc) if isinstance(exc, ValueError) else "اسم المستخدم أو البريد مستخدم بالفعل"
        raise HTTPException(409, detail) from None
    return {**token_for(user).model_dump(), "user": user_payload(db, user)}


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.username, data.password)
    if not user:
        raise HTTPException(401, "اسم المستخدم أو كلمة المرور غير صحيحة، أو الحساب موقوف")
    return token_for(user)


@router.post("/token", response_model=TokenResponse)
def swagger_login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return login(LoginRequest(username=form_data.username, password=form_data.password), db)


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_payload(db, user)


@router.patch("/me/profile")
def complete_legacy_profile(data: StudentDetails, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    profile = db.get(StudentProfile, user.id)
    if profile and profile.grade is not None:
        raise HTTPException(409, "الصف محفوظ مسبقًا؛ يمكن لولي الأمر تعديل بيانات الطالب")
    if profile is None:
        profile = StudentProfile(user_id=user.id)
        db.add(profile)
    user.full_name = data.full_name
    for key, value in data.model_dump(exclude={"full_name"}).items():
        setattr(profile, key, value)
    db.commit()
    return user_payload(db, user)


@router.post("/logout", status_code=204)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(update(User).where(User.id == user.id).values(token_version=User.token_version + 1))
    db.commit()
