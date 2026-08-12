"""Redis wake-up hint 的唯一 wire adapter。

Redis 在 durable platform 中只负责提示：消息不承载 payload、lease、token
或任何持久状态，Worker 收到提示后仍只从 PostgreSQL claim。本模块是仓库中
唯一导入 redis-py 的 owner，并把连接、publish、subscribe 与 close 异常收窄
为固定布尔值或 closed read action，绝不传播 URL 或 provider 错误正文。
"""

from __future__ import annotations

import json
from math import isfinite
from typing import Protocol, TypeAlias, runtime_checkable
from urllib.parse import urlsplit
from uuid import UUID

import redis

from dayu.host import worker as worker_types
from dayu.investment.domain.identifiers import TenantScope

REDIS_WAKEUP_SCHEMA_VERSION = 1
REDIS_WAKEUP_REASON = "enqueued"
REDIS_WAKEUP_MAX_BYTES = 512
_CHANNEL_PREFIX = "dayu:platform:v1:wakeup:"
_SUBSCRIBE_ACK_TIMEOUT_MAX_SECONDS = 1.0

_JsonScalar: TypeAlias = None | bool | int | str
_JsonValue: TypeAlias = _JsonScalar | list["_JsonValue"] | dict[str, "_JsonValue"]
_RedisMessageValue: TypeAlias = None | bool | int | str | bytes


class RedisWakeupUnavailableError(RuntimeError):
    """Redis client/subscriber 无法安全构造时的固定错误。"""


class _RedisPubSubProtocol(Protocol):
    """redis-py PubSub 所需的最小同步 surface。"""

    def subscribe(self, *channels: str) -> None:
        """订阅 channel。

        Args:
            channels: channel 名称。

        Returns:
            无。

        Raises:
            Exception: redis-py 连接异常。
        """
        ...

    def get_message(
        self,
        *,
        ignore_subscribe_messages: bool,
        timeout: float,
    ) -> dict[str, _RedisMessageValue] | None:
        """读取一条 PubSub frame。

        Args:
            ignore_subscribe_messages: 是否忽略订阅确认帧。
            timeout: bounded timeout。

        Returns:
            可空 frame mapping。

        Raises:
            Exception: redis-py 连接异常。
        """
        ...

    def close(self) -> None:
        """关闭 PubSub。

        Args:
            无。

        Returns:
            无。

        Raises:
            Exception: redis-py 关闭异常。
        """
        ...


@runtime_checkable
class _RedisClientProtocol(Protocol):
    """redis-py sync client 所需的最小 surface。"""

    def ping(self) -> bool:
        """调用 Redis PING。

        Args:
            无。

        Returns:
            Redis 响应。

        Raises:
            Exception: redis-py 连接异常。
        """
        ...

    def publish(self, channel: str, message: bytes) -> int:
        """发布 bytes message。

        Args:
            channel: 固定 tenant channel。
            message: canonical message bytes。

        Returns:
            subscriber 数量。

        Raises:
            Exception: redis-py 连接异常。
        """
        ...

    def pubsub(self, *, ignore_subscribe_messages: bool) -> _RedisPubSubProtocol:
        """创建 PubSub。

        Args:
            ignore_subscribe_messages: 是否忽略订阅确认帧。

        Returns:
            PubSub 实例。

        Raises:
            Exception: redis-py 构造异常。
        """
        ...

    def close(self) -> None:
        """关闭 client。

        Args:
            无。

        Returns:
            无。

        Raises:
            Exception: redis-py 关闭异常。
        """
        ...


class RedisWakeupSubscriber(worker_types.RedisWakeupSubscriberProtocol):
    """单 tenant 的严格 PubSub subscriber。"""

    def __init__(
        self,
        *,
        pubsub: _RedisPubSubProtocol,
        scope: TenantScope,
    ) -> None:
        """保存 PubSub 与 canonical tenant channel。

        Args:
            pubsub: sync PubSub 窄协议。
            scope: 显式 tenant scope。

        Returns:
            无。

        Raises:
            ValueError: tenant id 不是 canonical UUID 时抛出。
        """

        self._pubsub = pubsub
        self._tenant_id = _tenant_uuid(scope)
        self._channel = _channel_for_tenant(self._tenant_id)
        self._subscribe_ack_timeout_seconds = _SUBSCRIBE_ACK_TIMEOUT_MAX_SECONDS
        self._closed = False

    @classmethod
    def _create_with_ack_timeout(
        cls,
        *,
        pubsub: _RedisPubSubProtocol,
        scope: TenantScope,
        timeout_seconds: float,
    ) -> RedisWakeupSubscriber:
        """以已验证 socket timeout 创建 concrete subscriber。

        Args:
            pubsub: sync PubSub 窄协议。
            scope: 显式 tenant scope。
            timeout_seconds: subscribe ACK 的正有限读取上界。

        Returns:
            绑定 exact ACK timeout 的 subscriber。

        Raises:
            ValueError: timeout 或 tenant id 非法时抛出。
        """

        subscriber = cls(pubsub=pubsub, scope=scope)
        subscriber._subscribe_ack_timeout_seconds = _positive_finite_seconds(timeout_seconds)
        return subscriber

    def resubscribe(self) -> bool:
        """订阅固定 tenant channel 并等待 exact server ACK。

        Args:
            无。

        Returns:
            收到本 channel 的严格 subscribe ACK 时为 ``True``；ACK 缺失、
            漂移或 Redis 异常时为 ``False``。

        Raises:
            TypeError: 已构造 PubSub 的程序类型错误传播。
            ValueError: 已构造 PubSub 的程序值错误传播。
        """

        if self._closed:
            return False
        try:
            self._pubsub.subscribe(self._channel)
            frame = self._pubsub.get_message(
                ignore_subscribe_messages=False,
                timeout=self._subscribe_ack_timeout_seconds,
            )
        except redis.RedisError:
            return False
        return _is_exact_subscribe_ack(frame, expected_channel=self._channel)

    def get_message(self, *, timeout_seconds: float) -> worker_types.RedisWakeupRead:
        """读取并严格校验一条 wake-up frame。

        Args:
            timeout_seconds: 正有限 timeout。

        Returns:
            wakeup/no-message/invalid/connection-failure closed 结果。

        Raises:
            ValueError: timeout 不是正有限数时抛出。
        """

        timeout = _positive_finite_seconds(timeout_seconds)
        if self._closed:
            return worker_types.RedisWakeupRead(
                action=worker_types.RedisWakeupReadAction.CONNECTION_FAILURE,
                hint=None,
            )
        try:
            frame = self._pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=timeout,
            )
        except redis.RedisError:
            return worker_types.RedisWakeupRead(
                action=worker_types.RedisWakeupReadAction.CONNECTION_FAILURE,
                hint=None,
            )
        if frame is None:
            return worker_types.RedisWakeupRead(
                action=worker_types.RedisWakeupReadAction.NO_MESSAGE,
                hint=None,
            )
        if type(frame) is not dict:
            return _invalid_read()
        frame_type = frame.get("type")
        channel = frame.get("channel")
        data = frame.get("data")
        if frame_type != "message" or channel != self._channel.encode("ascii") or type(data) is not bytes:
            return _invalid_read()
        hint = decode_redis_wakeup_message(data, expected_tenant_id=self._tenant_id)
        if hint is None:
            return _invalid_read()
        return worker_types.RedisWakeupRead(
            action=worker_types.RedisWakeupReadAction.WAKEUP,
            hint=hint,
        )

    def close(self) -> None:
        """幂等关闭 PubSub，并收窄 close 异常。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        if self._closed:
            return
        self._closed = True
        try:
            self._pubsub.close()
        except redis.RedisError:
            return


class RedisWakeupAdapter(
    worker_types.RedisWakeupSubscriberFactoryProtocol,
    worker_types.RedisWakeupClientProtocol,
):
    """同步 redis-py client 的安全 publisher/factory/lifecycle adapter。"""

    def __init__(self, *, client: _RedisClientProtocol) -> None:
        """保存已配置为 RESP2/bytes/bounded timeout 的 client。

        Args:
            client: sync Redis client 窄协议。

        Returns:
            无。

        Raises:
            TypeError: client 不满足最小协议时抛出。
        """

        if not isinstance(client, _RedisClientProtocol):
            raise TypeError("client 必须满足 Redis sync protocol")
        self._client = client
        self._subscribe_ack_timeout_seconds = _SUBSCRIBE_ACK_TIMEOUT_MAX_SECONDS
        self._closed = False

    @classmethod
    def from_url(
        cls,
        redis_url: str,
        *,
        timeout_seconds: float,
    ) -> RedisWakeupAdapter:
        """以固定 RESP2/bytes/bounded timeout 构造 adapter。

        Args:
            redis_url: startup 从受控环境读取的 Redis URL。
            timeout_seconds: connect/socket 共用的正有限上界。

        Returns:
            新 ``RedisWakeupAdapter``。

        Raises:
            RedisWakeupUnavailableError: client 无法安全构造时抛出固定错误。
            ValueError: URL 空白或 timeout 非法时抛出。
        """

        if type(redis_url) is not str or not redis_url or redis_url != redis_url.strip():
            raise ValueError("redis_url 必须是非空无首尾空白字符串")
        timeout = _positive_finite_seconds(timeout_seconds)
        try:
            parsed_url = urlsplit(redis_url)
        except ValueError:
            raise RedisWakeupUnavailableError("redis wakeup admission failed") from None
        if parsed_url.query or parsed_url.fragment or "?" in redis_url or "#" in redis_url:
            raise RedisWakeupUnavailableError("redis wakeup admission failed")
        try:
            client = redis.Redis.from_url(
                redis_url,
                protocol=2,
                decode_responses=False,
                socket_connect_timeout=timeout,
                socket_timeout=timeout,
            )
        except (redis.RedisError, TypeError, ValueError):
            raise RedisWakeupUnavailableError("redis wakeup admission failed") from None
        adapter = cls(client=client)
        adapter._subscribe_ack_timeout_seconds = timeout
        return adapter

    def ping(self) -> bool:
        """执行有界 ping，并把 Redis 异常收窄为 ``False``。

        Args:
            无。

        Returns:
            client 未关闭且响应 exact ``True`` 时为 ``True``。

        Raises:
            无。
        """

        if self._closed:
            return False
        try:
            return self._client.ping() is True
        except redis.RedisError:
            return False

    def publish_hint(self, scope: TenantScope, job_id: UUID) -> bool:
        """向固定 tenant channel 发布 canonical bytes hint。

        Args:
            scope: 显式 tenant scope。
            job_id: 已完成 PG commit 的 job UUID。

        Returns:
            publish 命令成功时为 ``True``；Redis 连接异常时为 ``False``。

        Raises:
            TypeError: scope/job 或 client 程序类型错误时传播。
            ValueError: scope/job 或 client 程序值错误时传播。
        """

        if self._closed:
            return False
        tenant_id = _tenant_uuid(scope)
        message = encode_redis_wakeup_message(tenant_id, job_id)
        try:
            self._client.publish(_channel_for_tenant(tenant_id), message)
        except redis.RedisError:
            return False
        return True

    def create_subscriber(
        self,
        scope: TenantScope,
    ) -> worker_types.RedisWakeupSubscriberProtocol:
        """创建尚未订阅的 tenant subscriber。

        Args:
            scope: 显式 tenant scope。

        Returns:
            新 ``RedisWakeupSubscriber``。

        Raises:
            RedisWakeupUnavailableError: client 已关闭或 PubSub 构造失败。
            ValueError: tenant id 不是 canonical UUID 时抛出。
        """

        if self._closed:
            raise RedisWakeupUnavailableError("redis wakeup client is closed")
        _tenant_uuid(scope)
        try:
            pubsub = self._client.pubsub(ignore_subscribe_messages=False)
        except redis.RedisError:
            raise RedisWakeupUnavailableError("redis wakeup subscriber failed") from None
        return RedisWakeupSubscriber._create_with_ack_timeout(
            pubsub=pubsub,
            scope=scope,
            timeout_seconds=self._subscribe_ack_timeout_seconds,
        )

    def close(self) -> None:
        """幂等关闭 client，并收窄 close 异常。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        if self._closed:
            return
        self._closed = True
        try:
            self._client.close()
        except redis.RedisError:
            return


def encode_redis_wakeup_message(tenant_id: UUID, job_id: UUID) -> bytes:
    """编码唯一 canonical Redis wake-up message。

    Args:
        tenant_id: canonical tenant UUID。
        job_id: canonical job UUID。

    Returns:
        key 排序、紧凑 UTF-8 JSON bytes。

    Raises:
        TypeError: 任一参数不是 ``UUID`` 时抛出。
    """

    if not isinstance(tenant_id, UUID):
        raise TypeError("tenant_id 必须是 UUID")
    if not isinstance(job_id, UUID):
        raise TypeError("job_id 必须是 UUID")
    value: dict[str, _JsonValue] = {
        "job_id": str(job_id),
        "reason": REDIS_WAKEUP_REASON,
        "schema_version": REDIS_WAKEUP_SCHEMA_VERSION,
        "tenant_id": str(tenant_id),
    }
    encoded = _encode_canonical(value)
    if len(encoded) > REDIS_WAKEUP_MAX_BYTES:
        raise ValueError("redis wakeup message exceeds byte limit")
    return encoded


def decode_redis_wakeup_message(
    message: bytes,
    *,
    expected_tenant_id: UUID,
) -> worker_types.RedisWakeupHint | None:
    """严格解析 canonical Redis wake-up message。

    Args:
        message: PubSub data bytes。
        expected_tenant_id: 当前 subscriber 绑定的 tenant UUID。

    Returns:
        完全闭合且 tenant 相同的提示；任一 wire 漂移返回 ``None``。

    Raises:
        无。
    """

    if type(message) is not bytes or not message or len(message) > REDIS_WAKEUP_MAX_BYTES:
        return None
    if not isinstance(expected_tenant_id, UUID):
        return None
    try:
        text = message.decode("utf-8")
        raw: _JsonValue = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if type(raw) is not dict:
        return None
    mapping: dict[str, _JsonValue] = raw
    if set(mapping) != {"schema_version", "tenant_id", "job_id", "reason"}:
        return None
    try:
        canonical = _encode_canonical(mapping)
    except UnicodeEncodeError:
        return None
    if canonical != message:
        return None
    schema_version = mapping["schema_version"]
    tenant_text = mapping["tenant_id"]
    job_text = mapping["job_id"]
    reason = mapping["reason"]
    if (
        type(schema_version) is not int
        or schema_version != REDIS_WAKEUP_SCHEMA_VERSION
        or type(tenant_text) is not str
        or type(job_text) is not str
        or type(reason) is not str
        or reason != REDIS_WAKEUP_REASON
    ):
        return None
    tenant_id = _parse_canonical_uuid(tenant_text)
    job_id = _parse_canonical_uuid(job_text)
    if tenant_id is None or tenant_id != expected_tenant_id or job_id is None:
        return None
    return worker_types.RedisWakeupHint(tenant_id=tenant_id, job_id=job_id)


def _tenant_uuid(scope: TenantScope) -> UUID:
    """从显式 scope 收窄 canonical tenant UUID。

    Args:
        scope: 显式 tenant scope。

    Returns:
        canonical tenant UUID。

    Raises:
        TypeError: scope 类型错误时抛出。
        ValueError: tenant id 不是 canonical UUID 时抛出。
    """

    if not isinstance(scope, TenantScope):
        raise TypeError("scope 必须是 TenantScope")
    tenant_id = _parse_canonical_uuid(scope.tenant_id.value)
    if tenant_id is None:
        raise ValueError("tenant id 必须是 canonical UUID")
    return tenant_id


def _parse_canonical_uuid(value: str) -> UUID | None:
    """解析小写 canonical UUID 文本。

    Args:
        value: 待解析文本。

    Returns:
        canonical UUID；非法时为 ``None``。

        Raises:
            UnicodeEncodeError: value 含孤立 Unicode surrogate 时抛出。
    """

    if type(value) is not str:
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return parsed if str(parsed) == value else None


def _channel_for_tenant(tenant_id: UUID) -> str:
    """构造固定 tenant channel。

    Args:
        tenant_id: canonical tenant UUID。

    Returns:
        固定版本 channel。

    Raises:
        TypeError: ``tenant_id`` 不是 UUID 时抛出。
    """

    if not isinstance(tenant_id, UUID):
        raise TypeError("tenant_id 必须是 UUID")
    return f"{_CHANNEL_PREFIX}{tenant_id}"


def _positive_finite_seconds(value: float) -> float:
    """收窄正有限 timeout。

    Args:
        value: timeout 值。

    Returns:
        float timeout。

    Raises:
        ValueError: bool、非数值、非有限或非正时抛出。
    """

    if type(value) not in (int, float) or not isfinite(value) or value <= 0:
        raise ValueError("timeout_seconds 必须是正有限数")
    return float(value)


def _reject_duplicate_keys(
    pairs: list[tuple[str, _JsonValue]],
) -> dict[str, _JsonValue]:
    """拒绝重复 JSON key。

    Args:
        pairs: JSON parser 提供的有序键值对。

    Returns:
        无重复 key 的 mapping。

    Raises:
        ValueError: 发现重复 key 时抛出。
    """

    result: dict[str, _JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate redis wakeup key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> _JsonValue:
    """拒绝 NaN/Infinity token。

    Args:
        value: 非有限 token 文本。

    Returns:
        本函数不返回。

    Raises:
        ValueError: 始终抛出。
    """

    raise ValueError(f"nonfinite redis wakeup token: {value[:0]}")


def _encode_canonical(value: _JsonValue) -> bytes:
    """编码 canonical JSON bytes。

    Args:
        value: closed JSON value。

    Returns:
        排序、紧凑、UTF-8 bytes。

    Raises:
        无。
    """

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _invalid_read() -> worker_types.RedisWakeupRead:
    """构造固定 invalid-message read。

    Args:
        无。

    Returns:
        ``INVALID_MESSAGE`` read。

    Raises:
        无。
    """

    return worker_types.RedisWakeupRead(
        action=worker_types.RedisWakeupReadAction.INVALID_MESSAGE,
        hint=None,
    )


def _is_exact_subscribe_ack(
    frame: dict[str, _RedisMessageValue] | None,
    *,
    expected_channel: str,
) -> bool:
    """严格确认 RESP2 subscribe ACK 属于 exact channel。

    Args:
        frame: redis-py 解码后的可空 PubSub frame。
        expected_channel: 当前 subscriber 的 canonical channel。

    Returns:
        frame 仅含标准四字段、类型/channel/count 全匹配时为 ``True``。

    Raises:
        无。
    """

    if type(frame) is not dict or set(frame) != {
        "type",
        "pattern",
        "channel",
        "data",
    }:
        return False
    return (
        frame["type"] == "subscribe"
        and frame["pattern"] is None
        and frame["channel"] == expected_channel.encode("ascii")
        and type(frame["data"]) is int
        and frame["data"] == 1
    )


__all__ = [
    "REDIS_WAKEUP_MAX_BYTES",
    "REDIS_WAKEUP_REASON",
    "REDIS_WAKEUP_SCHEMA_VERSION",
    "RedisWakeupAdapter",
    "RedisWakeupSubscriber",
    "RedisWakeupUnavailableError",
    "decode_redis_wakeup_message",
    "encode_redis_wakeup_message",
]
