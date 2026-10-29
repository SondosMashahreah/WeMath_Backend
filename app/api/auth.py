from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user, require_roles
from app.auth.jwt import create_access_token
from app.auth.password import hash_password, verify_password
from app.db.database import get_db
from app.models.user import User
from app.models.learning import StudentProfile
from app.schemas.auth import LoginRequest, PasswordChangeRequest, RegisterRequest, StudentDetails, TokenResponse
from app.services.auth_service import authenticate_user, create_account, user_payload, validate_student_track

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def token_for(user, db=None):
    return TokenResponse(access_token=create_access_token(str(user.id), user.token_version), user=user_payload(db, user) if db else None)


@router.post("/register", status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    try:
        user = create_account(db, data)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        detail = str(exc) if isinstance(exc, ValueError) else "اسم المستخدم أو البريد مستخدم بالفعل"
        raise HTTPException(409, detail) from None
    return token_for(user, db)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.username, data.password)
    if not user:
        raise HTTPException(401, "اسم المستخدم أو كلمة المرور غير صحيحة، أو الحساب موقوف")
    return token_for(user, db)


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
    values = data.model_dump(exclude={"full_name"})
    values["track"] = validate_student_track(db, data.grade, data.track)
    for key, value in values.items():
        setattr(profile, key, value)
    db.commit()
    return user_payload(db, user)


@router.put("/me/password", response_model=TokenResponse)
def change_password(data: PasswordChangeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "كلمة المرور الحالية غير صحيحة")
    if data.current_password == data.new_password:
        raise HTTPException(400, "اختر كلمة مرور جديدة مختلفة")
    user.password_hash = hash_password(data.new_password)
    user.token_version += 1
    db.commit()
    db.refresh(user)
    return token_for(user, db)


@router.post("/logout", status_code=204)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(update(User).where(User.id == user.id).values(token_version=User.token_version + 1))
    db.commit()
