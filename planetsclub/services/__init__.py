"""データベースなどのサービス類"""

import logging
import ssl
from enum import Enum

import aiohttp
import aioredis
import certifi
from elasticsearch.serializer import JSONSerializer
from elasticsearch_async import AsyncElasticsearch

from planetsclub import settings

_LOGGER = logging.getLogger("planetsclub.services")


class CustomJSONSerializer(JSONSerializer):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


class _Services:
    def __init__(self):
        self.redis_pool = None
        self.es = None
        self.msghub = None
        self.http_session = None
        # self.gcs = google.cloud.storage.Client()
        # self.gcp_vision_image_annotator = google.cloud.vision.ImageAnnotatorClient()

    def setup(self, app):
        app.add_event_handler("startup", self._startup)
        app.add_event_handler("shutdown", self._shutdown)

    async def _startup(self):
        # HTTP Session
        self.http_session = aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar())

        # Redis
        self.redis_pool = await aioredis.create_redis_pool(
            address=settings.REDIS_URL, maxsize=10
        )
        _LOGGER.info("Redis pool ready")

        # Elasticsearch
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        self.es = AsyncElasticsearch(
            hosts=settings.ELASTICSEARCH_HOSTS,
            http_auth=settings.ELASTICSEARCH_HTTP_AUTH,
            use_ssl=settings.ELASTICSEARCH_USE_SSL,
            ssl_context=ssl_context,
            serializer=CustomJSONSerializer(),
        )
        _LOGGER.info("Elasticsearch ready")

        # # Message Hub
        # self.msghub = MessageHub(self.redis_pool)
        # await self.msghub.run()
        # _LOGGER.info("Message hub ready")

    async def _shutdown(self):
        await self.http_session.close()

        # # Message Hub
        # try:
        #     self.msghub.close()
        #     await self.msghub.wait_close()
        # except Exception:
        #     _LOGGER.exception("exception:")
        #     raise
        # else:
        #     _LOGGER.info("Message hub closed")

        # Elasticsearch
        try:
            await self.es.transport.close()
        except Exception:
            _LOGGER.exception("exception:")
        else:
            _LOGGER.info("Elasticsearch closed")

        # Redis
        try:
            self.redis_pool.close()
            await self.redis_pool.wait_closed()
        except Exception:
            _LOGGER.exception("exception:")
        else:
            _LOGGER.info("Redis pool closed")


services = _Services()
