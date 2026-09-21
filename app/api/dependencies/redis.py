"""Dependency provider for the Redis-backed service."""

from starlette.requests import Request

from app.services.redis_service import RedisService


def get_redis_service(request: Request) -> RedisService:
    """
    Return the :class:`~app.services.redis_service.RedisService` built at startup.

    :param request: current request.
    :return: service instance, shared across requests.
    """
    return request.app.state.redis_service
