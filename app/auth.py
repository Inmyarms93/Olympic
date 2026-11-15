import os
from fastapi import HTTPException, Request, status
from dotenv import load_dotenv

load_dotenv()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")


def is_admin(request: Request) -> bool:
    return bool(request.session.get("is_admin"))


def require_admin(request: Request):
    if not is_admin(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Требуется авторизация администратора")