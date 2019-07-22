"""オンメモリデータベース Redis"""

import logging

import aioredis

from planetsclub import settings

_LOGGER = logging.getLogger("planetsclub.services.redis")


async def create_redis():
    return await aioredis.create_redis(address=settings.REDIS_URL)
