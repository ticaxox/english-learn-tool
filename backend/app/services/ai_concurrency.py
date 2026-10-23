from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis

_CONCURRENCY_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local stale_before = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local job_id = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', stale_before)
local count = redis.call('ZCARD', key)
if count >= limit then
  return 0
end
redis.call('ZADD', key, now, job_id)
redis.call('EXPIRE', key, 86400)
return 1
"""


def concurrency_key(user_id: UUID) -> str:
    return f"ai:concurrency:{user_id}"


async def acquire_concurrency_slot(
    redis: Redis,
    *,
    user_id: UUID,
    job_id: UUID,
    limit: int,
    stale_seconds: int,
) -> bool:
    now = __import__("time").time()
    result = await redis.eval(
        _CONCURRENCY_SCRIPT,
        1,
        concurrency_key(user_id),
        str(now),
        str(now - stale_seconds),
        str(limit),
        str(job_id),
    )
    return int(result) == 1


async def release_concurrency_slot(redis: Redis, *, user_id: UUID, job_id: UUID) -> None:
    await redis.zrem(concurrency_key(user_id), str(job_id))


async def concurrency_in_use(redis: Redis, *, user_id: UUID) -> int:
    return int(await redis.zcard(concurrency_key(user_id)))
