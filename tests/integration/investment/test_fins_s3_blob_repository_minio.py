"""真实 MinIO integration lane（S14-CTRL-07/08）。

验证 S3-compatible Fins blob repository 在真实 MinIO 上的行为：

- 真实 client 的 put/get/stat/list/delete、``get_object`` 的 SHA 验证与
  seekable 流契约、overwrite 原子性、pagination 穷尽/排序/staging 排除；
- staging 生命周期：commit 发布 + staging 清理、rollback 保留旧 final；
- 单 writer lease：第二个 writer 被拒绝；
- crash/restart：SIGKILL 后重放 remote journal 收敛（staged 窗口与
  copy 后 journal 写前窗口），最终 metadata 与全部 bytes digest 一致；
- startup production S3 / development FS 选择（S14-CTRL-05）；
- FS/S3 对同一 source bytes 的 evidence 主文件 bytes 逐字相同。

镜像固定 multi-arch digest；pytest 绝不隐式 pull，镜像缺失时 hard fail
并打印手动 ``docker pull`` 命令。fixture 用随机 container/bucket/credential、
owner label、``127.0.0.1`` 随机端口；cleanup 有界（60 秒），先复核 owner
label 再删除，禁止 prune/glob/compose down。
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterator

import boto3
import pytest
from botocore.config import Config as BotoConfig
from mypy_boto3_s3 import S3Client

from dayu.fins.domain.document_models import FilingCreateRequest, SourceHandle
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.evidence_locator import (
    REPOSITORY_ID,
    SCHEMA_VERSION,
    ArtifactKind,
    DocumentLocatorPayload,
    EvidenceLocatorRequest,
    LocatorKind,
    sha256_hex,
)
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.storage import FsSourceDocumentRepository
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.storage.remote_op_journal import list_journal_ids
from dayu.fins.storage.s3_file_store import S3FileStore
from dayu.fins.storage.s3_settings import parse_object_storage_settings, read_credentials
from dayu.fins.storage.writer_lease import acquire_writer_lease
from dayu.investment.config import PlatformDeploymentProfile, PlatformSettings

pytestmark = pytest.mark.integration

_MINIO_IMAGE = (
    "minio/minio:RELEASE.2025-09-07T16-13-09Z"
    "@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e"
)
"""固定的 multi-arch MinIO 镜像 digest（S14-CTRL-07）。"""

_LABEL_KEY = "dayu.test.owner"
_READY_TIMEOUT_SECONDS = 30
_HEALTH_POLL_INTERVAL_SECONDS = 0.25
_CLEANUP_TOTAL_TIMEOUT_SECONDS = 60
_PROCESS_WAIT_TIMEOUT_SECONDS = 15
_MARKER_WAIT_TIMEOUT_SECONDS = 20

_PDF_BYTES = b"%PDF-1.7\n" + b"1" * 2048
_PDF_SHA256 = hashlib.sha256(_PDF_BYTES).hexdigest()


class _MinioInfraError(RuntimeError):
    """MinIO integration fixture 基础设施失败。"""


@dataclass(frozen=True)
class _MinioCluster:
    """Slice-owned 临时 MinIO 资源句柄。

    Args:
        container_name: 独占容器名。
        owner_label: owner label 值。
        host_port: ``127.0.0.1`` 上映射的随机 API 端口。
        bucket: 随机 bucket 名。
        access_key: 临时 access key（仅测试）。
        secret_key: 临时 secret key（仅测试）。
        endpoint_url: 该 bucket 的端点 URL。
    """

    container_name: str
    owner_label: str
    host_port: int
    bucket: str
    access_key: str
    secret_key: str
    endpoint_url: str

    def new_store(self) -> S3FileStore:
        """构造指向该 cluster 的 S3FileStore。"""

        return S3FileStore(
            endpoint_url=self.endpoint_url,
            region="us-east-1",
            bucket=self.bucket,
            access_key=self.access_key,
            secret_key=self.secret_key,
        )


def _run_docker(args: list[str], *, timeout: int) -> str:
    """执行 docker 命令并返回 stdout。"""

    completed = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise _MinioInfraError(
            f"docker {' '.join(args)} 失败: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _free_tcp_port() -> int:
    """申请一个空闲 TCP 端口。"""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _assert_minio_image_present() -> None:
    """镜像缺失时 hard fail 并打印手动 pull 命令（S14-CTRL-07）。"""

    inspect = subprocess.run(
        ["docker", "image", "inspect", _MINIO_IMAGE],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if inspect.returncode != 0:
        raise _MinioInfraError(
            "MinIO 测试镜像缺失，请先手动执行:\n"
            f"docker pull {_MINIO_IMAGE}"
        )


def _wait_for_minio_health(host_port: int, container_name: str) -> None:
    """bounded 等待 MinIO HTTP health endpoint。"""

    url = f"http://127.0.0.1:{host_port}/minio/health/live"
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(_HEALTH_POLL_INTERVAL_SECONDS)
    raise _MinioInfraError(
        f"MinIO 容器 {container_name} 健康检查超时: {_READY_TIMEOUT_SECONDS} 秒"
    )


def _stop_container(container_name: str) -> None:
    """有界停止并删除容器（先复核 owner label）。"""

    inspect = subprocess.run(
        ["docker", "inspect", container_name, "--format", "{{.Name}} {{index .Config.Labels \"" + _LABEL_KEY + "\"}}"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if inspect.returncode != 0:
        return
    _run_docker(["stop", "--time=1", container_name], timeout=20)
    try:
        subprocess.run(
            ["docker", "wait", container_name],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        _run_docker(["kill", container_name], timeout=15)
    _run_docker(["rm", "-f", container_name], timeout=20)


@pytest.fixture(scope="module")
def minio_cluster(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_MinioCluster]:
    """启动并清理 Slice-owned 随机 MinIO 容器。"""

    _assert_minio_image_present()
    suffix = uuid.uuid4().hex[:12]
    container_name = f"dayu-minio-{suffix}"
    owner_label = str(uuid.uuid4())
    host_port = _free_tcp_port()
    access_key = f"minioaccess{suffix}"
    secret_key = f"minio{secrets.token_hex(20)}"
    bucket = f"dayu-test-{suffix}"

    _run_docker(
        [
            "run",
            "-d",
            "--name",
            container_name,
            "--label",
            f"{_LABEL_KEY}={owner_label}",
            "-p",
            f"127.0.0.1:{host_port}:9000",
            "-e",
            f"MINIO_ROOT_USER={access_key}",
            "-e",
            f"MINIO_ROOT_PASSWORD={secret_key}",
            _MINIO_IMAGE,
            "server",
            "/data",
        ],
        timeout=120,
    )
    cluster: _MinioCluster | None = None
    try:
        _wait_for_minio_health(host_port, container_name)
        client = boto3.client(
            "s3",
            endpoint_url=f"http://127.0.0.1:{host_port}",
            region_name="us-east-1",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(s3={"addressing_style": "path"}, signature_version="s3v4"),
        )
        client.create_bucket(Bucket=bucket)
        cluster = _MinioCluster(
            container_name=container_name,
            owner_label=owner_label,
            host_port=host_port,
            bucket=bucket,
            access_key=access_key,
            secret_key=secret_key,
            endpoint_url=f"http://127.0.0.1:{host_port}",
        )
        yield cluster
    finally:
        _stop_container(container_name)


def _raw_client(cluster: _MinioCluster) -> S3Client:
    """构造原始 boto3 client（绕过 S3FileStore 的 metadata 保护）。"""

    return boto3.client(
        "s3",
        endpoint_url=cluster.endpoint_url,
        region_name="us-east-1",
        aws_access_key_id=cluster.access_key,
        aws_secret_access_key=cluster.secret_key,
        config=BotoConfig(s3={"addressing_style": "path"}, signature_version="s3v4"),
    )


def test_minio_put_get_stat_list_delete_roundtrip(minio_cluster: _MinioCluster) -> None:
    """fresh bucket：put/get/stat/list/delete 全链路。"""

    store = minio_cluster.new_store()
    store.head_bucket()
    key = "AAPL/filings/fil_1/a.pdf"
    expected_sha = hashlib.sha256(_PDF_BYTES).hexdigest()
    meta = store.put_object(
        key,
        BytesIO(_PDF_BYTES),
        content_type="application/pdf",
        metadata={"source": "original"},
    )
    assert meta.size == len(_PDF_BYTES)
    assert meta.sha256 == expected_sha
    assert meta.uri == f"s3://{minio_cluster.bucket}/{key}"

    stat = store.stat_object(key)
    assert stat.size == len(_PDF_BYTES)
    assert stat.sha256 == expected_sha

    stream = store.get_object(key)
    try:
        assert stream.seekable()
        assert stream.read() == _PDF_BYTES
        stream.seek(0)
        assert stream.read() == _PDF_BYTES
    finally:
        stream.close()

    listed = store.list_objects("AAPL/filings/")
    assert [item.uri for item in listed] == [f"s3://{minio_cluster.bucket}/{key}"]

    store.delete_object(key)
    with pytest.raises(FileNotFoundError):
        store.stat_object(key)


def test_minio_get_object_sha_drift_fails_closed(minio_cluster: _MinioCluster) -> None:
    """远端 ``dayu-sha256`` metadata 与 bytes 不符 => ``get_object`` fail closed。"""

    store = minio_cluster.new_store()
    key = "AAPL/filings/fil_1/drift.pdf"
    store.put_object(
        key,
        BytesIO(_PDF_BYTES),
        content_type="application/pdf",
        metadata={"source": "original"},
    )
    raw = _raw_client(minio_cluster)
    raw.copy_object(
        Bucket=minio_cluster.bucket,
        CopySource={"Bucket": minio_cluster.bucket, "Key": key},
        Key=key,
        MetadataDirective="REPLACE",
        Metadata={"dayu-sha256": "0" * 64, "source": "original"},
    )
    with pytest.raises(OSError):
        store.get_object(key)


def test_minio_overwrite_atomic(minio_cluster: _MinioCluster) -> None:
    """overwrite 原子：同 key 二次 put 后读取为最新 bytes。"""

    store = minio_cluster.new_store()
    key = "AAPL/filings/fil_1/v.pdf"
    first = b"%PDF-1.7\nold"
    second = b"%PDF-1.7\nnew-content"
    store.put_object(key, BytesIO(first))
    store.put_object(key, BytesIO(second))
    stream = store.get_object(key)
    try:
        assert stream.read() == second
    finally:
        stream.close()
    stat = store.stat_object(key)
    assert stat.sha256 == hashlib.sha256(second).hexdigest()


def test_minio_list_pagination_sorting_staging_exclusion(minio_cluster: _MinioCluster) -> None:
    """list 穷尽 pagination、按 key 升序、排除 ``.dayu-staging/``。"""

    store = minio_cluster.new_store()
    for index in range(1005):
        store.put_object(
            f"PAG/{index:05d}.bin",
            BytesIO(b"x"),
            content_type="application/octet-stream",
        )
    store.stage_publish(operation_id="op-1", data=BytesIO(b"staged"))
    listed = store.list_objects("PAG/")
    assert len(listed) == 1005
    keys = [item.uri.split(f"s3://{minio_cluster.bucket}/", 1)[1] for item in listed]
    assert keys == sorted(keys)
    staging = store.list_objects(".dayu-staging/")
    assert staging == []
    store.delete_object("PAG/00000.bin")
    store.delete_object("PAG/01000.bin")


def test_minio_staging_commit_publishes_and_rollback_keeps_old(
    minio_cluster: _MinioCluster,
    tmp_path: Path,
) -> None:
    """batch stage -> commit 发布 final 并清理 staging；rollback 保留旧 final。"""

    store = minio_cluster.new_store()
    repository_set = build_fs_repository_set(workspace_root=tmp_path, file_store=store)
    core = repository_set.core
    handle = SourceHandle(ticker="AAPL", document_id="fil_1", source_kind="filing")

    token = core.begin_batch("AAPL")
    meta_a = core.store_file(handle, "a.pdf", BytesIO(b"a"))
    meta_b = core.store_file(handle, "b.pdf", BytesIO(b"b"))
    core.create_filing(
        FilingCreateRequest(
            ticker="AAPL",
            document_id="fil_1",
            internal_document_id="int_1",
            form_type="10-K",
            primary_document="a.pdf",
            file_entries=[
                {"name": "a.pdf", "uri": meta_a.uri, "size": meta_a.size, "sha256": meta_a.sha256},
                {"name": "b.pdf", "uri": meta_b.uri, "size": meta_b.size, "sha256": meta_b.sha256},
            ],
        )
    )
    core.commit_batch(token)
    assert store.list_objects("AAPL/filings/fil_1/a.pdf") != []
    assert store.list_objects("AAPL/filings/fil_1/b.pdf") != []
    assert store.list_objects(".dayu-staging/") == []

    # rollback：只 stage 不 commit，旧 final 原样保留。
    token = core.begin_batch("AAPL")
    core.store_file(handle, "a.pdf", BytesIO(b"new-a"))
    core.rollback_batch(token)
    stream = store.get_object("AAPL/filings/fil_1/a.pdf")
    try:
        assert stream.read() == b"a"
    finally:
        stream.close()


def test_minio_delete_entry_staged_delete_commit_removes_after_swap(
    minio_cluster: _MinioCluster,
    tmp_path: Path,
) -> None:
    """``delete_entry`` S3 模式：commit 后（swap 后）才远端删除。"""

    from dayu.fins.domain.document_models import FilingUpdateRequest

    store = minio_cluster.new_store()
    repository_set = build_fs_repository_set(workspace_root=tmp_path, file_store=store)
    core = repository_set.core
    handle = SourceHandle(ticker="AAPL", document_id="fil_1", source_kind="filing")

    token = core.begin_batch("AAPL")
    meta_a = core.store_file(handle, "a.pdf", BytesIO(b"a"))
    meta_b = core.store_file(handle, "b.pdf", BytesIO(b"b"))
    core.create_filing(
        FilingCreateRequest(
            ticker="AAPL",
            document_id="fil_1",
            internal_document_id="int_1",
            form_type="10-K",
            primary_document="a.pdf",
            file_entries=[
                {"name": "a.pdf", "uri": meta_a.uri, "size": meta_a.size, "sha256": meta_a.sha256},
                {"name": "b.pdf", "uri": meta_b.uri, "size": meta_b.size, "sha256": meta_b.sha256},
            ],
        )
    )
    core.commit_batch(token)

    token = core.begin_batch("AAPL")
    core.delete_entry(handle, "b.pdf")
    journal = core._remote_journal(token)
    assert any(
        t.final_key == "AAPL/filings/fil_1/b.pdf" and t.delete_state == "pending"
        for t in journal.delete_targets
    )
    assert store.list_objects("AAPL/filings/fil_1/b.pdf") != []
    core.update_filing(
        FilingUpdateRequest(
            ticker="AAPL",
            document_id="fil_1",
            internal_document_id="int_1",
            form_type="10-K",
            primary_document="a.pdf",
            file_entries=[
                {"name": "a.pdf", "uri": meta_a.uri, "size": meta_a.size, "sha256": meta_a.sha256},
            ],
        )
    )
    core.commit_batch(token)
    assert store.list_objects("AAPL/filings/fil_1/b.pdf") == []
    assert store.list_objects("AAPL/filings/fil_1/a.pdf") != []


def _repo_root() -> Path:
    """返回仓库根目录。"""

    return Path(__file__).resolve().parents[3]


def _build_crash_writer_script() -> str:
    """构造 crash writer 子进程脚本。

    两种模式：

    - ``staged``：begin + 两个 store_file 后写出 marker 并挂起（put 后 crash）；
    - ``first-copy``：commit 中第一个 CopyObject 完成后写出 marker 并短暂挂起
      （copy 后 journal 写前 crash 窗口）。
    """

    return r"""
import sys
import time
from io import BytesIO
from pathlib import Path

from dayu.fins.domain.document_models import FilingCreateRequest, SourceHandle
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.storage.s3_file_store import S3FileStore

endpoint, region, bucket, access, secret, workspace, marker_path, mode = sys.argv[1:9]
workspace_root = Path(workspace)
marker = Path(marker_path)
store = S3FileStore(
    endpoint_url=endpoint,
    region=region,
    bucket=bucket,
    access_key=access,
    secret_key=secret,
)
repository_set = build_fs_repository_set(workspace_root=workspace_root, file_store=store)
core = repository_set.core
handle = SourceHandle(ticker="AAPL", document_id="fil_1", source_kind="filing")
token = core.begin_batch("AAPL")
meta_a = core.store_file(handle, "a.pdf", BytesIO(b"a"))
meta_b = core.store_file(handle, "b.pdf", BytesIO(b"b"))
core.create_filing(
    FilingCreateRequest(
        ticker="AAPL",
        document_id="fil_1",
        internal_document_id="int_1",
        form_type="10-K",
        primary_document="a.pdf",
        file_entries=[
            {"name": "a.pdf", "uri": meta_a.uri, "size": meta_a.size, "sha256": meta_a.sha256},
            {"name": "b.pdf", "uri": meta_b.uri, "size": meta_b.size, "sha256": meta_b.sha256},
        ],
    )
)
if mode == "staged":
    marker.write_text("staged")
    while True:
        time.sleep(60)
orig = store.publish_staged
state = {"n": 0}


def wrapped(**kwargs):
    state["n"] += 1
    result = orig(**kwargs)
    if state["n"] == 1:
        marker.write_text("first-copy")
        time.sleep(2)
    return result


store.publish_staged = wrapped
core.commit_batch(token)
marker.write_text("committed")
"""


def _spawn_crash_writer(
    cluster: _MinioCluster,
    workspace_root: Path,
    marker_path: Path,
    mode: str,
) -> subprocess.Popen[str]:
    """启动 crash writer 子进程。"""

    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(_repo_root()), environment.get("PYTHONPATH", "")]
    )
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            _build_crash_writer_script(),
            cluster.endpoint_url,
            "us-east-1",
            cluster.bucket,
            cluster.access_key,
            cluster.secret_key,
            str(workspace_root),
            str(marker_path),
            mode,
        ],
        cwd=_repo_root(),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for_crash_marker(process: subprocess.Popen[str], marker_path: Path, expected: str) -> None:
    """bounded 等待 crash writer 写出指定 marker。"""

    deadline = time.monotonic() + _MARKER_WAIT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if marker_path.exists() and marker_path.read_text(encoding="utf-8").strip() == expected:
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"crash writer 在写出 marker 前退出: {expected}\nstdout={stdout}\nstderr={stderr}"
            )
        time.sleep(0.01)
    process.kill()
    process.communicate()
    raise AssertionError(f"等待 crash marker 超时: {expected}")


def _kill_and_collect(process: subprocess.Popen[str]) -> None:
    """SIGKILL 子进程并收口输出。"""

    process.kill()
    process.communicate()


def _assert_recovered_digests(store: S3FileStore, key: str, expected: bytes) -> None:
    """断言 recovery 后 final bytes 与期望 digest 一致。"""

    stream = store.get_object(key)
    try:
        assert stream.read() == expected
    finally:
        stream.close()


def test_minio_crash_restart_recovery_staged_window(minio_cluster: _MinioCluster, tmp_path: Path) -> None:
    """put 后 crash：restart 重放 journal 完成发布 + metadata roll-forward。"""

    marker = tmp_path / "marker-staged"
    writer = _spawn_crash_writer(minio_cluster, tmp_path, marker, "staged")
    try:
        _wait_for_crash_marker(writer, marker, "staged")
        _kill_and_collect(writer)
    finally:
        if writer.poll() is None:
            _kill_and_collect(writer)
    store = minio_cluster.new_store()
    repository_set = build_fs_repository_set(workspace_root=tmp_path, file_store=store)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    meta = source_repository.get_source_meta("AAPL", "fil_1", SourceKind.FILING)
    assert meta.get("primary_document") == "a.pdf"
    _assert_recovered_digests(store, "AAPL/filings/fil_1/a.pdf", b"a")
    _assert_recovered_digests(store, "AAPL/filings/fil_1/b.pdf", b"b")
    assert store.list_objects(".dayu-staging/") == []
    assert list_journal_ids(tmp_path / ".dayu") == []


def test_minio_crash_restart_recovery_after_first_copy(minio_cluster: _MinioCluster, tmp_path: Path) -> None:
    """第 1 个 copy 后、journal 写前 crash：recovery 幂等判定并完成剩余发布。"""

    marker = tmp_path / "marker-first-copy"
    writer = _spawn_crash_writer(minio_cluster, tmp_path, marker, "first-copy")
    try:
        _wait_for_crash_marker(writer, marker, "first-copy")
        _kill_and_collect(writer)
    finally:
        if writer.poll() is None:
            _kill_and_collect(writer)
    store = minio_cluster.new_store()
    repository_set = build_fs_repository_set(workspace_root=tmp_path, file_store=store)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    meta = source_repository.get_source_meta("AAPL", "fil_1", SourceKind.FILING)
    assert meta.get("primary_document") == "a.pdf"
    _assert_recovered_digests(store, "AAPL/filings/fil_1/a.pdf", b"a")
    _assert_recovered_digests(store, "AAPL/filings/fil_1/b.pdf", b"b")
    assert store.list_objects(".dayu-staging/") == []
    assert list_journal_ids(tmp_path / ".dayu") == []


def test_minio_writer_lease_rejects_second_writer(minio_cluster: _MinioCluster, tmp_path: Path) -> None:
    """两个独立 writer：第二个进程被 lease 拒绝；release 后可重获。"""

    first = acquire_writer_lease(tmp_path)
    try:
        script = (
            "import sys\n"
            "from pathlib import Path\n"
            "from dayu.fins.storage.writer_lease import WriterLeaseError, acquire_writer_lease\n"
            "root = Path(sys.argv[1])\n"
            "try:\n"
            "    acquire_writer_lease(root)\n"
            "except WriterLeaseError:\n"
            "    print('REJECTED')\n"
            "    sys.exit(0)\n"
            "print('ACQUIRED')\n"
            "sys.exit(1)\n"
        )
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(_repo_root()), environment.get("PYTHONPATH", "")]
        )
        completed = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path)],
            cwd=_repo_root(),
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0
        assert completed.stdout.strip() == "REJECTED"
    finally:
        first.release()
    reacquired = acquire_writer_lease(tmp_path)
    reacquired.release()


def test_minio_startup_production_s3_selection(minio_cluster: _MinioCluster) -> None:
    """startup production S3 / development FS 选择 + 真实 settings 路径探活。"""

    from dayu.services.startup_preparation import _should_build_s3_store

    production = PlatformSettings(
        enabled=True,
        profile=PlatformDeploymentProfile.PRODUCTION,
        use_in_memory_adapters=False,
        postgres_dsn_env="DAYU_PG_DSN_TEST",
        object_storage_env="DAYU_OBJECT_STORAGE_TEST",
        redis_env="DAYU_REDIS_TEST",
        auth_key_env="DAYU_AUTH_KEY_TEST",
    )
    development = PlatformSettings(
        enabled=True,
        profile=PlatformDeploymentProfile.DEVELOPMENT,
        use_in_memory_adapters=True,
    )
    assert _should_build_s3_store(production) is True
    assert _should_build_s3_store(development) is False

    settings_json = json.dumps(
        {
            "backend": "s3",
            "endpoint_url": minio_cluster.endpoint_url,
            "region": "us-east-1",
            "bucket": minio_cluster.bucket,
            "access_key_env": "DAYU_S3_ACCESS_TEST",
            "secret_key_env": "DAYU_S3_SECRET_TEST",
        }
    )
    env = {
        "DAYU_OBJECT_STORAGE_TEST": settings_json,
        "DAYU_S3_ACCESS_TEST": minio_cluster.access_key,
        "DAYU_S3_SECRET_TEST": minio_cluster.secret_key,
    }
    parsed = parse_object_storage_settings(env, "DAYU_OBJECT_STORAGE_TEST")
    credentials = read_credentials(env, parsed)
    store = S3FileStore(
        endpoint_url=parsed.endpoint_url,
        region=parsed.region,
        bucket=parsed.bucket,
        access_key=credentials.access_key,
        secret_key=credentials.secret_key,
    )
    store.head_bucket()


def _write_source_document(repository_set: _FsRepositorySet, content: bytes) -> None:
    """把同一 source 文档写入给定 repository set（core 级）。"""

    core = repository_set.core
    handle = SourceHandle(ticker="AAPL", document_id="fil_1", source_kind="filing")
    token = core.begin_batch("AAPL")
    meta = core.store_file(
        handle,
        "a.pdf",
        BytesIO(content),
        content_type="application/pdf",
    )
    core.create_filing(
        FilingCreateRequest(
            ticker="AAPL",
            document_id="fil_1",
            internal_document_id="int_1",
            form_type="10-K",
            primary_document="a.pdf",
            meta={"document_version": "v1", "source_fingerprint": _PDF_SHA256},
            file_entries=[
                {"name": "a.pdf", "uri": meta.uri, "size": meta.size, "sha256": meta.sha256},
            ],
        )
    )
    core.commit_batch(token)


def test_filesystem_and_real_minio_produce_byte_identical_pathless_locator_projection(
    minio_cluster: _MinioCluster,
    tmp_path: Path,
) -> None:
    """FS/real-MinIO 对同一 source 产生 byte-identical pathless locator。"""

    fs_root = tmp_path / "fs"
    s3_root = tmp_path / "s3"
    fs_set = build_fs_repository_set(workspace_root=fs_root)
    s3_set = build_fs_repository_set(workspace_root=s3_root, file_store=minio_cluster.new_store())
    _write_source_document(fs_set, _PDF_BYTES)
    _write_source_document(s3_set, _PDF_BYTES)

    fs_stream = fs_set.core.get_primary_source("AAPL", "fil_1", SourceKind.FILING).open()
    try:
        fs_bytes = fs_stream.read()
    finally:
        fs_stream.close()
    s3_stream = s3_set.core.get_primary_source("AAPL", "fil_1", SourceKind.FILING).open()
    try:
        s3_bytes = s3_stream.read()
    finally:
        s3_stream.close()
    assert fs_bytes == _PDF_BYTES
    assert s3_bytes == _PDF_BYTES
    assert s3_bytes == fs_bytes
    assert hashlib.sha256(s3_bytes).hexdigest() == hashlib.sha256(fs_bytes).hexdigest()

    request = EvidenceLocatorRequest(
        schema_version=SCHEMA_VERSION,
        repository_id=REPOSITORY_ID,
        ticker="AAPL",
        document_id="fil_1",
        source_kind=SourceKind.FILING,
        artifact_kind=ArtifactKind.SOURCE,
        document_version="v1",
        source_fingerprint=_PDF_SHA256,
        primary_content_sha256=_PDF_SHA256,
        locator_kind=LocatorKind.DOCUMENT,
        locator_payload=DocumentLocatorPayload(),
        locator_content_sha256=_PDF_SHA256,
    )
    fs_runtime = DefaultFinsRuntime.create(workspace_root=fs_root, repository_set=fs_set)
    s3_runtime = DefaultFinsRuntime.create(workspace_root=s3_root, repository_set=s3_set)
    fs_projection = fs_runtime.resolve_evidence_locator(request)
    s3_projection = s3_runtime.resolve_evidence_locator(request)
    fs_runtime.validate_evidence_locator(fs_projection)
    s3_runtime.validate_evidence_locator(s3_projection)

    fs_projection_bytes = fs_projection.to_json()
    s3_projection_bytes = s3_projection.to_json()
    assert fs_projection_bytes == s3_projection_bytes
    assert fs_projection.locator_content_sha256 == sha256_hex(_PDF_BYTES)
    assert s3_projection.locator_content_sha256 == sha256_hex(_PDF_BYTES)
    projection_json = fs_projection_bytes.decode("utf-8").lower()
    for forbidden in (
        "file://",
        "http://",
        "https://",
        "s3://",
        "bucket",
        "uri",
        "handle",
        str(fs_root).lower(),
        str(s3_root).lower(),
    ):
        assert forbidden not in projection_json
