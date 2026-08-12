"""Redis wake-up canonical wire 与安全 adapter 单元测试。"""

from __future__ import annotations

import ast
import json
from dataclasses import fields
from pathlib import Path
from uuid import UUID

import pytest

from dayu.host import redis_wakeup as redis_wakeup_module
from dayu.host.redis_wakeup import (
    REDIS_WAKEUP_MAX_BYTES,
    RedisWakeupAdapter,
    RedisWakeupUnavailableError,
    decode_redis_wakeup_message,
    encode_redis_wakeup_message,
)
from dayu.host.worker import (
    RedisWakeupHint,
    RedisWakeupRead,
    RedisWakeupReadAction,
)
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope

TENANT_UUID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_TENANT_UUID = UUID("22222222-2222-4222-8222-222222222222")
JOB_UUID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CHANNEL = f"dayu:platform:v1:wakeup:{TENANT_UUID}"

_FrameValue = None | bool | int | str | bytes
_Frame = dict[str, _FrameValue]


def _scope() -> TenantScope:
    """构造 canonical tenant scope。

    Args:
        无。

    Returns:
        测试 tenant scope。

    Raises:
        无。
    """

    return Principal(
        tenant_id=TenantId(str(TENANT_UUID)),
        user_id="platform-test",
    ).to_scope()


class _FakePubSub:
    """可编程 PubSub fake。"""

    def __init__(self) -> None:
        """初始化调用记录与 frame queue。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.subscribe_calls: list[str] = []
        self.get_calls: list[tuple[bool, float]] = []
        self.frames: list[_Frame | None] = []
        self.close_calls = 0
        self.fail_subscribe = False
        self.fail_get = False
        self.fail_close = False
        self.raise_type_error = False
        self.raise_value_error = False
        self.raise_get_type_error = False
        self.raise_get_value_error = False

    def subscribe(self, *channels: str) -> None:
        """记录订阅或抛 RedisError。

        Args:
            channels: channel 名称。

        Returns:
            无。

        Raises:
            redis.RedisError: 配置失败时抛出。
        """

        if self.fail_subscribe:
            raise redis_wakeup_module.redis.RedisError("raw subscribe error")
        if self.raise_type_error:
            raise TypeError("program type error")
        if self.raise_value_error:
            raise ValueError("program value error")
        self.subscribe_calls.extend(channels)

    def get_message(
        self,
        *,
        ignore_subscribe_messages: bool,
        timeout: float,
    ) -> _Frame | None:
        """返回下一帧或模拟连接失败。

        Args:
            ignore_subscribe_messages: 是否忽略订阅确认。
            timeout: bounded timeout。

        Returns:
            下一条可空 frame。

        Raises:
            redis.RedisError: 配置失败时抛出。
        """

        self.get_calls.append((ignore_subscribe_messages, timeout))
        if self.fail_get:
            raise redis_wakeup_module.redis.RedisError("raw read error")
        if self.raise_get_type_error:
            raise TypeError("program get type error")
        if self.raise_get_value_error:
            raise ValueError("program get value error")
        if self.raise_type_error:
            raise TypeError("program type error")
        if self.raise_value_error:
            raise ValueError("program value error")
        return self.frames.pop(0) if self.frames else None

    def close(self) -> None:
        """记录关闭或模拟连接失败。

        Args:
            无。

        Returns:
            无。

        Raises:
            redis.RedisError: 配置失败时抛出。
        """

        self.close_calls += 1
        if self.fail_close:
            raise redis_wakeup_module.redis.RedisError("raw close error")
        if self.raise_type_error:
            raise TypeError("program type error")
        if self.raise_value_error:
            raise ValueError("program value error")


class _FakeRedisClient:
    """可编程 sync Redis client fake。"""

    def __init__(self) -> None:
        """初始化调用记录。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.pubsub_instance = _FakePubSub()
        self.publish_calls: list[tuple[str, bytes]] = []
        self.pubsub_calls: list[bool] = []
        self.ping_calls = 0
        self.close_calls = 0
        self.fail_ping = False
        self.fail_publish = False
        self.fail_pubsub = False
        self.fail_close = False
        self.raise_type_error = False
        self.raise_value_error = False

    def ping(self) -> bool:
        """返回真响应或模拟连接失败。

        Args:
            无。

        Returns:
            ``True``。

        Raises:
            redis.RedisError: 配置失败时抛出。
        """

        self.ping_calls += 1
        if self.fail_ping:
            raise redis_wakeup_module.redis.RedisError("raw ping error")
        if self.raise_type_error:
            raise TypeError("program type error")
        if self.raise_value_error:
            raise ValueError("program value error")
        return True

    def publish(self, channel: str, message: bytes) -> int:
        """记录 canonical publish。

        Args:
            channel: tenant channel。
            message: canonical bytes。

        Returns:
            fake subscriber count。

        Raises:
            redis.RedisError: 配置失败时抛出。
        """

        if self.fail_publish:
            raise redis_wakeup_module.redis.RedisError("raw publish error")
        if self.raise_type_error:
            raise TypeError("program type error")
        if self.raise_value_error:
            raise ValueError("program value error")
        self.publish_calls.append((channel, message))
        return 1

    def pubsub(self, *, ignore_subscribe_messages: bool) -> _FakePubSub:
        """返回唯一 fake PubSub。

        Args:
            ignore_subscribe_messages: 构造选项。

        Returns:
            fake PubSub。

        Raises:
            redis.RedisError: 配置失败时抛出。
        """

        self.pubsub_calls.append(ignore_subscribe_messages)
        if self.fail_pubsub:
            raise redis_wakeup_module.redis.RedisError("raw pubsub error")
        if self.raise_type_error:
            raise TypeError("program type error")
        if self.raise_value_error:
            raise ValueError("program value error")
        return self.pubsub_instance

    def close(self) -> None:
        """记录关闭或模拟连接失败。

        Args:
            无。

        Returns:
            无。

        Raises:
            redis.RedisError: 配置失败时抛出。
        """

        self.close_calls += 1
        if self.fail_close:
            raise redis_wakeup_module.redis.RedisError("raw close error")
        if self.raise_type_error:
            raise TypeError("program type error")
        if self.raise_value_error:
            raise ValueError("program value error")


def _subscribe_ack(channel: str = CHANNEL) -> _Frame:
    """构造 RESP2 exact subscribe ACK。

    Args:
        channel: ACK 所属 channel。

    Returns:
        redis-py 标准 subscribe frame。

    Raises:
        无。
    """

    return {
        "type": "subscribe",
        "pattern": None,
        "channel": channel.encode("ascii"),
        "data": 1,
    }


@pytest.mark.unit
def test_redis_wakeup_message_is_exact_canonical_tenant_job_hint() -> None:
    """唯一 wire bytes 只含四个固定字段。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    message = encode_redis_wakeup_message(TENANT_UUID, JOB_UUID)
    assert message == (
        b'{"job_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",'
        b'"reason":"enqueued","schema_version":1,'
        b'"tenant_id":"11111111-1111-4111-8111-111111111111"}'
    )
    assert decode_redis_wakeup_message(
        message,
        expected_tenant_id=TENANT_UUID,
    ) == RedisWakeupHint(tenant_id=TENANT_UUID, job_id=JOB_UUID)


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    (
        b"",
        b"[]",
        b'{"job_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}',
        b'{"job_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",'
        b'"job_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",'
        b'"reason":"enqueued","schema_version":1,'
        b'"tenant_id":"11111111-1111-4111-8111-111111111111"}',
        b'{"tenant_id":"11111111-1111-4111-8111-111111111111",'
        b'"schema_version":1,"reason":"enqueued",'
        b'"job_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}',
        b'{"job_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",'
        b'"reason":"enqueued","schema_version":true,'
        b'"tenant_id":"11111111-1111-4111-8111-111111111111"}',
        b'{"job_id":"AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",'
        b'"reason":"enqueued","schema_version":1,'
        b'"tenant_id":"11111111-1111-4111-8111-111111111111"}',
        b'{"job_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",'
        b'"reason":"other","schema_version":1,'
        b'"tenant_id":"11111111-1111-4111-8111-111111111111"}',
    ),
)
def test_invalid_duplicate_or_noncanonical_wakeup_message_is_rejected(
    message: bytes,
) -> None:
    """缺字段、重复键、重排、bool-int 与漂移值均 fail closed。

    Args:
        message: 非法 wire bytes。

    Returns:
        无。

    Raises:
        无。
    """

    assert (
        decode_redis_wakeup_message(
            message,
            expected_tenant_id=TENANT_UUID,
        )
        is None
    )


@pytest.mark.unit
def test_cross_tenant_and_oversized_wakeup_message_are_rejected() -> None:
    """跨 tenant 与超限数据永不触发 wakeup。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    message = encode_redis_wakeup_message(OTHER_TENANT_UUID, JOB_UUID)
    assert (
        decode_redis_wakeup_message(
            message,
            expected_tenant_id=TENANT_UUID,
        )
        is None
    )
    assert (
        decode_redis_wakeup_message(
            b"x" * (REDIS_WAKEUP_MAX_BYTES + 1),
            expected_tenant_id=TENANT_UUID,
        )
        is None
    )


@pytest.mark.unit
def test_adapter_publishes_then_subscriber_reads_exact_tenant_hint() -> None:
    """publisher/subscriber 共用固定 channel 与 canonical bytes。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    client = _FakeRedisClient()
    adapter = RedisWakeupAdapter(client=client)
    assert adapter.ping() is True
    assert adapter.publish_hint(_scope(), JOB_UUID) is True
    assert client.publish_calls == [(CHANNEL, encode_redis_wakeup_message(TENANT_UUID, JOB_UUID))]

    subscriber = adapter.create_subscriber(_scope())
    client.pubsub_instance.frames.append(_subscribe_ack())
    assert subscriber.resubscribe() is True
    client.pubsub_instance.frames.append(
        {
            "type": "message",
            "pattern": None,
            "channel": CHANNEL.encode("ascii"),
            "data": client.publish_calls[0][1],
        }
    )
    read = subscriber.get_message(timeout_seconds=0.5)
    assert read == RedisWakeupRead(
        action=RedisWakeupReadAction.WAKEUP,
        hint=RedisWakeupHint(tenant_id=TENANT_UUID, job_id=JOB_UUID),
    )
    assert client.pubsub_calls == [False]
    assert client.pubsub_instance.subscribe_calls == [CHANNEL]
    assert client.pubsub_instance.get_calls == [(False, 1.0), (True, 0.5)]


@pytest.mark.unit
@pytest.mark.parametrize(
    "frame",
    (
        None,
        {
            "type": "subscribe",
            "pattern": None,
            "channel": b"dayu:platform:v1:wakeup:wrong",
            "data": 1,
        },
        {
            "type": "message",
            "pattern": None,
            "channel": CHANNEL.encode("ascii"),
            "data": 1,
        },
        {
            "type": "subscribe",
            "pattern": None,
            "channel": CHANNEL.encode("ascii"),
            "data": True,
        },
    ),
)
def test_resubscribe_missing_malformed_or_cross_channel_ack_returns_false(
    frame: _Frame | None,
) -> None:
    """ACK 缺失、畸形或跨 channel 时订阅不得报告成功。

    Args:
        frame: 本次 fake 返回的可空 ACK 候选。

    Returns:
        无。

    Raises:
        无。
    """

    client = _FakeRedisClient()
    client.pubsub_instance.frames.append(frame)
    subscriber = RedisWakeupAdapter(client=client).create_subscriber(_scope())
    assert subscriber.resubscribe() is False
    assert client.pubsub_instance.get_calls == [(False, 1.0)]


@pytest.mark.unit
def test_resubscribe_ack_read_narrows_only_redis_error() -> None:
    """ACK read 的 RedisError safe false，程序错误保持传播。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    redis_failure_client = _FakeRedisClient()
    redis_failure_client.pubsub_instance.fail_get = True
    redis_failure_subscriber = RedisWakeupAdapter(client=redis_failure_client).create_subscriber(_scope())
    assert redis_failure_subscriber.resubscribe() is False

    type_error_client = _FakeRedisClient()
    type_error_client.pubsub_instance.raise_get_type_error = True
    type_error_subscriber = RedisWakeupAdapter(client=type_error_client).create_subscriber(_scope())
    with pytest.raises(TypeError):
        type_error_subscriber.resubscribe()

    value_error_client = _FakeRedisClient()
    value_error_client.pubsub_instance.raise_get_value_error = True
    value_error_subscriber = RedisWakeupAdapter(client=value_error_client).create_subscriber(_scope())
    with pytest.raises(ValueError):
        value_error_subscriber.resubscribe()


@pytest.mark.unit
def test_no_message_invalid_frame_and_connection_failure_are_distinct() -> None:
    """无消息、协议拒绝与连接失败保持三种 closed action。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    client = _FakeRedisClient()
    subscriber = RedisWakeupAdapter(client=client).create_subscriber(_scope())
    assert subscriber.get_message(timeout_seconds=1) == RedisWakeupRead(
        action=RedisWakeupReadAction.NO_MESSAGE,
        hint=None,
    )
    client.pubsub_instance.frames.append(
        {
            "type": "message",
            "channel": b"wrong-channel",
            "data": encode_redis_wakeup_message(TENANT_UUID, JOB_UUID),
        }
    )
    assert subscriber.get_message(timeout_seconds=1).action is (RedisWakeupReadAction.INVALID_MESSAGE)
    client.pubsub_instance.fail_get = True
    assert subscriber.get_message(timeout_seconds=1).action is (RedisWakeupReadAction.CONNECTION_FAILURE)


@pytest.mark.unit
def test_adapter_narrows_redis_failures_and_closes_exactly_once() -> None:
    """ping/publish/subscribe/close 原始异常均不穿透 adapter。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    client = _FakeRedisClient()
    adapter = RedisWakeupAdapter(client=client)
    client.fail_ping = True
    client.fail_publish = True
    assert adapter.ping() is False
    assert adapter.publish_hint(_scope(), JOB_UUID) is False

    subscriber = adapter.create_subscriber(_scope())
    client.pubsub_instance.fail_subscribe = True
    assert subscriber.resubscribe() is False
    client.pubsub_instance.fail_close = True
    subscriber.close()
    subscriber.close()
    assert client.pubsub_instance.close_calls == 1

    client.fail_close = True
    adapter.close()
    adapter.close()
    assert client.close_calls == 1
    assert adapter.ping() is False
    assert adapter.publish_hint(_scope(), JOB_UUID) is False


@pytest.mark.unit
def test_from_url_locks_resp2_bytes_and_bounded_socket_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """factory 固定 RESP2、bytes response 与同一有限 timeout。

    Args:
        monkeypatch: pytest patch helper。

    Returns:
        无。

    Raises:
        无。
    """

    client = _FakeRedisClient()
    calls: list[tuple[str, int, bool, float, float]] = []

    def _from_url(
        url: str,
        *,
        protocol: int,
        decode_responses: bool,
        socket_connect_timeout: float,
        socket_timeout: float,
    ) -> _FakeRedisClient:
        """记录 Redis factory 参数。

        Args:
            url: Redis URL。
            protocol: RESP version。
            decode_responses: response decoding flag。
            socket_connect_timeout: connect timeout。
            socket_timeout: socket timeout。

        Returns:
            fake client。

        Raises:
            无。
        """

        calls.append(
            (
                url,
                protocol,
                decode_responses,
                socket_connect_timeout,
                socket_timeout,
            )
        )
        return client

    monkeypatch.setattr(redis_wakeup_module.redis.Redis, "from_url", _from_url)
    adapter = RedisWakeupAdapter.from_url(
        "redis://127.0.0.1:6379/0",
        timeout_seconds=0.75,
    )
    assert adapter.ping() is True
    client.pubsub_instance.frames.append(_subscribe_ack())
    assert adapter.create_subscriber(_scope()).resubscribe() is True
    assert client.pubsub_instance.get_calls == [(False, 0.75)]
    assert calls == [("redis://127.0.0.1:6379/0", 2, False, 0.75, 0.75)]


@pytest.mark.unit
def test_from_url_failure_raises_only_fixed_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis factory 原始错误正文与 URL 不进入外层异常。

    Args:
        monkeypatch: pytest patch helper。

    Returns:
        无。

    Raises:
        无。
    """

    def _from_url(
        url: str,
        *,
        protocol: int,
        decode_responses: bool,
        socket_connect_timeout: float,
        socket_timeout: float,
    ) -> _FakeRedisClient:
        """始终抛包含敏感样本的 RedisError。

        Args:
            url: Redis URL。
            protocol: RESP version。
            decode_responses: response decoding flag。
            socket_connect_timeout: connect timeout。
            socket_timeout: socket timeout。

        Returns:
            本 fake 不返回。

        Raises:
            redis.RedisError: 始终抛出。
        """

        del url, protocol, decode_responses, socket_connect_timeout, socket_timeout
        raise redis_wakeup_module.redis.RedisError("redis://secret@host/raw")

    monkeypatch.setattr(redis_wakeup_module.redis.Redis, "from_url", _from_url)
    with pytest.raises(RedisWakeupUnavailableError) as exc_info:
        RedisWakeupAdapter.from_url(
            "redis://secret@host/0",
            timeout_seconds=1,
        )
    assert str(exc_info.value) == "redis wakeup admission failed"
    assert exc_info.value.__cause__ is None


@pytest.mark.unit
def test_redis_wakeup_closed_dtos_and_timeout_validation_are_exact() -> None:
    """DTO 联合矩阵与 bounded read timeout fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    assert tuple(field.name for field in fields(RedisWakeupHint)) == (
        "tenant_id",
        "job_id",
    )
    assert tuple(field.name for field in fields(RedisWakeupRead)) == (
        "action",
        "hint",
    )
    with pytest.raises(ValueError):
        RedisWakeupRead(action=RedisWakeupReadAction.WAKEUP, hint=None)
    with pytest.raises(ValueError):
        RedisWakeupRead(
            action=RedisWakeupReadAction.NO_MESSAGE,
            hint=RedisWakeupHint(tenant_id=TENANT_UUID, job_id=JOB_UUID),
        )
    subscriber = RedisWakeupAdapter(client=_FakeRedisClient()).create_subscriber(_scope())
    for timeout in (True, 0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            subscriber.get_message(timeout_seconds=timeout)


@pytest.mark.unit
def test_invalid_duplicate_reordered_or_cross_tenant_hint_never_changes_pg_state() -> None:
    """协议拒绝只返回 INVALID，不暴露任何持久化入口。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    client = _FakeRedisClient()
    subscriber = RedisWakeupAdapter(client=client).create_subscriber(_scope())
    invalid_messages = (
        json.dumps(
            {
                "schema_version": 1,
                "tenant_id": str(TENANT_UUID),
                "job_id": str(JOB_UUID),
                "reason": "enqueued",
            }
        ).encode(),
        encode_redis_wakeup_message(OTHER_TENANT_UUID, JOB_UUID),
        b'{"job_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",'
        b'"job_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",'
        b'"reason":"enqueued","schema_version":1,'
        b'"tenant_id":"11111111-1111-4111-8111-111111111111"}',
    )
    for message in invalid_messages:
        client.pubsub_instance.frames.append(
            {
                "type": "message",
                "channel": CHANNEL.encode("ascii"),
                "data": message,
            }
        )
        assert subscriber.get_message(timeout_seconds=0.1).action is (RedisWakeupReadAction.INVALID_MESSAGE)


@pytest.mark.unit
def test_lone_unicode_surrogate_message_is_invalid() -> None:
    """escaped 孤立 surrogate 不得穿透 canonical re-encode。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    message = (
        b'{"job_id":"\\ud800","reason":"enqueued","schema_version":1,'
        b'"tenant_id":"11111111-1111-4111-8111-111111111111"}'
    )
    assert (
        decode_redis_wakeup_message(
            message,
            expected_tenant_id=TENANT_UUID,
        )
        is None
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "url",
    (
        "redis://127.0.0.1:6379/0?protocol=3",
        "redis://127.0.0.1:6379/0?decode_responses=true",
        "redis://127.0.0.1:6379/0?socket_timeout=99",
        "redis://127.0.0.1:6379/0?unknown=value",
        "redis://127.0.0.1:6379/0?",
    ),
)
def test_redis_url_query_cannot_override_resp2_bytes_or_bounded_timeouts(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    """任一 query 都在 ``Redis.from_url`` 前以固定 safe error 拒绝。

    Args:
        monkeypatch: pytest patch helper。
        url: 带 query delimiter 的 Redis URL。

    Returns:
        无。

    Raises:
        无。
    """

    calls = 0

    def _from_url(
        redis_url: str,
        *,
        protocol: int,
        decode_responses: bool,
        socket_connect_timeout: float,
        socket_timeout: float,
    ) -> _FakeRedisClient:
        """记录意外 factory 调用。

        Args:
            redis_url: Redis URL。
            protocol: RESP version。
            decode_responses: response decoding flag。
            socket_connect_timeout: connect timeout。
            socket_timeout: socket timeout。

        Returns:
            fake client。

        Raises:
            无。
        """

        nonlocal calls
        del redis_url, protocol, decode_responses, socket_connect_timeout, socket_timeout
        calls += 1
        return _FakeRedisClient()

    monkeypatch.setattr(redis_wakeup_module.redis.Redis, "from_url", _from_url)
    with pytest.raises(RedisWakeupUnavailableError) as exc_info:
        RedisWakeupAdapter.from_url(url, timeout_seconds=0.5)
    assert str(exc_info.value) == "redis wakeup admission failed"
    assert calls == 0


@pytest.mark.unit
def test_redis_url_fragment_is_rejected_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fragment 在 client construction 前被拒绝且不泄漏 URL。

    Args:
        monkeypatch: pytest patch helper。

    Returns:
        无。

    Raises:
        无。
    """

    calls = 0

    def _from_url(
        redis_url: str,
        *,
        protocol: int,
        decode_responses: bool,
        socket_connect_timeout: float,
        socket_timeout: float,
    ) -> _FakeRedisClient:
        """记录意外 factory 调用。

        Args:
            redis_url: Redis URL。
            protocol: RESP version。
            decode_responses: response decoding flag。
            socket_connect_timeout: connect timeout。
            socket_timeout: socket timeout。

        Returns:
            fake client。

        Raises:
            无。
        """

        nonlocal calls
        del redis_url, protocol, decode_responses, socket_connect_timeout, socket_timeout
        calls += 1
        return _FakeRedisClient()

    monkeypatch.setattr(redis_wakeup_module.redis.Redis, "from_url", _from_url)
    with pytest.raises(RedisWakeupUnavailableError) as exc_info:
        RedisWakeupAdapter.from_url(
            "redis://127.0.0.1:6379/0#secret",
            timeout_seconds=0.5,
        )
    assert str(exc_info.value) == "redis wakeup admission failed"
    assert calls == 0


@pytest.mark.unit
@pytest.mark.parametrize("error_type", (TypeError, ValueError))
def test_runtime_redis_type_or_value_error_propagates_without_degraded_transition(
    error_type: type[TypeError] | type[ValueError],
) -> None:
    """已构造 client/PubSub 的程序错误不伪装成连接失败。

    Args:
        error_type: 本次注入的程序错误类型。

    Returns:
        无。

    Raises:
        无。
    """

    client = _FakeRedisClient()
    adapter = RedisWakeupAdapter(client=client)
    if error_type is TypeError:
        client.raise_type_error = True
    else:
        client.raise_value_error = True
    with pytest.raises(error_type):
        adapter.ping()
    with pytest.raises(error_type):
        adapter.publish_hint(_scope(), JOB_UUID)
    with pytest.raises(error_type):
        adapter.create_subscriber(_scope())

    client.raise_type_error = False
    client.raise_value_error = False
    subscriber = adapter.create_subscriber(_scope())
    if error_type is TypeError:
        client.pubsub_instance.raise_type_error = True
    else:
        client.pubsub_instance.raise_value_error = True
    with pytest.raises(error_type):
        subscriber.resubscribe()
    with pytest.raises(error_type):
        subscriber.get_message(timeout_seconds=0.1)


@pytest.mark.unit
def test_redis_adapter_is_the_only_import_redis_owner() -> None:
    """production tree 中只有 concrete adapter 可 import redis-py。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    dayu_root = Path(__file__).parents[2] / "dayu"
    owners: list[str] = []
    for path in sorted(dayu_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports_redis = any(
            (isinstance(node, ast.Import) and any(alias.name == "redis" for alias in node.names))
            or (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and (node.module == "redis" or node.module.startswith("redis."))
            )
            for node in ast.walk(tree)
        )
        if imports_redis:
            owners.append(str(path.relative_to(dayu_root)))
    assert owners == ["host/redis_wakeup.py"]
    assert "RedisWakeupRead" not in redis_wakeup_module.__all__
