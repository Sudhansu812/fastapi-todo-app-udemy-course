from fastapi import HTTPException
from starlette import status
from src.api.user_deps import user_dependency

def require_role(*allowed_roles: str):
    def role_checker(user: user_dependency):
        if not set(user.roles) & set(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource."
            )
        return user
    return role_checker