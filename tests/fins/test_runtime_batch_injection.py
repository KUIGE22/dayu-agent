"""Fins runtime 同-core batch 注入单元测试（S14-CTRL-12）。

验证 runtime 从同一 repository_set 构造唯一 ``FsBatchingRepository``，
沿真实 callgraph（``_build_pipeline_for_ticker`` / ingestion factory）逐层
显式传递同一实例；同一 runtime 下所有 ``CnPipeline`` 共享同一
``CnPreparationGate`` 实例。
"""

from __future__ import annotations

from pathlib import Path

from dayu.fins.pipelines.cn_pipeline import CnPipeline
from dayu.fins.pipelines.sec_pipeline import SecPipeline
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.storage.fs_batching_repository import FsBatchingRepository


def _runtime(tmp_path: Path) -> DefaultFinsRuntime:
    """构造注入 repository_set 的 runtime。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    return DefaultFinsRuntime.create(workspace_root=tmp_path, repository_set=repository_set)


def _sec_pipeline(runtime: DefaultFinsRuntime, ticker: str = "AAPL") -> SecPipeline:
    """构建并收窄 SEC pipeline。"""

    pipeline = runtime._build_pipeline_for_ticker(ticker)
    assert isinstance(pipeline, SecPipeline)
    return pipeline


def _cn_pipeline(runtime: DefaultFinsRuntime, ticker: str = "600519") -> CnPipeline:
    """构建并收窄 CN pipeline。"""

    pipeline = runtime._build_pipeline_for_ticker(ticker)
    assert isinstance(pipeline, CnPipeline)
    return pipeline


def test_create_builds_unique_batching_repository(tmp_path: Path) -> None:
    """create 从同一 repository_set 构造唯一 FsBatchingRepository。"""

    runtime = _runtime(tmp_path)
    assert isinstance(runtime.batching_repository, FsBatchingRepository)


def test_runtime_holds_shared_preparation_gate(tmp_path: Path) -> None:
    """runtime 持有共享 CnPreparationGate（容量 1）。"""

    runtime = _runtime(tmp_path)
    assert runtime._preparation_gate.capacity == 1


def test_sec_pipeline_receives_same_batching(tmp_path: Path) -> None:
    """SEC pipeline 收到 runtime 同一 batching_repository。"""

    runtime = _runtime(tmp_path)
    pipeline = _sec_pipeline(runtime)
    assert pipeline._batching_repository is runtime.batching_repository


def test_cn_pipeline_receives_same_batching(tmp_path: Path) -> None:
    """CN pipeline 收到 runtime 同一 batching_repository。"""

    runtime = _runtime(tmp_path)
    pipeline = _cn_pipeline(runtime)
    assert pipeline._batching_repository is runtime.batching_repository


def test_cn_pipeline_receives_shared_gate(tmp_path: Path) -> None:
    """同一 runtime 多 CnPipeline 共享同一 preparation_gate 实例。"""

    runtime = _runtime(tmp_path)
    first = _cn_pipeline(runtime)
    second = _cn_pipeline(runtime, "000858")
    assert first._preparation_gate is runtime._preparation_gate
    assert second._preparation_gate is runtime._preparation_gate
    assert first._preparation_gate is second._preparation_gate


def test_ingestion_factory_chain_same_batching(tmp_path: Path) -> None:
    """ingestion factory 链（runtime → factory → pipeline）同实例。"""

    from dayu.fins.ingestion.pipeline_backends import PipelineIngestionBackend

    runtime = _runtime(tmp_path)
    factory = runtime.build_ingestion_service_factory()
    service = factory("AAPL")
    backend = service._backend
    assert isinstance(backend, PipelineIngestionBackend)
    pipeline = backend.pipeline
    assert isinstance(pipeline, SecPipeline)
    assert pipeline._batching_repository is runtime.batching_repository


def test_ingestion_factory_cn_same_gate(tmp_path: Path) -> None:
    """ingestion factory 路径的 CN pipeline 收到同一 gate。"""

    from dayu.fins.ingestion.pipeline_backends import PipelineIngestionBackend

    runtime = _runtime(tmp_path)
    factory = runtime.build_ingestion_service_factory()
    service = factory("600519")
    backend = service._backend
    assert isinstance(backend, PipelineIngestionBackend)
    pipeline = backend.pipeline
    assert isinstance(pipeline, CnPipeline)
    assert pipeline._preparation_gate is runtime._preparation_gate
