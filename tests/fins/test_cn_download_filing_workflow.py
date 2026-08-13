"""CN/HK single-filing download stream contract tests."""

from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator
from typing import get_origin, get_type_hints

import pytest

from dayu.fins.pipelines.cn_download_filing_workflow import (
    run_cn_download_single_filing_stream,
)

pytestmark = pytest.mark.unit


def test_cn_single_filing_download_is_a_native_closable_async_generator_leaf() -> None:
    """The leaf exposes ``aclose`` statically without pretending to own an inner stream."""

    assert inspect.isasyncgenfunction(run_cn_download_single_filing_stream)
    return_type = get_type_hints(run_cn_download_single_filing_stream)["return"]
    assert get_origin(return_type) is AsyncGenerator
    source = inspect.getsource(run_cn_download_single_filing_stream)
    assert ".aclose(" not in source
