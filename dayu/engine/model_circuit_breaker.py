"""In-memory or SQLite-backed circuit breaker for model provider calls."""

from __future__ import annotations

import math
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Lock

from dayu.contracts.model_failover import is_provider_availability_error


class ModelCircuitState(StrEnum):
    """Stable provider circuit states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class ModelCircuitBreakerPolicy:
    """Per-call policy used by the shared circuit registry."""

    enabled: bool = True
    failure_threshold: int = 3
    cooldown_seconds: float = 60.0

    def __post_init__(self) -> None:
        if isinstance(self.failure_threshold, bool) or self.failure_threshold <= 0:
            raise ValueError("model circuit breaker failure_threshold must be positive")
        if (
            isinstance(self.cooldown_seconds, bool)
            or not math.isfinite(self.cooldown_seconds)
            or self.cooldown_seconds <= 0
        ):
            raise ValueError("model circuit breaker cooldown_seconds must be positive")


@dataclass(frozen=True)
class ModelCircuitPermit:
    """Admission token that prevents stale outcomes from changing newer state."""

    resource_id: str
    generation: int
    half_open_probe: bool
    failure_threshold: int
    cooldown_seconds: float


@dataclass(frozen=True)
class ModelCircuitAdmission:
    """Result of checking the circuit before one provider call."""

    allowed: bool
    permit: ModelCircuitPermit | None
    state: ModelCircuitState
    reason: str
    retry_after_seconds: float | None = None


@dataclass(frozen=True)
class ModelCircuitSnapshot:
    """Credential-free current state for diagnostics and tests."""

    resource_id: str
    state: ModelCircuitState
    consecutive_failures: int
    generation: int
    last_error_type: str | None
    retry_after_seconds: float | None


@dataclass
class _CircuitEntry:
    state: ModelCircuitState = ModelCircuitState.CLOSED
    consecutive_failures: int = 0
    generation: int = 0
    opened_at: float | None = None
    cooldown_seconds: float = 0.0
    half_open_probe_in_flight: bool = False
    last_error_type: str | None = None


class _InMemoryCircuitStateStore:
    """Thread-safe state store used when no persistence path is configured."""

    state_path: Path | None = None

    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[str, _CircuitEntry] = {}

    @contextmanager
    def locked_entry(
        self,
        resource_id: str,
        *,
        create: bool,
    ) -> Iterator[_CircuitEntry | None]:
        with self._lock:
            entry = self._entries.get(resource_id)
            if entry is None and create:
                entry = _CircuitEntry()
                self._entries[resource_id] = entry
            yield entry

    def reset(self, resource_id: str | None = None) -> None:
        with self._lock:
            if resource_id is None:
                self._entries.clear()
            else:
                self._entries.pop(resource_id, None)


class _SQLiteCircuitStateStore:
    """Short-transaction SQLite store shared by workers using one workspace."""

    _TABLE_NAME = "model_circuit_breakers"
    _BUSY_TIMEOUT_SECONDS = 5.0

    def __init__(self, state_path: str | Path) -> None:
        resolved_path = Path(state_path).expanduser().resolve()
        if resolved_path.exists() and not resolved_path.is_file():
            raise ValueError(
                "model circuit breaker state_path must point to a file: "
                f"{resolved_path}"
            )
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path = resolved_path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.state_path),
            timeout=self._BUSY_TIMEOUT_SECONDS,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute(
            f"PRAGMA busy_timeout={int(self._BUSY_TIMEOUT_SECONDS * 1_000)}"
        )
        return conn

    def _initialize(self) -> None:
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._TABLE_NAME} (
                    resource_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    consecutive_failures INTEGER NOT NULL,
                    generation INTEGER NOT NULL,
                    opened_at REAL,
                    cooldown_seconds REAL NOT NULL,
                    half_open_probe_in_flight INTEGER NOT NULL,
                    last_error_type TEXT
                )
                """
            )
        finally:
            conn.close()

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
        finally:
            conn.close()

    @contextmanager
    def locked_entry(
        self,
        resource_id: str,
        *,
        create: bool,
    ) -> Iterator[_CircuitEntry | None]:
        with self._write_transaction() as conn:
            row = conn.execute(
                f"SELECT * FROM {self._TABLE_NAME} WHERE resource_id = ?",
                (resource_id,),
            ).fetchone()
            entry = self._entry_from_row(row) if row is not None else None
            if entry is None and create:
                entry = _CircuitEntry()
            yield entry
            if entry is not None:
                self._write_entry(conn, resource_id, entry)

    def reset(self, resource_id: str | None = None) -> None:
        with self._write_transaction() as conn:
            if resource_id is None:
                conn.execute(f"DELETE FROM {self._TABLE_NAME}")
            else:
                conn.execute(
                    f"DELETE FROM {self._TABLE_NAME} WHERE resource_id = ?",
                    (resource_id,),
                )

    @staticmethod
    def _entry_from_row(row: sqlite3.Row) -> _CircuitEntry:
        opened_at = row["opened_at"]
        last_error_type = row["last_error_type"]
        return _CircuitEntry(
            state=ModelCircuitState(str(row["state"])),
            consecutive_failures=int(row["consecutive_failures"]),
            generation=int(row["generation"]),
            opened_at=float(opened_at) if opened_at is not None else None,
            cooldown_seconds=float(row["cooldown_seconds"]),
            half_open_probe_in_flight=bool(row["half_open_probe_in_flight"]),
            last_error_type=(
                str(last_error_type) if last_error_type is not None else None
            ),
        )

    def _write_entry(
        self,
        conn: sqlite3.Connection,
        resource_id: str,
        entry: _CircuitEntry,
    ) -> None:
        conn.execute(
            f"""
            INSERT INTO {self._TABLE_NAME} (
                resource_id,
                state,
                consecutive_failures,
                generation,
                opened_at,
                cooldown_seconds,
                half_open_probe_in_flight,
                last_error_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(resource_id) DO UPDATE SET
                state = excluded.state,
                consecutive_failures = excluded.consecutive_failures,
                generation = excluded.generation,
                opened_at = excluded.opened_at,
                cooldown_seconds = excluded.cooldown_seconds,
                half_open_probe_in_flight = excluded.half_open_probe_in_flight,
                last_error_type = excluded.last_error_type
            """,
            (
                resource_id,
                entry.state.value,
                entry.consecutive_failures,
                entry.generation,
                entry.opened_at,
                entry.cooldown_seconds,
                int(entry.half_open_probe_in_flight),
                entry.last_error_type,
            ),
        )


def is_provider_health_failure(error_type: object) -> bool:
    """Return whether an error should affect provider availability state."""

    return is_provider_availability_error(error_type)


class ModelCircuitBreakerRegistry:
    """Circuit state keyed by model configuration with optional persistence."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        state_path: str | Path | None = None,
    ) -> None:
        normalized_path = str(state_path or "").strip()
        self._store: _InMemoryCircuitStateStore | _SQLiteCircuitStateStore
        if normalized_path:
            self._store = _SQLiteCircuitStateStore(normalized_path)
            self._clock = clock or time.time
        else:
            self._store = _InMemoryCircuitStateStore()
            self._clock = clock or time.monotonic

    @property
    def state_path(self) -> Path | None:
        """Return the persistent database path, or None for process-local state."""

        return self._store.state_path

    def before_call(
        self,
        resource_id: str,
        policy: ModelCircuitBreakerPolicy,
    ) -> ModelCircuitAdmission:
        """Atomically admit, reject, or reserve the single half-open probe."""

        normalized_id = str(resource_id or "").strip()
        if not normalized_id:
            raise ValueError("model circuit breaker resource_id must not be empty")
        if not policy.enabled:
            return ModelCircuitAdmission(
                allowed=True,
                permit=None,
                state=ModelCircuitState.CLOSED,
                reason="disabled",
            )

        with self._store.locked_entry(normalized_id, create=True) as entry:
            if entry is None:  # pragma: no cover - create=True guarantees an entry
                raise RuntimeError("model circuit breaker state store returned no entry")
            now = self._clock()
            if entry.state is ModelCircuitState.OPEN:
                retry_after = self._retry_after_locked(entry, now)
                if retry_after > 0:
                    return ModelCircuitAdmission(
                        allowed=False,
                        permit=None,
                        state=entry.state,
                        reason="cooldown_active",
                        retry_after_seconds=retry_after,
                    )
                entry.state = ModelCircuitState.HALF_OPEN
                entry.opened_at = now
                entry.cooldown_seconds = policy.cooldown_seconds
                entry.half_open_probe_in_flight = True
                return ModelCircuitAdmission(
                    allowed=True,
                    permit=self._permit(normalized_id, entry, policy, half_open_probe=True),
                    state=entry.state,
                    reason="half_open_probe",
                )

            if entry.state is ModelCircuitState.HALF_OPEN:
                retry_after = self._retry_after_locked(entry, now)
                if retry_after <= 0:
                    entry.generation += 1
                    entry.opened_at = now
                    entry.cooldown_seconds = policy.cooldown_seconds
                    entry.half_open_probe_in_flight = True
                    return ModelCircuitAdmission(
                        allowed=True,
                        permit=self._permit(
                            normalized_id,
                            entry,
                            policy,
                            half_open_probe=True,
                        ),
                        state=entry.state,
                        reason="half_open_probe_recovered",
                    )
                return ModelCircuitAdmission(
                    allowed=False,
                    permit=None,
                    state=entry.state,
                    reason="half_open_probe_in_flight",
                    retry_after_seconds=retry_after,
                )

            return ModelCircuitAdmission(
                allowed=True,
                permit=self._permit(normalized_id, entry, policy, half_open_probe=False),
                state=entry.state,
                reason="closed",
            )

    def record_success(self, permit: ModelCircuitPermit | None) -> ModelCircuitSnapshot | None:
        """Settle one admitted call as healthy, ignoring stale completions."""

        if permit is None:
            return None
        with self._store.locked_entry(permit.resource_id, create=False) as entry:
            if entry is None or permit.generation != entry.generation:
                return self._snapshot_locked(permit.resource_id, entry)
            if entry.state is ModelCircuitState.CLOSED and not permit.half_open_probe:
                entry.consecutive_failures = 0
                entry.last_error_type = None
            elif entry.state is ModelCircuitState.HALF_OPEN and permit.half_open_probe:
                entry.state = ModelCircuitState.CLOSED
                entry.consecutive_failures = 0
                entry.opened_at = None
                entry.cooldown_seconds = 0.0
                entry.half_open_probe_in_flight = False
                entry.last_error_type = None
            return self._snapshot_locked(permit.resource_id, entry)

    def record_failure(
        self,
        permit: ModelCircuitPermit | None,
        *,
        error_type: str,
    ) -> ModelCircuitSnapshot | None:
        """Settle one admitted provider failure, ignoring stale completions."""

        if permit is None:
            return None
        with self._store.locked_entry(permit.resource_id, create=False) as entry:
            if entry is None or permit.generation != entry.generation:
                return self._snapshot_locked(permit.resource_id, entry)
            normalized_error = str(error_type or "unknown_error").strip() or "unknown_error"
            if entry.state is ModelCircuitState.HALF_OPEN and permit.half_open_probe:
                entry.consecutive_failures = max(
                    entry.consecutive_failures,
                    permit.failure_threshold,
                )
                self._open_locked(entry, permit, error_type=normalized_error)
            elif entry.state is ModelCircuitState.CLOSED and not permit.half_open_probe:
                entry.consecutive_failures += 1
                entry.last_error_type = normalized_error
                if entry.consecutive_failures >= permit.failure_threshold:
                    self._open_locked(entry, permit, error_type=normalized_error)
            return self._snapshot_locked(permit.resource_id, entry)

    def record_abandoned(self, permit: ModelCircuitPermit | None) -> ModelCircuitSnapshot | None:
        """Release an unfinished permit without treating ordinary cancellation as failure."""

        if permit is None:
            return None
        with self._store.locked_entry(permit.resource_id, create=False) as entry:
            if entry is None or permit.generation != entry.generation:
                return self._snapshot_locked(permit.resource_id, entry)
            if entry.state is ModelCircuitState.HALF_OPEN and permit.half_open_probe:
                self._open_locked(
                    entry,
                    permit,
                    error_type=entry.last_error_type or "probe_abandoned",
                )
            return self._snapshot_locked(permit.resource_id, entry)

    def snapshot(self, resource_id: str) -> ModelCircuitSnapshot:
        """Return current state without creating an entry."""

        normalized_id = str(resource_id or "").strip()
        if not normalized_id:
            raise ValueError("model circuit breaker resource_id must not be empty")
        with self._store.locked_entry(normalized_id, create=False) as entry:
            return self._snapshot_locked(normalized_id, entry)

    def reset(self, resource_id: str | None = None) -> None:
        """Reset one model or every state in the configured store."""

        normalized_id = str(resource_id or "").strip() if resource_id is not None else None
        self._store.reset(normalized_id)

    @staticmethod
    def _permit(
        resource_id: str,
        entry: _CircuitEntry,
        policy: ModelCircuitBreakerPolicy,
        *,
        half_open_probe: bool,
    ) -> ModelCircuitPermit:
        return ModelCircuitPermit(
            resource_id=resource_id,
            generation=entry.generation,
            half_open_probe=half_open_probe,
            failure_threshold=policy.failure_threshold,
            cooldown_seconds=policy.cooldown_seconds,
        )

    def _open_locked(
        self,
        entry: _CircuitEntry,
        permit: ModelCircuitPermit,
        *,
        error_type: str,
    ) -> None:
        entry.state = ModelCircuitState.OPEN
        entry.generation += 1
        entry.opened_at = self._clock()
        entry.cooldown_seconds = permit.cooldown_seconds
        entry.half_open_probe_in_flight = False
        entry.last_error_type = error_type

    def _snapshot_locked(
        self,
        resource_id: str,
        entry: _CircuitEntry | None,
    ) -> ModelCircuitSnapshot:
        if entry is None:
            return ModelCircuitSnapshot(
                resource_id=resource_id,
                state=ModelCircuitState.CLOSED,
                consecutive_failures=0,
                generation=0,
                last_error_type=None,
                retry_after_seconds=None,
            )
        retry_after = (
            self._retry_after_locked(entry, self._clock())
            if entry.state in {ModelCircuitState.OPEN, ModelCircuitState.HALF_OPEN}
            else None
        )
        return ModelCircuitSnapshot(
            resource_id=resource_id,
            state=entry.state,
            consecutive_failures=entry.consecutive_failures,
            generation=entry.generation,
            last_error_type=entry.last_error_type,
            retry_after_seconds=retry_after,
        )

    @staticmethod
    def _retry_after_locked(entry: _CircuitEntry, now: float) -> float:
        if entry.opened_at is None:
            return 0.0
        return max(0.0, entry.cooldown_seconds - (now - entry.opened_at))


GLOBAL_MODEL_CIRCUIT_BREAKERS = ModelCircuitBreakerRegistry()


__all__ = [
    "GLOBAL_MODEL_CIRCUIT_BREAKERS",
    "ModelCircuitAdmission",
    "ModelCircuitBreakerPolicy",
    "ModelCircuitBreakerRegistry",
    "ModelCircuitPermit",
    "ModelCircuitSnapshot",
    "ModelCircuitState",
    "is_provider_health_failure",
]
