from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import get_metadata_store, get_current_user
from backend.api.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from backend.core.security import verify_password, hash_password, create_access_token

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, meta=Depends(get_metadata_store)):
    user = meta.get_user_by_username(body.username)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    token = create_access_token({"sub": user.user_id})
    return TokenResponse(access_token=token)


@router.post("/register", response_model=UserResponse, status_code=201)
def register(body: RegisterRequest, meta=Depends(get_metadata_store)):
    if meta.get_user_by_username(body.username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    uid = meta.create_user(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role="user",
    )
    user = meta.get_user_by_id(uid)
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
    )


@router.get("/me", response_model=UserResponse)
def me(user=Depends(get_current_user)):
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
    )
