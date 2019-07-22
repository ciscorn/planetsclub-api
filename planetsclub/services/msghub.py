"""Redisを用いたメッセージブローカーの実装（未使用）"""


import asyncio
import logging
import weakref

import msgpack
from async_timeout import timeout

from planetsclub.services.redis import create_redis

_LOGGER = logging.getLogger("planetsclub.msghub")

_HUB_BROADCAST_CHANNEL = "planetsclub-hub"
_PING_INTERVAL = 10
_PING_TIMEOUT = 4


class Subscription:
    def __init__(self, hub, queue, topics):
        self._hub = hub
        self._queue = queue
        self.topics = topics

    async def get(self):
        return await self._queue.get()

    def close(self):
        self._hub.unsubscribe(self)


class MessageHub:
    def __init__(self, redis_pool):
        self._redis_pool = redis_pool
        self._subscriptions = {}
        self._redis_task = None

    async def _redis_subscriber(self):
        async def run_subscriber():
            _LOGGER.info("Connecting message hub to redis")
            redis = await create_redis()
            try:
                (channel, *_) = await redis.subscribe(_HUB_BROADCAST_CHANNEL)
                while True:
                    msg = None
                    try:
                        with timeout(_PING_INTERVAL):
                            msg = await channel.get()
                    except asyncio.TimeoutError:
                        pass
                    if msg:
                        (topic, data) = msgpack.loads(msg, raw=False)
                        await self._process_msg(topic, data)
                    else:
                        # heartbeat
                        with timeout(_PING_TIMEOUT):
                            await redis.ping()
            finally:
                if not redis.closed:
                    await redis.unsubscribe(channel.name)
                    await redis.quit()

        while True:
            try:
                await run_subscriber()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                _LOGGER.exception(exc)
                await asyncio.sleep(2)

    async def run(self):
        self._redis_task = asyncio.ensure_future(self._redis_subscriber())

    async def _process_msg(self, topic, data):
        def gen_topic_name():
            yield "*"
            nodes = topic.split(".")
            for i in range(1, len(nodes) + 1):
                yield ".".join(nodes[:i]) + ".*"
            yield topic

        subs = self._subscriptions
        all_queues = set()
        for to in gen_topic_name():
            queues = subs.get(to)
            if queues:
                all_queues.update(queues)

        for queue in all_queues:
            await queue.put((topic, data))

    async def emit(self, topic, data):
        with (await self._redis_pool) as r:
            await r.publish(_HUB_BROADCAST_CHANNEL, msgpack.dumps([topic, data]))

    def close(self):
        if self._redis_task:
            self._redis_task.cancel()
            self._subscriptions.clear()

    async def wait_close(self):
        if self._redis_task:
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass

    def subscribe(self, topic_or_topics):
        if isinstance(topic_or_topics, str):
            topics = (topic_or_topics,)
        else:
            topics = tuple(set(topic_or_topics))

        queue = asyncio.Queue()
        subs = self._subscriptions
        for topic in topics:
            if topic not in subs:
                subs[topic] = weakref.WeakSet()
            subs[topic].add(queue)

        return Subscription(self, queue, topics)

    def unsubscribe(self, subscription):
        queue = subscription._queue
        subs = self._subscriptions
        for topic in subscription.topics:
            if topic in subs:
                subs[topic].discard(queue)
                if not subs[topic]:
                    subs.pop(topic)
