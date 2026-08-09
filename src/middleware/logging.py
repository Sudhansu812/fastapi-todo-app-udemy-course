from starlette.middleware.base import BaseHTTPMiddleware
from src.core.logging import logger

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if response.status_code >= 400:
            logger.error(f"ERROR ----- METHOD: {request.method}   PATH: {request.url.path}   QUERY_PARAMS: {request.query_params}   PATH_PARAMS: {request.path_params}   HEADERS: {request.headers}   STATUS_CODE: {response.status_code} ----- CLIENT: {request.client}")
        else:
            logger.info(f"INFO  ----- METHOD: {request.method}   PATH: {request.url.path}   STATUS_CODE: {response.status_code}")
        return response