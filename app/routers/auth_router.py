from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from ..auth import ADMIN_PASSWORD, is_admin

router = APIRouter()


class LoginIn(BaseModel):
    password: str


@router.post("/login")
def login(data: LoginIn, request: Request):
    if data.password != ADMIN_PASSWORD:
        raise HTTPException(401, "Неверный пароль")
    request.session["is_admin"] = True
    return {"ok": True}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    return {"is_admin": is_admin(request)}