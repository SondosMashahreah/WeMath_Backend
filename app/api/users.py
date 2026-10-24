from fastapi import APIRouter, Depends

from app.auth.dependencies import require_roles
from app.models.user import User


router = APIRouter(
    prefix="/api/users",
    tags=["Users"],
)


@router.get("/student-area")
def student_area(
    user: User = Depends(
        require_roles("student")
    ),
):
    return {
        "message": "Student access granted",
        "user_id": user.id,
    }


@router.get("/admin-area")
def admin_area(
    user: User = Depends(
        require_roles("admin")
    ),
):
    return {
        "message": "Admin access granted",
        "user_id": user.id,
    }