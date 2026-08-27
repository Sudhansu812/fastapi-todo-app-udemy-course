from datetime import datetime, timedelta, timezone
from typing import Annotated, cast
from fastapi import APIRouter, Depends, HTTPException
from starlette import status
from src.api.deps import db_dependency
from src.schemas.user import Token, TokenData, UserLoginRequest, UserRequest, UserResponse
from src.models.user import User
from passlib.context import CryptContext
from src.crud.auth import register_user as create_user, get_user_hashed_password as get_user_hash
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import JWTError, jwt
from src.core.config import settings as app_config

router = APIRouter(prefix="/auth", tags=["auth-v1"])
bcrypt_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
oauth2_bearer = OAuth2PasswordBearer(tokenUrl='api/v1/auth/authenticate')

@router.post("/create", status_code=status.HTTP_201_CREATED)
async def register_user(db: db_dependency, user: UserRequest):
    create_user_model = User(
        first_name=user.first_name,
        last_name = user.last_name,
        email = user.email,
        username = user.username,
        hashed_password=__hash_password(user.password),
        is_active=True,
        role=user.role
    )
    
    db_user = create_user(create_user_model, db)
    
    return db_user

@router.post("/authenticate", response_model=Token, status_code=status.HTTP_200_OK)
async def authenticate(db: db_dependency, user_credentials: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = get_user_hash(UserLoginRequest(username=user_credentials.username, password=user_credentials.password), db)
    
    if not user:
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username / email.")
        
    if not __verify_password(user_credentials.password, cast(str, user.hashed_password)):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password.")
    
    token = __create_access_token(username=cast(str, user.username), user_id=cast(int, user.id), role=cast(str, user.role), expires_delta=timedelta(minutes=30))
    
    return token 

async def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]):
    try:
        jwt_secret: str = app_config.jwt_secret
        algorithm: str = app_config.algorithm
        payload = jwt.decode(token, jwt_secret, algorithms=[algorithm])
        username = payload.get('sub')
        user_id = payload.get('id')
        role = payload.get('role')
        if username is None or user_id is None or role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials.")
        token_data = TokenData(user_id=user_id, username=username, role=role)
        return token_data # { 'username': username, 'id': user_id }
    except JWTError as je:
        raise HTTPException(status_code=401, detail="Could not validate credentials.")

'''
Helpers
'''
def __create_access_token(username: str, user_id: int, role: str, expires_delta: timedelta) -> Token:
    encode = { 'sub': username, 'id': user_id, 'role': role }
    expires: datetime = datetime.now(timezone.utc) + expires_delta
    encode.update({ 'exp': expires })
    
    jwt_secret: str = app_config.jwt_secret
    algorithm: str = app_config.algorithm
    
    jwt_token = jwt.encode(encode, jwt_secret, algorithm=algorithm)
    
    token = Token(access_token=jwt_token, token_type="bearer")
    return token

def __hash_password(password: str) -> str:
    return bcrypt_context.hash(password)

def __verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt_context.verify(plain_password, hashed_password)