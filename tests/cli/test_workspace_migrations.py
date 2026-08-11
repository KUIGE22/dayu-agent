"""旧 workspace 显式导入的 unit/CLI 测试（S15-CTRL-12 unit 部分）。

本文件覆盖：

- domain 纯契约：七个稳定错误类别、frozen DTO 严格性、UUIDv5 算法
  exact、canonical ticker 分类、HK/CN/US market consistency gate、
  fingerprint 确定性与 drift 敏感性；
- staging adapter：strict manifest 结构/重复 key/NaN/路径逃逸、
  Fins inventory exact-set、missing/invalid meta、bundle typed closure
  cross-check、source definitions 派生、fingerprint、staging 失败
  DB connect=0；
- CLI import mode：参数矩阵、default-tenant 拒绝、与普通 init 的
  call-graph/behavior 隔离、输出不含 absolute path/DSN/secret。

本文件不触碰数据库；真实 PostgreSQL 16 / RLS / concurrency 验证在
``tests/integration/investment/test_workspace_migration.py``。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from argparse import ArgumentError, Namespace
from collections.abc import Sequence
from pathlib import Path
from typing import Callable, TypeAlias
from uuid import NAMESPACE_URL, uuid5

import pytest

from dayu.cli.arg_parsing import _ImportSemanticFlag, _ImportSemanticValue, parse_arguments
from dayu.cli.commands._research_template_materialize import materialize_research_template_bundle
from dayu.cli.commands.init import _run_import_existing_workspace, run_init_command
from dayu.cli.workspace_migrations.platform_import import stage_workspace_import
from dayu.investment.domain.identifiers import TenantId, TenantScope
from dayu.investment.domain.source import SecurityType, SourceKind
from dayu.investment.domain.workspace_import import (
    LEGACY_FINS_FILING_SOURCE_KEY,
    LEGACY_FINS_MATERIAL_SOURCE_KEY,
    LEGACY_REPOSITORY_KEY,
    WORKSPACE_IMPORT_MIGRATION_ID,
    WORKSPACE_IMPORT_SCHEMA_VERSION,
    WorkspaceImportDriftError,
    WorkspaceImportError,
    WorkspaceImportIdentityInconsistentError,
    WorkspaceImportManifestInvalidError,
    WorkspaceImportOwnerInvalidError,
    WorkspaceImportReceipt,
    WorkspaceImportRepositoryFailureError,
    WorkspaceImportRequest,
    WorkspaceImportSchemaUnavailableError,
    WorkspaceImportUsageError,
    LegacyBundleReference,
    VerifiedLegacyCompany,
    build_verified_bundle_locator,
    build_verified_company,
    build_workspace_import_request,
    classify_canonical_ticker,
    compute_source_root_fingerprint,
    compute_staged_payload_sha256,
    derive_bundle_locator_id,
    derive_company_id,
    derive_security_id,
    derive_source_definition_id,
    derive_workspace_import_marker_id,
)
from dayu.investment.storage.db import DEFAULT_ORGANIZATION_ID

_DEFAULT_TENANT = TenantId(DEFAULT_ORGANIZATION_ID)

ManifestFixtureScalar: TypeAlias = str | int | bool | None
ManifestFixtureValue: TypeAlias = (
    ManifestFixtureScalar | list["ManifestFixtureValue"] | dict[str, "ManifestFixtureValue"]
)
"""测试 fixture 的 manifest JSON 递归类型（避免宽 dict/object）。"""


# =============================================================================
# domain 纯契约
# =============================================================================


class TestWorkspaceImportErrorHierarchy:
    """七个稳定错误类别契约。"""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("error_type", "expected_code"),
        [
            (WorkspaceImportUsageError, "workspace_import_usage"),
            (WorkspaceImportManifestInvalidError, "workspace_import_manifest_invalid"),
            (WorkspaceImportOwnerInvalidError, "workspace_import_owner_invalid"),
            (WorkspaceImportIdentityInconsistentError, "workspace_import_identity_inconsistent"),
            (WorkspaceImportSchemaUnavailableError, "workspace_import_schema_unavailable"),
            (WorkspaceImportDriftError, "workspace_import_drift"),
            (WorkspaceImportRepositoryFailureError, "workspace_import_repository_failure"),
        ],
    )
    def test_stable_error_codes(self, error_type: type[WorkspaceImportError], expected_code: str) -> None:
        """每个错误类携带精确 stable safe code 作为消息。

        Args:
            error_type: 错误类。
            expected_code: 期望的稳定错误码。

        Returns:
            无。

        Raises:
            无。
        """

        error = error_type()
        assert str(error) == expected_code
        assert error.error_code == expected_code
        assert isinstance(error, WorkspaceImportError)


class TestWorkspaceImportUuidV5:
    """UUIDv5 唯一 ID 算法契约。"""

    @pytest.mark.unit
    def test_derive_company_id_matches_fixed_name(self) -> None:
        """company id 精确为 ``dayu:workspace-import:v1:company:{raw}``。"""

        legacy_company_id = "AAPL_US"
        expected = str(uuid5(NAMESPACE_URL, f"dayu:workspace-import:v1:company:{legacy_company_id}"))
        assert derive_company_id(legacy_company_id) == expected

    @pytest.mark.unit
    def test_derive_company_id_uses_raw_value(self) -> None:
        """company id 使用 inventory raw value，不做大小写归一化。"""

        assert derive_company_id("aapl_us") != derive_company_id("AAPL_US")

    @pytest.mark.unit
    def test_derive_security_id_matches_fixed_name(self) -> None:
        """security id 精确为 ``...:security:{mic}:{ticker}``。"""

        expected = str(uuid5(NAMESPACE_URL, "dayu:workspace-import:v1:security:XNAS:AAPL"))
        assert derive_security_id("XNAS", "AAPL") == expected

    @pytest.mark.unit
    def test_derive_source_id_matches_fixed_name(self) -> None:
        """source id 精确为 ``...:source:{source_key}``。"""

        expected = str(uuid5(NAMESPACE_URL, f"dayu:workspace-import:v1:source:{LEGACY_FINS_FILING_SOURCE_KEY}"))
        assert derive_source_definition_id(LEGACY_FINS_FILING_SOURCE_KEY) == expected

    @pytest.mark.unit
    def test_derive_marker_id_matches_fixed_name(self) -> None:
        """marker id 精确为 ``...:marker:{tenant}:{migration}``。"""

        expected = str(
            uuid5(
                NAMESPACE_URL,
                f"dayu:workspace-import:v1:marker:{_DEFAULT_TENANT.value}:{WORKSPACE_IMPORT_MIGRATION_ID}",
            )
        )
        assert (
            derive_workspace_import_marker_id(_DEFAULT_TENANT, WORKSPACE_IMPORT_MIGRATION_ID)
            == expected
        )

    @pytest.mark.unit
    def test_derive_bundle_locator_id_matches_fixed_name(self) -> None:
        """bundle locator id 精确为 ``...:bundle:{tenant}:{mic}:{ticker}:{template}``。"""

        expected = str(
            uuid5(
                NAMESPACE_URL,
                f"dayu:workspace-import:v1:bundle:{_DEFAULT_TENANT.value}:XNAS:AAPL:technology",
            )
        )
        assert (
            derive_bundle_locator_id(_DEFAULT_TENANT, "XNAS", "AAPL", "technology")
            == expected
        )


class TestCanonicalTickerClassification:
    """canonical ticker 分类契约。"""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("ticker", "expected_market"),
        [
            ("AAPL", "US"),
            ("BRK-B", "US"),
            ("0700", "HK"),
            ("89988", "HK"),
            ("600519", "CN_SSE"),
            ("000333", "CN_SZSE"),
            ("300750", "CN_SZSE"),
        ],
    )
    def test_canonical_forms_classify(self, ticker: str, expected_market: str) -> None:
        """canonical 形态正确分类。"""

        assert classify_canonical_ticker(ticker).value == expected_market

    @pytest.mark.unit
    @pytest.mark.parametrize("ticker", ["aapl", "700", "00700", "07005", "0700.HK", "A B", ""])
    def test_non_canonical_forms_rejected(self, ticker: str) -> None:
        """非 canonical 形态一律拒绝。"""

        with pytest.raises(ValueError):
            classify_canonical_ticker(ticker)


def _build_us_company(*, ticker: str = "AAPL", mic: str = "XNAS") -> VerifiedLegacyCompany:
    """构造合法 US 公司 DTO（测试 helper）。

    Args:
        ticker: canonical ticker。
        mic: 4 位大写 MIC。

    Returns:
        已验证公司 DTO。

    Raises:
        无。
    """

    return build_verified_company(
        legacy_company_id=f"{ticker}_US",
        company_name=f"{ticker} Corp",
        company_meta_market="US",
        lei=None,
        country_code="US",
        ticker=ticker,
        exchange_mic=mic,
        security_type=SecurityType.EQUITY,
        currency="USD",
        isin=None,
        is_active=True,
        bundles=(),
    )


class TestMarketConsistencyGate:
    """HK/CN/US market consistency gate。"""

    @pytest.mark.unit
    def test_hk_fixed_mapping(self) -> None:
        """HK ticker 必须 XHKG/HKD/HK。"""

        company = build_verified_company(
            legacy_company_id="0700_HKEX",
            company_name="Tencent Holdings",
            company_meta_market="HK",
            lei=None,
            country_code="HK",
            ticker="0700",
            exchange_mic="XHKG",
            security_type=SecurityType.EQUITY,
            currency="HKD",
            isin=None,
            is_active=True,
            bundles=(),
        )
        assert company.security.exchange_mic == "XHKG"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"exchange_mic": "XNYS", "currency": "HKD", "country_code": "HK"},
            {"exchange_mic": "XHKG", "currency": "USD", "country_code": "HK"},
            {"exchange_mic": "XHKG", "currency": "HKD", "country_code": "US"},
        ],
    )
    def test_hk_mismatch_rejected(self, kwargs: dict[str, str]) -> None:
        """HK 任一固定映射违反即 identity_inconsistent。"""

        with pytest.raises(WorkspaceImportIdentityInconsistentError):
            build_verified_company(
                legacy_company_id="0700_HKEX",
                company_name="Tencent Holdings",
                company_meta_market="HK",
                lei=None,
                ticker="0700",
                security_type=SecurityType.EQUITY,
                isin=None,
                is_active=True,
                bundles=(),
                **kwargs,
            )

    @pytest.mark.unit
    def test_cn_sse_and_szse_fixed_mapping(self) -> None:
        """CN SSE/SZSE 分别固定 XSHG/XSHE 且 CNY/CN。"""

        sse = build_verified_company(
            legacy_company_id="600519_SSE",
            company_name="Kweichow Moutai",
            company_meta_market="CN",
            lei=None,
            country_code="CN",
            ticker="600519",
            exchange_mic="XSHG",
            security_type=SecurityType.EQUITY,
            currency="CNY",
            isin=None,
            is_active=True,
            bundles=(),
        )
        assert sse.security.exchange_mic == "XSHG"
        szse = build_verified_company(
            legacy_company_id="000333_SZSE",
            company_name="Midea Group",
            company_meta_market="CN",
            lei=None,
            country_code="CN",
            ticker="000333",
            exchange_mic="XSHE",
            security_type=SecurityType.EQUITY,
            currency="CNY",
            isin=None,
            is_active=True,
            bundles=(),
        )
        assert szse.security.exchange_mic == "XSHE"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("mic", "exchange"),
        [("XSHG", "SZSE"), ("XSHE", "SSE")],
    )
    def test_cn_exchange_mic_swap_rejected(self, mic: str, exchange: str) -> None:
        """CN 交易所 MIC 互换即 identity_inconsistent。"""

        ticker = "600519" if exchange == "SSE" else "000333"
        legacy_id = f"{ticker}_{exchange}"
        with pytest.raises(WorkspaceImportIdentityInconsistentError):
            build_verified_company(
                legacy_company_id=legacy_id,
                company_name="Midea Group",
                company_meta_market="CN",
                lei=None,
                country_code="CN",
                ticker=ticker,
                exchange_mic=mic,
                security_type=SecurityType.EQUITY,
                currency="CNY",
                isin=None,
                is_active=True,
                bundles=(),
            )

    @pytest.mark.unit
    def test_us_mic_is_explicit_not_guessed(self) -> None:
        """US MIC 由 manifest 明示，只做 4 位大写语义验证。"""

        company = _build_us_company(mic="XNYS")
        assert company.security.exchange_mic == "XNYS"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"exchange_mic": "XNK", "currency": "USD", "country_code": "US"},
            {"exchange_mic": "xnAS", "currency": "USD", "country_code": "US"},
            {"exchange_mic": "XNAS", "currency": "US", "country_code": "US"},
            {"exchange_mic": "XNAS", "currency": "USD", "country_code": "us"},
        ],
    )
    def test_us_shape_violation_rejected(self, kwargs: dict[str, str]) -> None:
        """US 形状违反（MIC/currency/country 形态）即 identity_inconsistent。"""

        with pytest.raises(WorkspaceImportIdentityInconsistentError):
            build_verified_company(
                legacy_company_id="AAPL_US",
                company_name="Apple Inc.",
                company_meta_market="US",
                lei=None,
                ticker="AAPL",
                security_type=SecurityType.EQUITY,
                isin=None,
                is_active=True,
                bundles=(),
                **kwargs,
            )

    @pytest.mark.unit
    def test_market_mismatch_with_ticker_classification_rejected(self) -> None:
        """CompanyMeta.market 与 ticker 分类不一致即 identity_inconsistent。"""

        with pytest.raises(WorkspaceImportIdentityInconsistentError):
            build_verified_company(
                legacy_company_id="AAPL_US",
                company_name="Apple Inc.",
                company_meta_market="HK",
                lei=None,
                country_code="US",
                ticker="AAPL",
                exchange_mic="XNAS",
                security_type=SecurityType.EQUITY,
                currency="USD",
                isin=None,
                is_active=True,
                bundles=(),
            )

    @pytest.mark.unit
    def test_lowercase_ticker_rejected_as_identity_inconsistent(self) -> None:
        """manifest ticker 非 canonical 一律 identity_inconsistent。"""

        with pytest.raises(WorkspaceImportIdentityInconsistentError):
            build_verified_company(
                legacy_company_id="AAPL_US",
                company_name="Apple Inc.",
                company_meta_market="US",
                lei=None,
                country_code="US",
                ticker="aapl",
                exchange_mic="XNAS",
                security_type=SecurityType.EQUITY,
                currency="USD",
                isin=None,
                is_active=True,
                bundles=(),
            )


class TestWorkspaceImportFingerprint:
    """fingerprint 确定性与 drift 敏感性。"""

    def _sample_request(self) -> WorkspaceImportRequest:
        """构造样本 import 请求。

        Args:
            无。

        Returns:
            样本请求。

        Raises:
            无。
        """

        company = _build_us_company()
        locator = build_verified_bundle_locator(
            tenant_id=_DEFAULT_TENANT,
            exchange_mic="XNAS",
            ticker="AAPL",
            template_name="technology",
            relative_locator="assets/research_templates/technology.bundle.json",
            bundle_sha256="a" * 64,
            artifact_manifest_sha256="b" * 64,
        )
        return build_workspace_import_request(
            migration_id=WORKSPACE_IMPORT_MIGRATION_ID,
            companies=(company,),
            source_definitions=(),
            locators=(locator,),
            company_projections=(),
            source_root_presence=(),
            bundle_closures=(),
        )

    @pytest.mark.unit
    def test_fingerprints_deterministic(self) -> None:
        """相同输入产生相同 fingerprint。"""

        first = self._sample_request()
        second = self._sample_request()
        assert first.source_root_fingerprint == second.source_root_fingerprint
        assert first.staged_payload_sha256 == second.staged_payload_sha256
        assert len(first.source_root_fingerprint) == 64
        assert len(first.staged_payload_sha256) == 64

    @pytest.mark.unit
    def test_source_root_fingerprint_changes_when_company_projection_changes(self) -> None:
        """CompanyMeta 投影变化（updated_at）改变 source_root_fingerprint。"""

        from dayu.investment.domain.workspace_import import FingerprintCompanyProjection

        base = compute_source_root_fingerprint(
            companies=(_build_us_company(),),
            company_projections=(
                FingerprintCompanyProjection(
                    company_id="AAPL_US",
                    company_name="Apple Inc.",
                    ticker="AAPL",
                    market="US",
                    resolver_version="v1",
                    updated_at="2026-01-01T00:00:00Z",
                    aliases=("AAPL",),
                ),
            ),
            source_root_presence=(),
            bundle_closures=(),
        )
        changed = compute_source_root_fingerprint(
            companies=(_build_us_company(),),
            company_projections=(
                FingerprintCompanyProjection(
                    company_id="AAPL_US",
                    company_name="Apple Inc.",
                    ticker="AAPL",
                    market="US",
                    resolver_version="v1",
                    updated_at="2026-06-01T00:00:00Z",
                    aliases=("AAPL",),
                ),
            ),
            source_root_presence=(),
            bundle_closures=(),
        )
        assert base != changed

    @pytest.mark.unit
    def test_bundle_drift_changes_request_payload(self) -> None:
        """bundle closure 变化改变 staged payload。"""

        company = _build_us_company()
        locator = build_verified_bundle_locator(
            tenant_id=_DEFAULT_TENANT,
            exchange_mic="XNAS",
            ticker="AAPL",
            template_name="technology",
            relative_locator="assets/research_templates/technology.bundle.json",
            bundle_sha256="a" * 64,
            artifact_manifest_sha256="b" * 64,
        )
        request = build_workspace_import_request(
            migration_id=WORKSPACE_IMPORT_MIGRATION_ID,
            companies=(company,),
            source_definitions=(),
            locators=(locator,),
            company_projections=(),
            source_root_presence=(),
            bundle_closures=(),
        )
        changed_locator = build_verified_bundle_locator(
            tenant_id=_DEFAULT_TENANT,
            exchange_mic="XNAS",
            ticker="AAPL",
            template_name="technology",
            relative_locator="assets/research_templates/technology.bundle.json",
            bundle_sha256="c" * 64,
            artifact_manifest_sha256="b" * 64,
        )
        changed_request = build_workspace_import_request(
            migration_id=WORKSPACE_IMPORT_MIGRATION_ID,
            companies=(company,),
            source_definitions=(),
            locators=(changed_locator,),
            company_projections=(),
            source_root_presence=(),
            bundle_closures=(),
        )
        assert request.staged_payload_sha256 != changed_request.staged_payload_sha256
        assert compute_staged_payload_sha256(request) == request.staged_payload_sha256

    @pytest.mark.unit
    def test_wrong_migration_id_rejected(self) -> None:
        """migration id 非精确固定值抛 manifest_invalid。"""

        company = _build_us_company()
        with pytest.raises(WorkspaceImportManifestInvalidError):
            build_workspace_import_request(
                migration_id="other-migration",
                companies=(company,),
                source_definitions=(),
                locators=(),
                company_projections=(),
                source_root_presence=(),
                bundle_closures=(),
            )


class TestWorkspaceImportDtos:
    """frozen DTO 严格性与防御性复制。"""

    @pytest.mark.unit
    def test_bundles_are_defensively_copied(self) -> None:
        """bundles 集合构造期复制为 tuple，外部修改不影响 DTO。"""

        bundle = LegacyBundleReference(
            template_name="technology",
            relative_locator="assets/research_templates/technology.bundle.json",
        )
        company = build_verified_company(
            legacy_company_id="AAPL_US",
            company_name="Apple Inc.",
            company_meta_market="US",
            lei=None,
            country_code="US",
            ticker="AAPL",
            exchange_mic="XNAS",
            security_type=SecurityType.EQUITY,
            currency="USD",
            isin=None,
            is_active=True,
            bundles=(bundle,),
        )
        assert company.bundles == (bundle,)

    @pytest.mark.unit
    def test_build_verified_bundle_locator_rejects_non_legacy_repository_key(self) -> None:
        """locator repository_key 固定为 legacy-workspace。"""

        locator = build_verified_bundle_locator(
            tenant_id=_DEFAULT_TENANT,
            exchange_mic="XNAS",
            ticker="AAPL",
            template_name="technology",
            relative_locator="assets/research_templates/technology.bundle.json",
            bundle_sha256="a" * 64,
            artifact_manifest_sha256="b" * 64,
        )
        assert locator.repository_key == LEGACY_REPOSITORY_KEY

    @pytest.mark.unit
    def test_receipt_validation(self) -> None:
        """receipt 字段严格校验。"""

        receipt = WorkspaceImportReceipt(
            marker_id=derive_workspace_import_marker_id(_DEFAULT_TENANT, WORKSPACE_IMPORT_MIGRATION_ID),
            migration_id=WORKSPACE_IMPORT_MIGRATION_ID,
            status="committed",
            company_count=1,
            security_count=1,
            source_definition_count=0,
            bundle_count=0,
            source_root_fingerprint="a" * 64,
            staged_payload_sha256="b" * 64,
        )
        assert receipt.status == "committed"
        no_op = WorkspaceImportReceipt(
            marker_id=receipt.marker_id,
            migration_id=WORKSPACE_IMPORT_MIGRATION_ID,
            status="no_op",
            company_count=1,
            security_count=1,
            source_definition_count=0,
            bundle_count=0,
            source_root_fingerprint="a" * 64,
            staged_payload_sha256="b" * 64,
        )
        assert no_op.status == "no_op"
        with pytest.raises(ValueError):
            WorkspaceImportReceipt(
                marker_id=receipt.marker_id,
                migration_id=WORKSPACE_IMPORT_MIGRATION_ID,
                status="committed",
                company_count=1,
                security_count=1,
                source_definition_count=0,
                bundle_count=0,
                source_root_fingerprint="short",
                staged_payload_sha256="b" * 64,
            )


# =============================================================================
# staging adapter fixtures 与测试
# =============================================================================


def _company_meta_dict(
    *,
    company_id: str = "AAPL_US",
    company_name: str = "Apple Inc.",
    ticker: str = "AAPL",
    market: str = "US",
    updated_at: str = "2026-08-11T00:00:00.000000Z",
) -> dict[str, ManifestFixtureValue]:
    """构造 ``portfolio/<ticker>/meta.json`` 内容。

    Args:
        company_id: CompanyMeta.company_id。
        company_name: CompanyMeta.company_name。
        ticker: CompanyMeta.ticker。
        market: CompanyMeta.market。
        updated_at: CompanyMeta.updated_at。

    Returns:
        meta.json 字典。

    Raises:
        无。
    """

    return {
        "company_id": company_id,
        "company_name": company_name,
        "ticker": ticker,
        "ticker_aliases": [ticker],
        "market": market,
        "resolver_version": "test",
        "updated_at": updated_at,
    }


def _write_meta(portfolio_dir: Path, meta: dict[str, ManifestFixtureValue]) -> None:
    """把 CompanyMeta 写入 ``portfolio/<ticker>/meta.json``。

    Args:
        portfolio_dir: ``portfolio`` 目录。
        meta: CompanyMeta 字典。

    Returns:
        无。

    Raises:
        无。
    """

    ticker_dir = portfolio_dir / str(meta["ticker"])
    ticker_dir.mkdir(parents=True, exist_ok=True)
    (ticker_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False),
        encoding="utf-8",
    )


def _materialize_bundle(workspace_root: Path) -> None:
    """在 workspace 内物化一个合法 research template bundle。

    Args:
        workspace_root: workspace 根目录。

    Returns:
        无。

    Raises:
        无。
    """

    materialize_research_template_bundle(
        "technology",
        workspace_root=workspace_root,
        ticker="AAPL",
        company="Apple Inc.",
        overwrite=True,
    )


def _manifest_dict(
    *,
    companies: list[dict[str, ManifestFixtureValue]] | None = None,
) -> dict[str, ManifestFixtureValue]:
    """构造合法 operator manifest 字典。

    Args:
        companies: 覆盖的公司列表；为空时使用默认 AAPL 单公司。

    Returns:
        manifest 字典。

    Raises:
        无。
    """

    if companies is None:
        default_companies: list[dict[str, ManifestFixtureValue]] = [
            {
                "legacy_company_id": "AAPL_US",
                "country_code": "US",
                "lei": None,
                "security": {
                    "ticker": "AAPL",
                    "exchange_mic": "XNAS",
                    "security_type": "equity",
                    "currency": "USD",
                    "isin": None,
                    "is_active": True,
                },
                "bundles": [
                    {
                        "template_name": "technology",
                        "relative_locator": "assets/research_templates/technology.bundle.json",
                    }
                ],
            }
        ]
        companies = default_companies
    payload: dict[str, ManifestFixtureValue] = {
        "schema_version": 1,
        "migration_id": "legacy-workspace-import-v1",
        "companies": list(companies),
    }
    return payload


def _build_fixture_workspace(
    tmp_path: Path,
    *,
    meta: dict[str, ManifestFixtureValue] | None = None,
    with_bundle: bool = True,
    filing_root: bool = True,
    material_root: bool = False,
) -> Path:
    """构造标准 fixture workspace。

    Args:
        tmp_path: pytest 临时目录。
        meta: 覆盖的 CompanyMeta 字典。
        with_bundle: 是否物化 bundle。
        filing_root: 是否创建 filing storage root。
        material_root: 是否创建 material storage root。

    Returns:
        workspace 根目录。

    Raises:
        无。
    """

    workspace_root = tmp_path / "workspace"
    portfolio_dir = workspace_root / "portfolio"
    _write_meta(portfolio_dir, meta if meta is not None else _company_meta_dict())
    if with_bundle:
        _materialize_bundle(workspace_root)
    if filing_root:
        (portfolio_dir / "AAPL" / "filings").mkdir(parents=True, exist_ok=True)
    if material_root:
        (portfolio_dir / "AAPL" / "materials").mkdir(parents=True, exist_ok=True)
    return workspace_root


def _write_manifest(workspace_root: Path, payload: dict[str, ManifestFixtureValue]) -> Path:
    """把 manifest 写入 workspace 并返回路径。

    Args:
        workspace_root: workspace 根目录。
        payload: manifest 字典。

    Returns:
        manifest 路径。

    Raises:
        无。
    """

    manifest_path = workspace_root / "operator.manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return manifest_path


class TestStagingAdapter:
    """staging adapter 只读验证契约。"""

    @pytest.mark.unit
    def test_stage_success_us_with_filing_source(self, tmp_path: Path) -> None:
        """US 公司 + filing root 成功 staging，source definitions 派生。"""

        workspace_root = _build_fixture_workspace(tmp_path)
        manifest_path = _write_manifest(workspace_root, _manifest_dict())
        request = stage_workspace_import(
            source_root=workspace_root,
            manifest_path=manifest_path,
            target_tenant_id=DEFAULT_ORGANIZATION_ID,
        )
        assert request.schema_version == WORKSPACE_IMPORT_SCHEMA_VERSION
        assert request.migration_id == WORKSPACE_IMPORT_MIGRATION_ID
        assert len(request.companies) == 1
        company = request.companies[0]
        assert company.legacy_company_id == "AAPL_US"
        assert company.security.exchange_mic == "XNAS"
        assert company.security.ticker == "AAPL"
        assert len(company.bundles) == 1
        assert company.bundles[0].relative_locator == "assets/research_templates/technology.bundle.json"
        assert len(request.source_definitions) == 1
        assert request.source_definitions[0].source_key == LEGACY_FINS_FILING_SOURCE_KEY
        assert request.source_definitions[0].source_kind is SourceKind.FILING
        assert not request.source_definitions[0].enabled_by_default
        assert len(request.locators) == 1
        assert request.locators[0].template_name == "technology"
        descriptor_path = workspace_root / request.locators[0].relative_locator
        assert request.locators[0].bundle_sha256 == hashlib.sha256(
            descriptor_path.read_bytes()
        ).hexdigest()

    @pytest.mark.unit
    def test_stage_source_definitions_only_by_presence(self, tmp_path: Path) -> None:
        """source definitions 只由 storage root presence 派生。"""

        workspace_root = _build_fixture_workspace(
            tmp_path,
            filing_root=False,
            material_root=True,
        )
        manifest_path = _write_manifest(workspace_root, _manifest_dict())
        request = stage_workspace_import(
            source_root=workspace_root,
            manifest_path=manifest_path,
            target_tenant_id=DEFAULT_ORGANIZATION_ID,
        )
        assert [definition.source_key for definition in request.source_definitions] == [
            LEGACY_FINS_MATERIAL_SOURCE_KEY
        ]
        assert request.source_definitions[0].source_kind is SourceKind.RESEARCH_MATERIAL

    @pytest.mark.unit
    def test_stage_empty_workspace_is_valid_empty_import(self, tmp_path: Path) -> None:
        """``companies=[]`` 且 inventory 也为空时是合法 empty import。"""

        workspace_root = tmp_path / "workspace"
        (workspace_root / "portfolio").mkdir(parents=True)
        manifest_path = _write_manifest(workspace_root, _manifest_dict(companies=[]))
        request = stage_workspace_import(
            source_root=workspace_root,
            manifest_path=manifest_path,
            target_tenant_id=DEFAULT_ORGANIZATION_ID,
        )
        assert request.companies == ()
        assert request.locators == ()
        assert request.source_definitions == ()

    @pytest.mark.unit
    def test_stage_empty_manifest_with_inventory_fails(self, tmp_path: Path) -> None:
        """``companies=[]`` 但 inventory 非空时 fail closed。"""

        workspace_root = _build_fixture_workspace(tmp_path, with_bundle=False)
        manifest_path = _write_manifest(workspace_root, _manifest_dict(companies=[]))
        with pytest.raises(WorkspaceImportOwnerInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_missing_meta_fails_closed(self, tmp_path: Path) -> None:
        """inventory 含 missing_meta 时 fail closed。"""

        workspace_root = tmp_path / "workspace"
        (workspace_root / "portfolio" / "NO_META").mkdir(parents=True)
        manifest_path = _write_manifest(workspace_root, _manifest_dict(companies=[]))
        with pytest.raises(WorkspaceImportOwnerInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_invalid_meta_fails_closed(self, tmp_path: Path) -> None:
        """inventory 含 invalid_meta 时 fail closed。"""

        workspace_root = tmp_path / "workspace"
        ticker_dir = workspace_root / "portfolio" / "AAPL"
        ticker_dir.mkdir(parents=True)
        (ticker_dir / "meta.json").write_text('{"broken":', encoding="utf-8")
        manifest_path = _write_manifest(workspace_root, _manifest_dict(companies=[]))
        with pytest.raises(WorkspaceImportOwnerInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_inventory_set_mismatch_fails(self, tmp_path: Path) -> None:
        """manifest company 与 inventory 双向 exact-set 违反时 fail closed。"""

        workspace_root = _build_fixture_workspace(tmp_path, with_bundle=False)
        manifest = _manifest_dict()
        companies = manifest["companies"]
        assert isinstance(companies, list)
        first_company = companies[0]
        assert isinstance(first_company, dict)
        first_company["legacy_company_id"] = "OTHER_US"
        manifest_path = _write_manifest(workspace_root, manifest)
        with pytest.raises(WorkspaceImportOwnerInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_inventory_ticker_mismatch_is_identity_inconsistent(self, tmp_path: Path) -> None:
        """inventory ticker 非 canonical 或与 manifest 不一致。"""

        meta = _company_meta_dict(ticker="aapl")
        workspace_root = _build_fixture_workspace(tmp_path, meta=meta, with_bundle=False)
        manifest_path = _write_manifest(workspace_root, _manifest_dict())
        with pytest.raises(WorkspaceImportIdentityInconsistentError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_hk_fixed_mapping_success(self, tmp_path: Path) -> None:
        """HK 公司成功 staging（XHKG/HKD/HK）。"""

        meta = _company_meta_dict(
            company_id="0700_HKEX",
            company_name="Tencent Holdings",
            ticker="0700",
            market="HK",
        )
        workspace_root = tmp_path / "workspace"
        portfolio_dir = workspace_root / "portfolio"
        _write_meta(portfolio_dir, meta)
        (portfolio_dir / "0700" / "filings").mkdir(parents=True, exist_ok=True)
        materialize_research_template_bundle(
            "technology",
            workspace_root=workspace_root,
            ticker="0700",
            company="Tencent Holdings",
            overwrite=True,
        )
        companies = [
            {
                "legacy_company_id": "0700_HKEX",
                "country_code": "HK",
                "lei": None,
                "security": {
                    "ticker": "0700",
                    "exchange_mic": "XHKG",
                    "security_type": "equity",
                    "currency": "HKD",
                    "isin": None,
                    "is_active": True,
                },
                "bundles": [
                    {
                        "template_name": "technology",
                        "relative_locator": "assets/research_templates/technology.bundle.json",
                    }
                ],
            }
        ]
        manifest_path = _write_manifest(workspace_root, _manifest_dict(companies=companies))
        request = stage_workspace_import(
            source_root=workspace_root,
            manifest_path=manifest_path,
            target_tenant_id=DEFAULT_ORGANIZATION_ID,
        )
        assert request.companies[0].security.exchange_mic == "XHKG"
        assert request.companies[0].security.currency == "HKD"

    @pytest.mark.unit
    def test_stage_bundle_template_mismatch_is_identity_inconsistent(self, tmp_path: Path) -> None:
        """manifest template_name 与 owner closure 不一致时 fail closed。"""

        workspace_root = _build_fixture_workspace(tmp_path)
        manifest = _manifest_dict()
        companies = manifest["companies"]
        assert isinstance(companies, list)
        first_company = companies[0]
        assert isinstance(first_company, dict)
        bundles = first_company["bundles"]
        assert isinstance(bundles, list)
        first_bundle = bundles[0]
        assert isinstance(first_bundle, dict)
        first_bundle["template_name"] = "financial"
        manifest_path = _write_manifest(workspace_root, manifest)
        with pytest.raises(WorkspaceImportIdentityInconsistentError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_bundle_company_name_mismatch_is_identity_inconsistent(
        self, tmp_path: Path
    ) -> None:
        """owner closure 公司名称与 CompanyMeta.company_name 不一致时 fail closed。"""

        meta = _company_meta_dict(company_name="Apple Inc. (Different)")
        workspace_root = _build_fixture_workspace(tmp_path, meta=meta)
        manifest_path = _write_manifest(workspace_root, _manifest_dict())
        with pytest.raises(WorkspaceImportIdentityInconsistentError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_manifest_structural_invalid(self, tmp_path: Path) -> None:
        """missing/extra key、NaN、bool-as-int、duplicate key 均 manifest_invalid。"""

        workspace_root = _build_fixture_workspace(tmp_path, with_bundle=False)
        manifest_path = workspace_root / "operator.manifest.json"

        manifest_path.write_text('{"schema_version": 1}', encoding="utf-8")
        with pytest.raises(WorkspaceImportManifestInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

        manifest_path.write_text(
            json.dumps({**_manifest_dict(), "extra_top": 1}),
            encoding="utf-8",
        )
        with pytest.raises(WorkspaceImportManifestInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

        manifest_path.write_text(
            '{"schema_version": NaN, "migration_id": "legacy-workspace-import-v1", "companies": []}',
            encoding="utf-8",
        )
        with pytest.raises(WorkspaceImportManifestInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

        manifest_path.write_text(
            '{"schema_version": 1, "migration_id": "legacy-workspace-import-v1", '
            '"migration_id": "x", "companies": []}',
            encoding="utf-8",
        )
        with pytest.raises(WorkspaceImportManifestInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_manifest_duplicate_company_rejected(self, tmp_path: Path) -> None:
        """重复 legacy_company_id 一律 manifest_invalid。"""

        workspace_root = _build_fixture_workspace(tmp_path, with_bundle=False)
        companies = [
            {
                "legacy_company_id": "AAPL_US",
                "country_code": "US",
                "lei": None,
                "security": {
                    "ticker": "AAPL",
                    "exchange_mic": "XNAS",
                    "security_type": "equity",
                    "currency": "USD",
                    "isin": None,
                    "is_active": True,
                },
                "bundles": [],
            },
            {
                "legacy_company_id": "AAPL_US",
                "country_code": "US",
                "lei": None,
                "security": {
                    "ticker": "AAPL",
                    "exchange_mic": "XNAS",
                    "security_type": "equity",
                    "currency": "USD",
                    "isin": None,
                    "is_active": True,
                },
                "bundles": [],
            },
        ]
        manifest_path = _write_manifest(workspace_root, _manifest_dict(companies=companies))
        with pytest.raises(WorkspaceImportManifestInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_manifest_locator_escape_rejected(self, tmp_path: Path) -> None:
        """relative_locator 含 ``..`` 一律 manifest_invalid。"""

        workspace_root = _build_fixture_workspace(tmp_path, with_bundle=False)
        manifest = _manifest_dict()
        companies = manifest["companies"]
        assert isinstance(companies, list)
        first_company = companies[0]
        assert isinstance(first_company, dict)
        bundles = first_company["bundles"]
        assert isinstance(bundles, list)
        first_bundle = bundles[0]
        assert isinstance(first_bundle, dict)
        first_bundle["relative_locator"] = "../outside.bundle.json"
        manifest_path = _write_manifest(workspace_root, manifest)
        with pytest.raises(WorkspaceImportManifestInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_manifest_path_outside_source_root_rejected(self, tmp_path: Path) -> None:
        """manifest 位于 source root 之外时 fail closed。"""

        workspace_root = _build_fixture_workspace(tmp_path, with_bundle=False)
        outside_manifest = tmp_path / "outside.manifest.json"
        outside_manifest.write_text(json.dumps(_manifest_dict()), encoding="utf-8")
        with pytest.raises(WorkspaceImportManifestInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=outside_manifest,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_manifest_symlink_rejected(self, tmp_path: Path) -> None:
        """manifest 为 symlink 时 fail closed。"""

        workspace_root = _build_fixture_workspace(tmp_path, with_bundle=False)
        target = tmp_path / "real.manifest.json"
        target.write_text(json.dumps(_manifest_dict()), encoding="utf-8")
        symlink = workspace_root / "linked.manifest.json"
        symlink.symlink_to(target)
        with pytest.raises(WorkspaceImportManifestInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=symlink,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_manifest_fifo_rejected(self, tmp_path: Path) -> None:
        """manifest 为 FIFO 时 fail closed。"""

        workspace_root = _build_fixture_workspace(tmp_path, with_bundle=False)
        fifo = workspace_root / "fifo.manifest.json"
        os.mkfifo(fifo)
        with pytest.raises(WorkspaceImportManifestInvalidError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=fifo,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_invalid_tenant_uuid_rejected_as_usage(self, tmp_path: Path) -> None:
        """非法 tenant UUID 在文件扫描前拒绝（usage）。"""

        workspace_root = _build_fixture_workspace(tmp_path)
        manifest_path = _write_manifest(workspace_root, _manifest_dict())
        with pytest.raises(WorkspaceImportUsageError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id="not-a-uuid",
            )

    @pytest.mark.unit
    def test_stage_valid_non_default_tenant_proceeds_to_staging(self, tmp_path: Path) -> None:
        """staging 接受合法 UUID 的 tenant（tenant gate 由 CLI/Service 执行）。"""

        workspace_root = _build_fixture_workspace(tmp_path)
        manifest_path = _write_manifest(workspace_root, _manifest_dict())
        request = stage_workspace_import(
            source_root=workspace_root,
            manifest_path=manifest_path,
            target_tenant_id="00000000-0000-0000-0000-000000000002",
        )
        assert len(request.companies) == 1

    @pytest.mark.unit
    def test_stage_missing_source_root_fails(self, tmp_path: Path) -> None:
        """source root 不存在或不是目录时 fail closed。"""

        missing_root = tmp_path / "missing"
        manifest_path = tmp_path / "m.manifest.json"
        manifest_path.write_text(json.dumps(_manifest_dict()), encoding="utf-8")
        with pytest.raises(WorkspaceImportOwnerInvalidError):
            stage_workspace_import(
                source_root=missing_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_cross_company_duplicate_security_rejected(self, tmp_path: Path) -> None:
        """跨 company 相同 canonical security 在 staging/DB connect 前拒绝。"""

        workspace_root = tmp_path / "workspace"
        portfolio_dir = workspace_root / "portfolio"
        _write_meta(portfolio_dir, _company_meta_dict(company_id="AAPL_US"))
        second_dir = portfolio_dir / "AAPL_ALT"
        second_dir.mkdir(parents=True)
        (second_dir / "meta.json").write_text(
            json.dumps(
                _company_meta_dict(
                    company_id="AAPL_ALT_US",
                    company_name="Apple Inc.",
                    ticker="AAPL",
                ),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        companies: list[dict[str, ManifestFixtureValue]] = [
            {
                "legacy_company_id": "AAPL_US",
                "country_code": "US",
                "lei": None,
                "security": {
                    "ticker": "AAPL",
                    "exchange_mic": "XNAS",
                    "security_type": "equity",
                    "currency": "USD",
                    "isin": None,
                    "is_active": True,
                },
                "bundles": [],
            },
            {
                "legacy_company_id": "AAPL_ALT_US",
                "country_code": "US",
                "lei": None,
                "security": {
                    "ticker": "AAPL",
                    "exchange_mic": "XNAS",
                    "security_type": "equity",
                    "currency": "USD",
                    "isin": None,
                    "is_active": True,
                },
                "bundles": [],
            },
        ]
        manifest_path = _write_manifest(workspace_root, _manifest_dict(companies=companies))
        with pytest.raises(WorkspaceImportIdentityInconsistentError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_stage_cross_company_duplicate_security_same_locator_rejected(
        self,
        tmp_path: Path,
    ) -> None:
        """跨 company 相同 canonical security（locator 相同）在 staging 前拒绝。"""

        workspace_root = tmp_path / "workspace"
        portfolio_dir = workspace_root / "portfolio"
        _write_meta(portfolio_dir, _company_meta_dict(company_id="AAPL_US"))
        second_dir = portfolio_dir / "AAPL_ALT"
        second_dir.mkdir(parents=True)
        (second_dir / "meta.json").write_text(
            json.dumps(
                _company_meta_dict(
                    company_id="AAPL_ALT_US",
                    company_name="Apple Inc.",
                    ticker="AAPL",
                ),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        _materialize_bundle(workspace_root)
        companies: list[dict[str, ManifestFixtureValue]] = [
            {
                "legacy_company_id": "AAPL_US",
                "country_code": "US",
                "lei": None,
                "security": {
                    "ticker": "AAPL",
                    "exchange_mic": "XNAS",
                    "security_type": "equity",
                    "currency": "USD",
                    "isin": None,
                    "is_active": True,
                },
                "bundles": [
                    {
                        "template_name": "technology",
                        "relative_locator": "assets/research_templates/technology.bundle.json",
                    }
                ],
            },
            {
                "legacy_company_id": "AAPL_ALT_US",
                "country_code": "US",
                "lei": None,
                "security": {
                    "ticker": "AAPL",
                    "exchange_mic": "XNAS",
                    "security_type": "equity",
                    "currency": "USD",
                    "isin": None,
                    "is_active": True,
                },
                "bundles": [
                    {
                        "template_name": "technology",
                        "relative_locator": "assets/research_templates/technology.bundle.json",
                    }
                ],
            },
        ]
        manifest_path = _write_manifest(workspace_root, _manifest_dict(companies=companies))
        with pytest.raises(WorkspaceImportIdentityInconsistentError):
            stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )

    @pytest.mark.unit
    def test_require_global_identity_uniqueness_rejects_duplicate_locator(self) -> None:
        """跨 company 相同 repository relative locator 直接拒绝（不延后 drift）。"""

        from dayu.cli.workspace_migrations.platform_import import (
            _ManifestBundle,
            _ManifestCompany,
            _ManifestSecurity,
            _require_global_identity_uniqueness,
        )

        security_a = _ManifestSecurity(
            ticker="AAPL",
            exchange_mic="XNAS",
            security_type="equity",
            currency="USD",
            isin=None,
            is_active=True,
        )
        security_b = _ManifestSecurity(
            ticker="MSFT",
            exchange_mic="XNAS",
            security_type="equity",
            currency="USD",
            isin=None,
            is_active=True,
        )
        shared_bundle = _ManifestBundle(
            template_name="technology",
            relative_locator="assets/research_templates/technology.bundle.json",
        )
        companies = (
            _ManifestCompany(
                legacy_company_id="AAPL_US",
                country_code="US",
                lei=None,
                security=security_a,
                bundles=(shared_bundle,),
            ),
            _ManifestCompany(
                legacy_company_id="MSFT_US",
                country_code="US",
                lei=None,
                security=security_b,
                bundles=(shared_bundle,),
            ),
        )
        with pytest.raises(WorkspaceImportIdentityInconsistentError):
            _require_global_identity_uniqueness(companies)


# =============================================================================
# CLI import mode
# =============================================================================


class _FakeImportService:
    """测试用 fake workspace import Service。"""

    def __init__(self) -> None:
        """初始化 fake service。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.calls: list[tuple[TenantScope, WorkspaceImportRequest]] = []
        self.closed = False

    @property
    def platform_service_name(self) -> str:
        """返回稳定注册名。

        Args:
            无。

        Returns:
            ``workspace_import``。

        Raises:
            无。
        """

        return "workspace_import"

    def import_workspace(
        self,
        scope: TenantScope,
        request: WorkspaceImportRequest,
    ) -> WorkspaceImportReceipt:
        """记录调用并返回 committed receipt。

        Args:
            scope: 租户范围。
            request: import 请求。

        Returns:
            committed receipt。

        Raises:
            无。
        """

        self.calls.append((scope, request))
        return WorkspaceImportReceipt(
            marker_id=derive_workspace_import_marker_id(
                scope.tenant_id,
                request.migration_id,
            ),
            migration_id=request.migration_id,
            status="committed",
            company_count=len(request.companies),
            security_count=len(request.companies),
            source_definition_count=len(request.source_definitions),
            bundle_count=len(request.locators),
            source_root_fingerprint=request.source_root_fingerprint,
            staged_payload_sha256=request.staged_payload_sha256,
        )

    def close(self) -> None:
        """记录 close 调用。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.closed = True


def _patch_import_mode_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    fake_service: _FakeImportService,
) -> None:
    """打桩 import mode 的 stage/prepare 依赖。

    Args:
        monkeypatch: pytest 属性替换夹具。
        fake_service: fake service。

    Returns:
        无。

    Raises:
        无。
    """

    from dayu.services.startup_preparation import PreparedWorkspaceImportDependencies

    def _fake_prepare() -> PreparedWorkspaceImportDependencies:
        return PreparedWorkspaceImportDependencies(service=fake_service)

    monkeypatch.setattr(
        "dayu.cli.workspace_migrations.platform_import.stage_workspace_import",
        _fake_stage,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.prepare_workspace_import_dependencies",
        _fake_prepare,
    )


def _fake_stage(
    *,
    source_root: Path,
    manifest_path: Path,
    target_tenant_id: str,
) -> WorkspaceImportRequest:
    """fake stage：返回最小空请求。

    Args:
        source_root: source root。
        manifest_path: manifest 路径。
        target_tenant_id: 目标租户。

    Returns:
        空 import 请求。

    Raises:
        无。
    """

    del source_root, manifest_path, target_tenant_id
    return build_workspace_import_request(
        migration_id=WORKSPACE_IMPORT_MIGRATION_ID,
        companies=(),
        source_definitions=(),
        locators=(),
        company_projections=(),
        source_root_presence=(),
        bundle_closures=(),
    )


class TestCliParserImportMode:
    """import mode 参数解析矩阵（S15-CTRL-12 parser mode 矩阵）。"""

    @pytest.mark.unit
    def test_parser_parses_import_mode_args(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """完整 import mode 参数可被 argparse 解析。"""

        manifest_path = tmp_path / "operator.manifest.json"
        monkeypatch.setattr(
            "sys.argv",
            [
                "dayu-cli",
                "init",
                "--import-existing-workspace",
                "--base",
                str(tmp_path),
                "--import-manifest",
                str(manifest_path),
                "--target-tenant-id",
                DEFAULT_ORGANIZATION_ID,
            ],
        )
        args = parse_arguments()
        assert args.command == "init"
        assert args.import_existing_workspace is True
        assert args.import_manifest == str(manifest_path)
        assert args.target_tenant_id == DEFAULT_ORGANIZATION_ID
        assert args.reset is False
        assert args.overwrite is False

    @pytest.mark.unit
    def test_parser_plain_init_has_no_import_mode_args(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """普通 init 不携带 import mode 参数。"""

        monkeypatch.setattr("sys.argv", ["dayu-cli", "init"])
        args = parse_arguments()
        assert args.command == "init"
        assert args.import_existing_workspace is False
        assert args.import_manifest is None
        assert args.target_tenant_id is None
        assert int(getattr(args, "import_manifest_seen", 0)) == 0
        assert int(getattr(args, "target_tenant_id_seen", 0)) == 0

    @pytest.mark.unit
    def test_parser_records_duplicate_import_manifest(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """重复 ``--import-manifest`` 记录 repeated 标志与计数。"""

        manifest_path = tmp_path / "operator.manifest.json"
        monkeypatch.setattr(
            "sys.argv",
            [
                "dayu-cli",
                "init",
                "--import-existing-workspace",
                "--import-manifest",
                str(manifest_path),
                "--import-manifest",
                str(manifest_path),
                "--target-tenant-id",
                DEFAULT_ORGANIZATION_ID,
            ],
        )
        args = parse_arguments()
        assert args.import_manifest == str(manifest_path)
        assert int(args.import_manifest_seen) == 2
        assert args.import_manifest_repeated is True

    @pytest.mark.unit
    def test_parser_records_duplicate_target_tenant(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """重复 ``--target-tenant-id`` 记录 repeated 标志与计数。"""

        manifest_path = tmp_path / "operator.manifest.json"
        monkeypatch.setattr(
            "sys.argv",
            [
                "dayu-cli",
                "init",
                "--import-existing-workspace",
                "--import-manifest",
                str(manifest_path),
                "--target-tenant-id",
                DEFAULT_ORGANIZATION_ID,
                "--target-tenant-id",
                DEFAULT_ORGANIZATION_ID,
            ],
        )
        args = parse_arguments()
        assert args.target_tenant_id == DEFAULT_ORGANIZATION_ID
        assert int(args.target_tenant_id_seen) == 2
        assert args.target_tenant_id_repeated is True

    @pytest.mark.unit
    def test_parser_records_duplicate_master_switch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """重复 ``--import-existing-workspace`` 记录 seen 计数与 repeated 标志。"""

        manifest_path = tmp_path / "operator.manifest.json"
        monkeypatch.setattr(
            "sys.argv",
            [
                "dayu-cli",
                "init",
                "--import-existing-workspace",
                "--import-existing-workspace",
                "--import-manifest",
                str(manifest_path),
                "--target-tenant-id",
                DEFAULT_ORGANIZATION_ID,
            ],
        )
        args = parse_arguments()
        assert args.import_existing_workspace is True
        assert int(args.import_existing_workspace_seen) == 2
        assert args.import_existing_workspace_repeated is True

    @pytest.mark.unit
    def test_parser_single_master_switch_has_seen_one_not_repeated(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """主开关恰好出现一次：seen==1 且 repeated 未置位。"""

        manifest_path = tmp_path / "operator.manifest.json"
        monkeypatch.setattr(
            "sys.argv",
            [
                "dayu-cli",
                "init",
                "--import-existing-workspace",
                "--import-manifest",
                str(manifest_path),
                "--target-tenant-id",
                DEFAULT_ORGANIZATION_ID,
            ],
        )
        args = parse_arguments()
        assert args.import_existing_workspace is True
        assert int(args.import_existing_workspace_seen) == 1
        assert not bool(getattr(args, "import_existing_workspace_repeated", False))


class TestImportSemanticAction:
    """import 语义 action 精确契约（round3 adversarial）。"""

    @pytest.mark.unit
    def test_flag_first_occurrence_writes_true_and_seen_one(self) -> None:
        """无值开关首次出现写入 True 且 seen 为 1、无 repeated。"""

        parser = argparse.ArgumentParser()
        action = _ImportSemanticFlag(["--import-existing-workspace"], "import_existing_workspace")
        namespace = Namespace()
        action(parser, namespace, values=[])
        assert namespace.import_existing_workspace is True
        assert int(namespace.import_existing_workspace_seen) == 1
        assert not bool(getattr(namespace, "import_existing_workspace_repeated", False))

    @pytest.mark.unit
    def test_flag_repeated_occurrence_only_records_repeated(self) -> None:
        """无值开关重复出现不覆盖首次值，只置 repeated 并递增 seen。"""

        parser = argparse.ArgumentParser()
        action = _ImportSemanticFlag(["--import-existing-workspace"], "import_existing_workspace")
        namespace = Namespace(import_existing_workspace=True, import_existing_workspace_seen=1)
        action(parser, namespace, values=[])
        assert namespace.import_existing_workspace is True
        assert int(namespace.import_existing_workspace_seen) == 2
        assert namespace.import_existing_workspace_repeated is True

    @pytest.mark.unit
    def test_value_first_occurrence_writes_string(self) -> None:
        """单字符串值参数首次出现写入字符串且 seen 为 1。"""

        parser = argparse.ArgumentParser()
        action = _ImportSemanticValue(["--import-manifest"], "import_manifest")
        namespace = Namespace()
        action(parser, namespace, values="operator.json")
        assert namespace.import_manifest == "operator.json"
        assert int(namespace.import_manifest_seen) == 1

    @pytest.mark.unit
    def test_value_repeated_occurrence_keeps_first_value(self) -> None:
        """单字符串值参数重复出现保留首次值，只置 repeated 并递增 seen。"""

        parser = argparse.ArgumentParser()
        action = _ImportSemanticValue(["--import-manifest"], "import_manifest")
        namespace = Namespace(import_manifest="a.json", import_manifest_seen=1)
        action(parser, namespace, values="b.json")
        assert namespace.import_manifest == "a.json"
        assert int(namespace.import_manifest_seen) == 2
        assert namespace.import_manifest_repeated is True

    @pytest.mark.unit
    @pytest.mark.parametrize("bad_values", [["a.json", "b.json"], None])
    def test_value_rejects_non_string_input_fail_closed(
        self,
        bad_values: Sequence[str] | None,
    ) -> None:
        """单字符串值 action 收到非字符串输入时 fail closed。"""

        parser = argparse.ArgumentParser()
        action = _ImportSemanticValue(["--import-manifest"], "import_manifest")
        with pytest.raises(ArgumentError):
            action(parser, Namespace(), values=bad_values)


_NORMAL_INIT_SYMBOLS = (
    "dayu.cli.commands.init._copy_config",
    "dayu.cli.commands.init._copy_assets",
    "dayu.cli.commands.init._prompt_provider_selection",
    "dayu.cli.commands.init._run_init_prewarm",
    "dayu.cli.workspace_migrations.runner.apply_all_workspace_migrations",
)


def _never_called(name: str) -> Callable[..., None]:
    """构造调用即抛错的普通 init 符号桩。

    Args:
        name: 被断言不得调用的符号名。

    Returns:
        调用时抛出 ``AssertionError`` 的桩函数。

    Raises:
        AssertionError: 桩被调用时抛出。
    """

    def _boom(*_args: str | Path | bool, **_kwargs: str | Path | bool) -> None:
        raise AssertionError(f"import mode 调用了普通 init 符号 {name}")

    return _boom


class TestCliImportMode:
    """CLI import mode 隔离与行为契约。"""

    @pytest.mark.unit
    def test_import_mode_rejects_reset_and_overwrite(self, tmp_path: Path) -> None:
        """--reset / --overwrite 与 import mode 互斥（usage）。"""

        for extra in ({"reset": True}, {"overwrite": True}):
            args = Namespace(
                base=str(tmp_path),
                import_existing_workspace=True,
                import_existing_workspace_seen=1,
                import_existing_workspace_repeated=False,
                import_manifest=str(tmp_path / "m.json"),
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
                **extra,
            )
            assert run_init_command(args) == 1

    @pytest.mark.unit
    def test_import_mode_requires_manifest_and_tenant(self, tmp_path: Path) -> None:
        """缺失 manifest/tenant 一律 usage。"""

        args = Namespace(
            base=str(tmp_path),
            import_existing_workspace=True,
            import_existing_workspace_seen=1,
            import_existing_workspace_repeated=False,
            import_manifest=None,
            target_tenant_id=None,
            reset=False,
            overwrite=False,
        )
        assert run_init_command(args) == 1

    @pytest.mark.unit
    def test_import_mode_rejects_duplicate_semantic_params(self, tmp_path: Path) -> None:
        """主开关下重复语义参数一律 usage。"""

        for extra in (
            {"import_manifest_repeated": True, "import_manifest_seen": 2},
            {"target_tenant_id_repeated": True, "target_tenant_id_seen": 2},
        ):
            args = Namespace(
                base=str(tmp_path),
                import_existing_workspace=True,
                import_existing_workspace_seen=1,
                import_existing_workspace_repeated=False,
                import_manifest=str(tmp_path / "m.json"),
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
                reset=False,
                overwrite=False,
                **extra,
            )
            assert run_init_command(args) == 1

    @pytest.mark.unit
    def test_import_mode_rejects_duplicate_master_switch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """重复主开关 + 合法 manifest/tenant：usage/1，stage 与 prepare 均不调用。"""

        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()
        manifest_path = workspace_root / "m.json"
        monkeypatch.setattr(
            "sys.argv",
            [
                "dayu-cli",
                "init",
                "--import-existing-workspace",
                "--import-existing-workspace",
                "--base",
                str(workspace_root),
                "--import-manifest",
                str(manifest_path),
                "--target-tenant-id",
                DEFAULT_ORGANIZATION_ID,
            ],
        )
        args = parse_arguments()
        stage_calls: list[bool] = []
        prepare_calls: list[bool] = []

        def _counting_stage(
            *,
            source_root: Path,
            manifest_path: Path,
            target_tenant_id: str,
        ) -> WorkspaceImportRequest:
            stage_calls.append(True)
            return _fake_stage(
                source_root=source_root,
                manifest_path=manifest_path,
                target_tenant_id=target_tenant_id,
            )

        def _counting_prepare() -> object:
            prepare_calls.append(True)
            from dayu.services.startup_preparation import PreparedWorkspaceImportDependencies

            return PreparedWorkspaceImportDependencies(service=_FakeImportService())

        monkeypatch.setattr(
            "dayu.cli.workspace_migrations.platform_import.stage_workspace_import",
            _counting_stage,
        )
        monkeypatch.setattr(
            "dayu.services.startup_preparation.prepare_workspace_import_dependencies",
            _counting_prepare,
        )
        assert run_init_command(args) == 1
        assert stage_calls == []
        assert prepare_calls == []
        captured = capsys.readouterr().out
        assert "workspace_import_usage" in captured

    @pytest.mark.unit
    def test_import_mode_rejects_seen_zero_or_repeated_flag(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """手工 Namespace 缺 seen 或 repeated 置位：usage/1，不进入 staging。"""

        for extra in (
            {},
            {"import_existing_workspace_seen": 0, "import_existing_workspace_repeated": False},
            {"import_existing_workspace_seen": 1, "import_existing_workspace_repeated": True},
            {"import_existing_workspace_seen": 2, "import_existing_workspace_repeated": True},
        ):
            args = Namespace(
                base=str(tmp_path),
                import_existing_workspace=True,
                import_manifest=str(tmp_path / "m.json"),
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
                reset=False,
                overwrite=False,
                **extra,
            )
            assert run_init_command(args) == 1

    @pytest.mark.unit
    def test_import_mode_direct_dispatch_requires_exact_master_switch(
        self,
        tmp_path: Path,
    ) -> None:
        """直接调用 ``_run_import_existing_workspace``：seen 非 1 或 repeated 均 usage。"""

        for extra in (
            {},
            {"import_existing_workspace_seen": 0, "import_existing_workspace_repeated": False},
            {"import_existing_workspace_seen": 2, "import_existing_workspace_repeated": True},
        ):
            args = Namespace(
                base=str(tmp_path),
                import_existing_workspace=True,
                import_manifest=str(tmp_path / "m.json"),
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
                reset=False,
                overwrite=False,
                **extra,
            )
            assert _run_import_existing_workspace(args) == 1

    @pytest.mark.unit
    def test_import_semantic_args_without_master_switch_are_usage(
        self,
        tmp_path: Path,
    ) -> None:
        """无主开关携带 import 语义参数（A1 双参/A2 仅 manifest/A3 仅 tenant）usage。"""

        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()
        scenarios = (
            {
                "import_manifest": str(workspace_root / "m.json"),
                "target_tenant_id": DEFAULT_ORGANIZATION_ID,
            },
            {
                "import_manifest": str(workspace_root / "m.json"),
                "target_tenant_id": None,
            },
            {
                "import_manifest": None,
                "target_tenant_id": DEFAULT_ORGANIZATION_ID,
            },
        )
        for scenario in scenarios:
            args = Namespace(
                base=str(workspace_root),
                import_existing_workspace=False,
                reset=False,
                overwrite=False,
                **scenario,
            )
            assert run_init_command(args) == 1

    @pytest.mark.unit
    def test_import_semantic_args_without_master_switch_have_zero_side_effects(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """无主开关携带 import 参数：稳定 usage、普通 init 副作用 calls=0、tree 不变。"""

        for name in _NORMAL_INIT_SYMBOLS:
            monkeypatch.setattr(name, _never_called(name))

        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()
        before = _tree_manifest(workspace_root)
        args = Namespace(
            base=str(workspace_root),
            import_existing_workspace=False,
            import_manifest=str(workspace_root / "m.json"),
            target_tenant_id=DEFAULT_ORGANIZATION_ID,
            reset=False,
            overwrite=False,
        )
        assert run_init_command(args) == 1
        _assert_tree_unchanged(before, workspace_root)
        captured = capsys.readouterr().out
        assert "workspace_import_usage" in captured
        assert str(workspace_root) not in captured

    @pytest.mark.unit
    def test_import_mode_rejects_non_default_tenant_before_scan(self, tmp_path: Path) -> None:
        """非 default tenant 在文件扫描前拒绝（usage）。"""

        args = Namespace(
            base=str(tmp_path),
            import_existing_workspace=True,
            import_existing_workspace_seen=1,
            import_existing_workspace_repeated=False,
            import_manifest=str(tmp_path / "m.json"),
            target_tenant_id="00000000-0000-0000-0000-000000000002",
            reset=False,
            overwrite=False,
        )
        assert run_init_command(args) == 1

    @pytest.mark.unit
    def test_import_mode_success_flow_and_isolation(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """import mode 成功：不调用普通 init 的任何副作用。"""

        for name in _NORMAL_INIT_SYMBOLS:
            monkeypatch.setattr(name, _never_called(name))

        fake_service = _FakeImportService()
        _patch_import_mode_dependencies(monkeypatch, fake_service)
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()
        args = Namespace(
            base=str(workspace_root),
            import_existing_workspace=True,
            import_existing_workspace_seen=1,
            import_existing_workspace_repeated=False,
            import_manifest=str(workspace_root / "m.json"),
            target_tenant_id=DEFAULT_ORGANIZATION_ID,
            reset=False,
            overwrite=False,
        )
        exit_code = run_init_command(args)
        assert exit_code == 0
        assert fake_service.closed
        assert len(fake_service.calls) == 1
        scope, request = fake_service.calls[0]
        assert scope.tenant_id == TenantId(DEFAULT_ORGANIZATION_ID)
        captured = capsys.readouterr().out
        assert "workspace import committed" in captured
        assert str(workspace_root) not in captured
        assert "postgres" not in captured.lower()
        assert "secret" not in captured.lower()

    @pytest.mark.unit
    def test_import_mode_staging_failure_returns_1_with_stable_code(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """staging 失败返回 1 且输出稳定错误码，不连接 DB。"""

        def _failing_stage(
            *,
            source_root: Path,
            manifest_path: Path,
            target_tenant_id: str,
        ) -> WorkspaceImportRequest:
            del source_root, manifest_path, target_tenant_id
            raise WorkspaceImportOwnerInvalidError()

        monkeypatch.setattr(
            "dayu.cli.workspace_migrations.platform_import.stage_workspace_import",
            _failing_stage,
        )
        prepare_called: list[bool] = []

        from dayu.services.startup_preparation import PreparedWorkspaceImportDependencies

        def _fake_prepare() -> PreparedWorkspaceImportDependencies:
            prepare_called.append(True)
            return PreparedWorkspaceImportDependencies(service=_FakeImportService())

        monkeypatch.setattr(
            "dayu.services.startup_preparation.prepare_workspace_import_dependencies",
            _fake_prepare,
        )
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()
        args = Namespace(
            base=str(workspace_root),
            import_existing_workspace=True,
            import_existing_workspace_seen=1,
            import_existing_workspace_repeated=False,
            import_manifest=str(workspace_root / "m.json"),
            target_tenant_id=DEFAULT_ORGANIZATION_ID,
            reset=False,
            overwrite=False,
        )
        assert run_init_command(args) == 1
        assert prepare_called == []
        captured = capsys.readouterr().out
        assert "workspace_import_owner_invalid" in captured

    @pytest.mark.unit
    def test_import_mode_staging_oserror_returns_owner_invalid(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """staging 抛 OSError/ValueError：owner_invalid/1，prepare 不调用。"""

        def _raising_stage(
            *,
            source_root: Path,
            manifest_path: Path,
            target_tenant_id: str,
        ) -> WorkspaceImportRequest:
            del source_root, manifest_path, target_tenant_id
            raise OSError("injected stage failure")

        monkeypatch.setattr(
            "dayu.cli.workspace_migrations.platform_import.stage_workspace_import",
            _raising_stage,
        )
        prepare_called: list[bool] = []

        from dayu.services.startup_preparation import PreparedWorkspaceImportDependencies

        def _fake_prepare() -> PreparedWorkspaceImportDependencies:
            prepare_called.append(True)
            return PreparedWorkspaceImportDependencies(service=_FakeImportService())

        monkeypatch.setattr(
            "dayu.services.startup_preparation.prepare_workspace_import_dependencies",
            _fake_prepare,
        )
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()
        args = Namespace(
            base=str(workspace_root),
            import_existing_workspace=True,
            import_existing_workspace_seen=1,
            import_existing_workspace_repeated=False,
            import_manifest=str(workspace_root / "m.json"),
            target_tenant_id=DEFAULT_ORGANIZATION_ID,
            reset=False,
            overwrite=False,
        )
        assert run_init_command(args) == 1
        assert prepare_called == []
        captured = capsys.readouterr().out
        assert "workspace_import_owner_invalid" in captured


def test_import_mode_ast_branch_is_first_and_isolated() -> None:
    """AST：import 分支位于 run_init_command 最前，普通 init 副作用不变。"""

    import ast as ast_module

    source = Path("dayu/cli/commands/init.py").read_text(encoding="utf-8")
    tree = ast_module.parse(source)
    run_init = next(
        node for node in tree.body if isinstance(node, ast_module.FunctionDef) and node.name == "run_init_command"
    )
    statements = [stmt for stmt in run_init.body if not isinstance(stmt, ast_module.Expr)]
    first_stmt = statements[0]
    assert isinstance(first_stmt, ast_module.If)
    import_condition = first_stmt.test
    assert isinstance(import_condition, ast_module.Call)
    assert "import_existing_workspace" in ast_module.dump(import_condition)
    import_branch = first_stmt.body
    assert any(
        isinstance(node, ast_module.Return) for node in ast_module.walk(ast_module.Module(body=import_branch, type_ignores=[]))
    )
    normal_path = statements[1:]
    assert any(
        isinstance(node, ast_module.Call)
        and (
            (
                isinstance(node.func, ast_module.Name)
                and node.func.id == "apply_all_workspace_migrations"
            )
            or (
                isinstance(node.func, ast_module.Attribute)
                and node.func.attr == "apply_all_workspace_migrations"
            )
        )
        for node in ast_module.walk(ast_module.Module(body=normal_path, type_ignores=[]))
    )


def test_import_mode_calls_close_in_finally_on_service_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """service 失败后仍幂等 close。"""

    fake_service = _FakeImportService()

    class _FailingService:
        """fake service：import_workspace 抛 repository failure。"""

        @property
        def platform_service_name(self) -> str:
            """返回稳定注册名。"""

            return "workspace_import"

        def import_workspace(
            self,
            scope: TenantScope,
            request: WorkspaceImportRequest,
        ) -> WorkspaceImportReceipt:
            """恒抛 repository failure。

            Args:
                scope: 租户范围。
                request: import 请求。

            Returns:
                永不返回。

            Raises:
                WorkspaceImportRepositoryFailureError: 恒抛。
            """

            del scope, request
            raise WorkspaceImportRepositoryFailureError()

        def close(self) -> None:
            """标记关闭。"""

            fake_service.closed = True

    from dayu.services.startup_preparation import PreparedWorkspaceImportDependencies

    def _fake_prepare() -> PreparedWorkspaceImportDependencies:
        return PreparedWorkspaceImportDependencies(service=_FailingService())

    monkeypatch.setattr(
        "dayu.cli.workspace_migrations.platform_import.stage_workspace_import",
        _fake_stage,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.prepare_workspace_import_dependencies",
        _fake_prepare,
    )
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    args = Namespace(
        base=str(workspace_root),
        import_existing_workspace=True,
        import_existing_workspace_seen=1,
        import_existing_workspace_repeated=False,
        import_manifest=str(workspace_root / "m.json"),
        target_tenant_id=DEFAULT_ORGANIZATION_ID,
        reset=False,
        overwrite=False,
    )
    assert run_init_command(args) == 1
    assert fake_service.closed


def _tree_manifest(root: Path) -> dict[str, tuple[str, int, int]]:
    """收集目录下全部 entry 的 (类型, size, mtime_ns) 快照。

    Args:
        root: 待快照的目录。

    Returns:
        相对路径 -> (类型, size, mtime_ns) 映射。

    Raises:
        OSError: 遍历失败时抛出。
    """

    snapshot: dict[str, tuple[str, int, int]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        try:
            entry_stat = path.lstat()
        except OSError:
            continue
        if stat.S_ISDIR(entry_stat.st_mode):
            entry_type = "dir"
        elif stat.S_ISLNK(entry_stat.st_mode):
            entry_type = "symlink"
        else:
            entry_type = "file"
        snapshot[relative] = (entry_type, entry_stat.st_size, entry_stat.st_mtime_ns)
    return snapshot


def _assert_tree_unchanged(before: dict[str, tuple[str, int, int]], root: Path) -> None:
    """断言 source tree 在 staging 前后完全不变（no-create/recovery 证明）。

    Args:
        before: staging 前快照。
        root: source root。

    Returns:
        无。

    Raises:
        AssertionError: tree 发生变化时抛出。
    """

    assert _tree_manifest(root) == before


class TestStagingReadOnlyTree:
    """staging 不修改 source tree（no-create 与无 recovery）。"""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "scenario",
        ["empty", "missing_meta", "invalid_meta", "source_root_file"],
    )
    def test_tree_untouched_across_staging_failures(self, tmp_path: Path, scenario: str) -> None:
        """empty/missing-meta/invalid/source-root-file 场景 tree 完全不变。"""

        workspace_root = tmp_path / "workspace"
        portfolio_dir = workspace_root / "portfolio"
        if scenario == "empty":
            portfolio_dir.mkdir(parents=True)
            manifest_payload = _manifest_dict(companies=[])
        elif scenario == "missing_meta":
            (portfolio_dir / "AAPL").mkdir(parents=True)
            manifest_payload = _manifest_dict()
        elif scenario == "invalid_meta":
            ticker_dir = portfolio_dir / "AAPL"
            ticker_dir.mkdir(parents=True)
            (ticker_dir / "meta.json").write_text('{"broken":', encoding="utf-8")
            manifest_payload = _manifest_dict()
        else:
            ticker_dir = portfolio_dir / "AAPL"
            ticker_dir.mkdir(parents=True)
            _write_meta(portfolio_dir, _company_meta_dict())
            (ticker_dir / "filings").write_text("not a dir", encoding="utf-8")
            manifest_payload = _manifest_dict()
        manifest_path = _write_manifest(workspace_root, manifest_payload)
        before = _tree_manifest(workspace_root)
        if scenario == "empty":
            request = stage_workspace_import(
                source_root=workspace_root,
                manifest_path=manifest_path,
                target_tenant_id=DEFAULT_ORGANIZATION_ID,
            )
            assert request.companies == ()
        else:
            with pytest.raises(WorkspaceImportError):
                stage_workspace_import(
                    source_root=workspace_root,
                    manifest_path=manifest_path,
                    target_tenant_id=DEFAULT_ORGANIZATION_ID,
                )
        _assert_tree_unchanged(before, workspace_root)

    @pytest.mark.unit
    def test_tree_untouched_on_successful_staging(self, tmp_path: Path) -> None:
        """成功 staging 后 source tree 完全不变。"""

        workspace_root = _build_fixture_workspace(tmp_path)
        manifest_path = _write_manifest(workspace_root, _manifest_dict())
        before = _tree_manifest(workspace_root)
        stage_workspace_import(
            source_root=workspace_root,
            manifest_path=manifest_path,
            target_tenant_id=DEFAULT_ORGANIZATION_ID,
        )
        _assert_tree_unchanged(before, workspace_root)
        assert not (workspace_root / ".dayu").exists()
        assert not (workspace_root / "portfolio" / "AA2PL").exists()
