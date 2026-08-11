"""投资域骨架的架构守护与值对象严格测试。

本文件守住 Slice 0.1 的两类边界：

1. 架构守护（AST 扫描 ``dayu.investment`` 生产代码）：不得导入任何
   上层包或 ORM/Web 框架；不得出现 ``Any`` / ``object`` / ``cast`` /
   ``type: ignore`` / ``getattr`` / ``hasattr`` 逃逸；所有模块、类、
   函数都必须携带含中文的 docstring。
2. 值对象严格反例：五个标识为 frozen slots 运行时值对象，直接构造与
   ``make_*`` 工厂执行同样的严格校验；``TenantScope`` 禁止公开直接
   构造；金额、数量与 UTC 时间工具对非法输入一律 fail closed
   （``TypeError`` / ``ValueError``）。

本测试文件自身同样遵守根 ``AGENTS.md`` 约束：不使用 ``object`` /
``Any`` / ``cast`` / ``type: ignore`` / ``getattr`` / ``hasattr``。
"""

from __future__ import annotations

import ast
import symtable
from dataclasses import replace
from datetime import datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from pathlib import Path
from typing import Callable

import pytest

import dayu.investment as investment_pkg
import dayu.investment.domain as domain_pkg
from dayu.investment import (
    AccountId,
    CompanyId,
    Money,
    PortfolioId,
    Principal,
    Quantity,
    SecurityId,
    TenantId,
    TenantScope,
    make_account_id,
    make_company_id,
    make_portfolio_id,
    make_security_id,
    make_tenant_id,
    parse_utc,
    to_utc_iso,
    utc_now,
)
from dayu.investment.domain import (
    AccountId as DomainAccountId,
)
from dayu.investment.domain import (
    Money as DomainMoney,
)
from dayu.investment.domain import (
    Quantity as DomainQuantity,
)
from dayu.investment.domain import (
    TenantScope as DomainTenantScope,
)
from dayu.investment.domain.identifiers import _TENANT_SCOPE_TOKEN, _TenantScopeToken

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INVESTMENT_SRC = _REPO_ROOT / "dayu" / "investment"
_INTEGRATION_TESTS_SRC = _REPO_ROOT / "tests" / "integration" / "investment"

_IdentifierFactory = Callable[[str], TenantId | CompanyId | SecurityId | PortfolioId | AccountId]

# 完整 forbidden set：pure 层（根 __init__/domain/config/composition）禁止
# 全部上层与 ORM/驱动依赖。pure 集合精确为这些相对路径。
_PURE_FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "sqlalchemy",
    "psycopg",
    "alembic",
    "fastapi",
    "pydantic",
    "dayu.fins",
    "dayu.host",
    "dayu.engine",
    "dayu.services",
    "dayu.web",
    "dayu.wechat",
    "dayu.cli",
    "dayu.startup",
    "dayu.contracts",
    "dayu.execution",
)

# infra 集合（storage/**）从完整 forbidden set 移除 ORM/驱动依赖，
# 其它上层依赖与 escape/docstring guards 不变。
_INFRA_FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = tuple(
    prefix
    for prefix in _PURE_FORBIDDEN_IMPORT_PREFIXES
    if prefix not in {"sqlalchemy", "psycopg", "alembic"}
)

# pure 集合精确相对路径；未知新增路径默认按 pure 规则拒绝。
_PURE_RELATIVE_PATHS: tuple[str, ...] = (
    "__init__.py",
    "domain/",
    "config.py",
    "composition.py",
)

# infra 集合精确相对路径前缀。
_INFRA_RELATIVE_PREFIX = "storage/"

_ESCAPE_CALL_NAMES: frozenset[str] = frozenset({"cast", "getattr", "hasattr"})
_ESCAPE_NAME_IDS: frozenset[str] = frozenset({"Any", "object"})

_CJK_RANGE: tuple[int, int] = (0x4E00, 0x9FFF)


def _iter_investment_files() -> list[Path]:
    """收集 investment 包下全部 Python 文件。

    Args:
        无。

    Returns:
        按文件名排序的 Python 文件路径列表。

    Raises:
        无。
    """

    return sorted(path for path in _INVESTMENT_SRC.rglob("*.py") if path.is_file())


def _iter_integration_test_files() -> list[Path]:
    """收集投资平台 integration 测试目录下全部 Python 文件。

    Args:
        无。

    Returns:
        按文件名排序的 Python 文件路径列表。

    Raises:
        无。
    """

    if not _INTEGRATION_TESTS_SRC.is_dir():
        return []
    return sorted(path for path in _INTEGRATION_TESTS_SRC.rglob("*.py") if path.is_file())


def _relative_to_investment(file_path: Path) -> str:
    """返回文件相对于 investment 包的 POSIX 路径。

    Args:
        file_path: investment 包内的 Python 文件路径。

    Returns:
        以 ``dayu/investment`` 为根的相对路径（POSIX 分隔符）。

    Raises:
        ValueError: 文件不在 investment 包内时抛出。
    """

    try:
        return file_path.resolve().relative_to(_INVESTMENT_SRC.resolve()).as_posix()
    except ValueError:
        raise ValueError(f"{file_path} 不在 dayu.investment 包内") from None


def _forbidden_prefixes_for(file_path: Path) -> tuple[str, ...] | None:
    """按相对路径返回文件适用的 forbidden import 集合。

    pure 集合精确为根 ``__init__.py``、``domain/**``、``config.py``、
    ``composition.py``；infra 集合精确为 ``storage/**``；未知新增路径
    返回 ``None`` 表示按 pure 规则拒绝。

    Args:
        file_path: investment 包内的 Python 文件路径。

    Returns:
        文件适用的 forbidden import 前缀元组；路径不属于任何已声明
        集合时返回 ``None``。

    Raises:
        无。
    """

    relative = _relative_to_investment(file_path)
    if relative == "__init__.py" or relative.startswith("domain/") or relative in {
        "config.py",
        "composition.py",
    }:
        return _PURE_FORBIDDEN_IMPORT_PREFIXES
    if relative.startswith(_INFRA_RELATIVE_PREFIX):
        return _INFRA_FORBIDDEN_IMPORT_PREFIXES
    return None


def _read_source(file_path: Path) -> str:
    """读取 Python 源文件文本。

    Args:
        file_path: 目标 Python 文件路径。

    Returns:
        文件 UTF-8 文本。

    Raises:
        OSError: 文件不可读时抛出。
    """

    return file_path.read_text(encoding="utf-8")


def _collect_forbidden_imports(file_path: Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    """收集文件中违反依赖方向约束的导入语句。

    Args:
        file_path: 目标 Python 文件路径。
        forbidden_prefixes: 该文件适用的 forbidden import 前缀集合。

    Returns:
        违规的模块名列表（未违规时为空）。

    Raises:
        无。
    """

    tree = ast.parse(_read_source(file_path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            candidates = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            candidates = [node.module or ""]
        else:
            continue
        for module_name in candidates:
            if any(
                module_name == prefix or module_name.startswith(f"{prefix}.")
                for prefix in forbidden_prefixes
            ):
                hits.append(module_name)
    return hits


def _collect_escape_violations(file_path: Path) -> list[str]:
    """收集文件中 Any/object/cast/type-ignore/getattr/hasattr 逃逸。

    除裸 ``Name`` 外还解析：

    - ``import module as alias`` / ``from module import name as alias``
      的本地别名，把别名使用映射回真名；
    - ``Attribute`` 访问（如 ``typing.Any``、``t.cast``、模块别名的
      属性）；
    - 带别名或属性的调用（如 ``t.cast(...)``、
      ``from builtins import getattr as read_attr; read_attr(...)``）。

    Args:
        file_path: 目标 Python 文件路径。

    Returns:
        违规描述列表（未违规时为空）。

    Raises:
        无。
    """

    source = _read_source(file_path)
    return _collect_escape_violations_from_source(source)


def _collect_escape_violations_from_source(source: str) -> list[str]:
    """对给定源码字符串执行 escape 扫描（自测反例用）。

    Args:
        source: 待扫描的 Python 源码文本。

    Returns:
        违规描述列表（未违规时为空）。

    Raises:
        无。
    """

    tree = ast.parse(source)
    hits: list[str] = []

    alias_targets = _collect_escape_aliases(tree)
    alias_names = set(alias_targets)
    allowed_object_nodes = _collect_allowed_object_setattr_nodes(tree, source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in _ESCAPE_NAME_IDS:
                if id(node) in allowed_object_nodes:
                    continue
                hits.append(f"禁止使用 {node.id}")
            if node.id in alias_names and alias_targets[node.id] in _ESCAPE_NAME_IDS:
                hits.append(f"禁止使用别名 {node.id}（来自 {alias_targets[node.id]}）")
        if isinstance(node, ast.Attribute):
            if node.attr in _ESCAPE_NAME_IDS:
                hits.append(f"禁止属性访问 {node.attr}")
            if node.attr in _ESCAPE_CALL_NAMES:
                hits.append(f"禁止属性访问并调用 {node.attr}()")
        if isinstance(node, ast.Call):
            func_name = _resolve_call_target(node.func, alias_targets)
            if func_name in _ESCAPE_CALL_NAMES:
                hits.append(f"禁止调用 {func_name}()")

    for line_number, line in enumerate(source.splitlines(), start=1):
        if "# type: ignore" in line:
            hits.append(f"第 {line_number} 行禁止 type: ignore")
    return hits


def _collect_frozen_slots_fields_by_class(
    tree: ast.Module,
    standard_dataclass_names: frozenset[str],
    parents: dict[int, ast.AST],
) -> dict[int, frozenset[str]]:
    """收集每个 frozen+slots dataclass 节点 id 到其本类 AnnAssign 字段名。

    只接受**直接**挂在模块顶层（parent 为 ``ast.Module``）的类，函数/
    类体等嵌套作用域内的同形类不进入映射（局部同名伪 decorator 无法
    借此绕过）。

    Args:
        tree: 模块 AST。
        standard_dataclass_names: 模块级可信的标准 dataclass 名字集合。
        parents: 节点 id 到父节点的映射。

    Returns:
        类节点 id 到该类的直接 AnnAssign 字段名集合的映射；非
        frozen+slots dataclass 不进入映射。
    """

    fields_by_class: dict[int, frozenset[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not isinstance(parents.get(id(node)), ast.Module):
            continue
        if not _is_frozen_slots_dataclass(node, standard_dataclass_names):
            continue
        fields: set[str] = set()
        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                fields.add(child.target.id)
        fields_by_class[id(node)] = frozenset(fields)
    return fields_by_class


def _build_parent_map(tree: ast.Module) -> dict[int, ast.AST]:
    """构建 AST 节点 id 到其父节点的映射。

    Args:
        tree: 模块 AST。

    Returns:
        节点 id 到父节点对象的映射（根节点无父，不入映射）。
    """

    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _direct_post_init_owner(
    call: ast.Call,
    parents: dict[int, ast.AST],
    standard_dataclass_names: frozenset[str],
) -> ast.ClassDef | None:
    """沿父链找到调用直接所在的 frozen+slots class 的 __post_init__。

    只接受调用**直接**位于某 frozen+slots dataclass 的
    ``__post_init__(self)`` 方法体内（方法定义直接挂在该类 body 上、
    且调用不经过任何嵌套函数、嵌套类、lambda 或 comprehension 等
    嵌套执行作用域）；该类必须是**直接**挂在模块顶层的 ClassDef
    （嵌套作用域内同形类一律拒绝）。否则返回 ``None``。

    Args:
        call: ``object.__setattr__`` 调用节点。
        parents: 节点 id 到父节点的映射。
        standard_dataclass_names: 模块级可信的标准 dataclass 名字集合。

    Returns:
        调用直接位于其 ``__post_init__(self)`` 方法体内的
        frozen+slots dataclass；不满足时返回 ``None``。
    """

    node: ast.AST = call
    while id(node) in parents:
        parent = parents[id(node)]
        if isinstance(parent, ast.FunctionDef):
            if parent.name != "__post_init__":
                return None
            if not _is_sole_self_param(parent.args):
                return None
            owner = parents.get(id(parent))
            if not isinstance(owner, ast.ClassDef):
                return None
            if not isinstance(parents.get(id(owner)), ast.Module):
                return None
            if not _is_frozen_slots_dataclass(owner, standard_dataclass_names):
                return None
            if parent not in owner.body:
                return None
            return owner
        if isinstance(
            parent,
            (
                ast.ClassDef,
                ast.Module,
                ast.Lambda,
                ast.ListComp,
                ast.SetComp,
                ast.DictComp,
                ast.GeneratorExp,
            ),
        ):
            return None
        node = parent
    return None


def _is_sole_self_param(args: ast.arguments) -> bool:
    """判断函数参数是否为唯一的精确 ``self`` 位置参数。

    只接受恰好一个名为 ``self`` 的位置参数，且不携带任何 posonly /
    vararg / kwonly / kwargs，杜绝 `def __post_init__(owner)`、
    `def __post_init__(self, *args)` 等形态。

    Args:
        args: 函数参数 AST。

    Returns:
        参数形态严格为 `def f(self)` 时返回 True。

    Raises:
        无。
    """

    return (
        len(args.posonlyargs) == 0
        and len(args.args) == 1
        and args.args[0].arg == "self"
        and args.vararg is None
        and len(args.kwonlyargs) == 0
        and args.kwarg is None
    )


def _collect_standard_dataclass_names(source: str) -> frozenset[str]:
    """收集模块级可信的标准 dataclass 名字集合（symtable 绑定真源）。

    绑定判定以 Python 标准库 symtable 为真源，不再手工枚举赋值形态。
    候选名必须同时满足：

    1. AST 层面：是**唯一**的模块级 ``from dataclasses import dataclass
       [as alias]`` 导入绑定，模块作用域内无其它同名 import（
       ``import fake as dataclass`` / ``from fake import dataclass`` 等
       一律视为模糊绑定）导致歧义；
    2. symtable 层面：``symtable.symtable(source, ..., "exec")`` 的
       ``lookup(alias)`` 必须 ``is_imported()`` 为 True 且
       ``is_assigned()`` 为 False——assignment/for/with/except/walrus/
       match capture/del/function/class 等一切模块级写绑定统一 fail
       closed；嵌套函数/类内部的作用域由 symtable 天然隔离。

    Args:
        source: 待扫描的 Python 源码文本。

    Returns:
        可被安全认定为标准库 dataclass 的模块级名字集合。

    Raises:
        SyntaxError: source 无法解析时由 ``ast.parse`` / ``symtable``
            抛出。
    """

    tree = ast.parse(source)
    module_table = symtable.symtable(source, "<module>", "exec")

    standard_counts: dict[str, int] = {}
    nonstandard: set[str] = set()
    for statement in tree.body:
        for name, is_standard in _module_scope_import_bindings(statement):
            if is_standard:
                standard_counts[name] = standard_counts.get(name, 0) + 1
            else:
                nonstandard.add(name)

    trusted: set[str] = set()
    for name, count in standard_counts.items():
        if name in nonstandard or count != 1:
            continue
        symbol = module_table.lookup(name)
        if symbol.is_imported() and not symbol.is_assigned():
            trusted.add(name)
    return frozenset(trusted)


def _module_scope_import_bindings(statement: ast.stmt) -> list[tuple[str, bool]]:
    """收集语句在模块作用域内执行时发生的 import 绑定。

    遍历顶层语句子树但不深入函数/类/lambda 等新作用域；返回
    （绑定名, 是否为标准 dataclasses 导入）对。标准 dataclasses 导入
    精确为 ``from dataclasses import dataclass``（含 ``as`` 别名）；
    其余 import 一律标记为非标准。

    Args:
        statement: 模块顶层语句。

    Returns:
        语句在模块作用域内绑定名字与来源标记的列表。

    Raises:
        无。
    """

    bindings: list[tuple[str, bool]] = []
    stack: list[ast.AST] = [statement]
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings.append((alias.asname or alias.name.split(".")[0], False))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                is_standard = node.module == "dataclasses" and alias.name == "dataclass"
                bindings.append((alias.asname or alias.name, is_standard))
        stack.extend(ast.iter_child_nodes(node))
    return bindings


def _is_frozen_slots_dataclass(node: ast.ClassDef, standard_dataclass_names: frozenset[str]) -> bool:
    """判断类是否由标准库 dataclass 直接装饰为 frozen=True 且 slots=True。

    只接受模块级 ``from dataclasses import dataclass`` 解析得到、且未被
    模块级重绑定的名字，以**直接** ``ast.Name`` 作为 decorator callee；
    ``fake.dataclass`` 等 attribute callee、本地/模块同名伪 decorator、
    无标准导入一律视为不满足。``frozen`` 与 ``slots`` 必须出现在
    **同一个** decorator call 中且值均为 ``ast.Constant(True)``，不得
    跨多个 decorator 聚合；重复关键字或模糊绑定一律 fail closed。

    Args:
        node: 类定义 AST。
        standard_dataclass_names: 模块级可信的标准 dataclass 名字集合。

    Returns:
        是标准 frozen+slots dataclass 时返回 True。

    Raises:
        无。
    """

    dataclass_calls: list[ast.Call] = []
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if not isinstance(func, ast.Name):
            continue
        if func.id not in standard_dataclass_names:
            continue
        dataclass_calls.append(decorator)
    if len(dataclass_calls) != 1:
        return False
    call = dataclass_calls[0]
    if len(call.args) != 0:
        return False
    seen: dict[str, bool] = {}
    for keyword in call.keywords:
        if keyword.arg in {"frozen", "slots"}:
            if keyword.arg in seen:
                return False
            seen[keyword.arg] = isinstance(keyword.value, ast.Constant) and keyword.value.value is True
    return seen.get("frozen") is True and seen.get("slots") is True


def _collect_allowed_object_setattr_nodes(tree: ast.Module, source: str) -> set[int]:
    """收集合法 frozen+slots 赋值上下文中的 ``object`` Name 节点 id。

    精确豁免（S12-CTRL-08 + TERRA-003）：调用目标为
    ``object.__setattr__``、恰好三个位置参数零 keyword、第一参数为
    ``self``、第二参数为本类已声明字段名字符串字面量，且调用直接位于
    当前 frozen=True+slots=True dataclass 的 ``__post_init__(self)``
    方法体内（沿 AST 父链绑定，不经任何嵌套函数/嵌套类、该类直接挂
    在模块顶层）。dataclass 可信判定以 ``source`` 经 symtable 真源
    完成（见 ``_collect_standard_dataclass_names``）。

    Args:
        tree: 模块 AST（与调用方扫描所用的同一 tree，保证节点 id
            一致）。
        source: 待扫描的 Python 源码文本（供 symtable 绑定真源）。

    Returns:
        应豁免的 ``object`` Name 节点 id 集合。

    Raises:
        SyntaxError: source 无法解析时由 ``symtable`` 抛出。
    """

    parents = _build_parent_map(tree)
    standard_dataclass_names = _collect_standard_dataclass_names(source)
    fields_by_class = _collect_frozen_slots_fields_by_class(
        tree,
        standard_dataclass_names,
        parents,
    )
    allowed: set[int] = set()
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        if not _is_object_setattr_call(call):
            continue
        if not _has_exact_three_positional_args_no_keywords(call):
            continue
        if not isinstance(call.args[0], ast.Name) or call.args[0].id != "self":
            continue
        field_arg = call.args[1]
        if not isinstance(field_arg, ast.Constant) or not isinstance(field_arg.value, str):
            continue
        owner = _direct_post_init_owner(call, parents, standard_dataclass_names)
        if owner is None:
            continue
        if field_arg.value not in fields_by_class[id(owner)]:
            continue
        func_value = call.func
        if not isinstance(func_value, ast.Attribute):
            continue
        base = func_value.value
        if isinstance(base, ast.Name) and base.id == "object":
            allowed.add(id(base))
    return allowed


def _is_object_setattr_call(call: ast.Call) -> bool:
    """判断调用目标是否为 ``object.__setattr__``。

    Args:
        call: 调用节点。

    Returns:
        是 ``object.__setattr__`` 调用时返回 True。

    Raises:
        无。
    """

    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr != "__setattr__":
        return False
    return isinstance(func.value, ast.Name) and func.value.id == "object"


def _has_exact_three_positional_args_no_keywords(call: ast.Call) -> bool:
    """判断调用是否恰好三个位置参数且零 keyword。

    Args:
        call: 调用节点。

    Returns:
        恰好三个位置参数且零 keyword 时返回 True。

    Raises:
        无。
    """

    return len(call.args) == 3 and len(call.keywords) == 0


def _collect_escape_aliases(tree: ast.Module) -> dict[str, str]:
    """收集模块/导入别名到目标名的映射（仅关心逃逸目标）。

    Args:
        tree: 模块 AST。

    Returns:
        本地别名到目标名的映射；只包含映射到
        ``Any/object/cast/getattr/hasattr`` 的别名。

    Raises:
        无。
    """

    aliases: dict[str, str] = {}
    escape_targets = _ESCAPE_NAME_IDS | _ESCAPE_CALL_NAMES
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name.split(".")[-1]
                if alias.asname and target in escape_targets:
                    aliases[alias.asname] = target
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname and alias.name in escape_targets:
                    aliases[alias.asname] = alias.name
    return aliases


def _resolve_call_target(func: ast.expr, alias_targets: dict[str, str]) -> str | None:
    """解析调用目标为逃逸函数名（含别名与属性链）。

    Args:
        func: 调用目标表达式。
        alias_targets: 别名到目标名映射。

    Returns:
        若调用目标是逃逸函数（``cast/getattr/hasattr``）则返回函数名，
        否则返回 ``None``。

    Raises:
        无。
    """

    if isinstance(func, ast.Name):
        if func.id in _ESCAPE_CALL_NAMES:
            return func.id
        if func.id in alias_targets and alias_targets[func.id] in _ESCAPE_CALL_NAMES:
            return alias_targets[func.id]
        return None
    if isinstance(func, ast.Attribute):
        if func.attr in _ESCAPE_CALL_NAMES:
            return func.attr
        if isinstance(func.value, ast.Name) and func.value.id in alias_targets:
            if alias_targets[func.value.id] in _ESCAPE_CALL_NAMES:
                return alias_targets[func.value.id]
    return None


def _contains_cjk(text: str) -> bool:
    """判断文本是否包含至少一个中文字符。

    Args:
        text: 待判断的文本。

    Returns:
        包含中文时返回 True，否则返回 False。

    Raises:
        无。
    """

    return any(_CJK_RANGE[0] <= ord(char) <= _CJK_RANGE[1] for char in text)


def _collect_docstring_violations(file_path: Path) -> list[str]:
    """收集文件中缺少中文 docstring 的模块/类/函数节点。

    Args:
        file_path: 目标 Python 文件路径。

    Returns:
        违规节点定位列表（未违规时为空）。

    Raises:
        无。
    """

    tree = ast.parse(_read_source(file_path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Module):
            node_name = "<module>"
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            node_name = node.name
        else:
            continue
        docstring = ast.get_docstring(node)
        if docstring is None or not _contains_cjk(docstring):
            hits.append(f"{type(node).__name__} {node_name} 缺少中文 docstring")
    return hits


class _NoOffsetTimezone(tzinfo):
    """测试用 tzinfo：``utcoffset`` 恒返回 ``None``。

    用于构造“语义上 naive”的时刻：``tzinfo`` 非空但 ``utcoffset()``
    为空，验证 UTC 工具不会退化为本机时区换算。
    """

    def utcoffset(self, moment: datetime | None) -> timedelta | None:
        """恒返回 None，表示无 UTC 偏移。

        Args:
            moment: 待求偏移的时刻（本实现不使用）。

        Returns:
            恒为 ``None``。

        Raises:
            无。
        """

        return None

    def dst(self, moment: datetime | None) -> timedelta | None:
        """恒返回 None，表示无夏令时偏移。

        Args:
            moment: 待求夏令时偏移的时刻（本实现不使用）。

        Returns:
            恒为 ``None``。

        Raises:
            无。
        """

        return None

    def tzname(self, moment: datetime | None) -> str | None:
        """返回固定时区名。

        Args:
            moment: 待求时区名的时刻（本实现不使用）。

        Returns:
            固定字符串 ``"NO_OFFSET"``。

        Raises:
            无。
        """

        return "NO_OFFSET"


class TestArchitectureBoundaries:
    """投资包依赖方向与逃逸模式守护。"""

    @pytest.mark.unit
    def test_investment_never_imports_forbidden_modules(self) -> None:
        """pure 层禁止上层包与 ORM，storage 层仅允许 SQL 依赖。

        ``dayu.investment`` 以相对路径分组：pure 集合（根
        ``__init__.py`` / ``domain/**`` / ``config.py`` /
        ``composition.py``）继续使用完整 forbidden set（含
        SQLAlchemy/psycopg/Alembic）；infra 集合（``storage/**``）
        只移除 ORM/驱动依赖，其它上层依赖仍禁止；未知新增路径默认
        按 pure 规则拒绝。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        violations: list[str] = []
        for file_path in _iter_investment_files():
            prefixes = _forbidden_prefixes_for(file_path)
            if prefixes is None:
                violations.append(f"{_relative_to_investment(file_path)} 未声明 owner 集合，按 pure 规则拒绝")
                continue
            for module_name in _collect_forbidden_imports(file_path, prefixes):
                violations.append(f"{_relative_to_investment(file_path)} 导入受限模块 {module_name}")
        assert violations == []

    @pytest.mark.unit
    def test_investment_never_uses_escape_patterns(self) -> None:
        """投资包不得出现 Any/object/cast/type-ignore/getattr/hasattr 逃逸。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        violations: list[str] = []
        for file_path in _iter_investment_files():
            for hit in _collect_escape_violations(file_path):
                violations.append(f"{file_path.name}: {hit}")
        assert violations == []

    @pytest.mark.unit
    def test_investment_modules_carry_chinese_docstrings(self) -> None:
        """投资包所有模块/类/函数必须携带中文 docstring。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        violations: list[str] = []
        for file_path in _iter_investment_files():
            for hit in _collect_docstring_violations(file_path):
                violations.append(f"{file_path.name}: {hit}")
        assert violations == []

    @pytest.mark.unit
    def test_integration_tests_never_use_escape_patterns(self) -> None:
        """投资 integration 测试不得出现宽类型/逃逸模式。

        TERRA-004：把 ``tests/integration/investment/**`` 纳入与
        production 相同的 ``Any`` / ``object`` / ``cast`` /
        ``type: ignore`` / ``getattr`` / ``hasattr`` 守护，避免 catalog
        断言静默宽化类型。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        violations: list[str] = []
        for file_path in _iter_integration_test_files():
            for hit in _collect_escape_violations(file_path):
                violations.append(f"{file_path.name}: {hit}")
        assert violations == []

    @pytest.mark.unit
    def test_integration_tests_carry_chinese_docstrings(self) -> None:
        """投资 integration 测试所有模块/类/函数必须携带中文 docstring。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        violations: list[str] = []
        for file_path in _iter_integration_test_files():
            for hit in _collect_docstring_violations(file_path):
                violations.append(f"{file_path.name}: {hit}")
        assert violations == []

    @pytest.mark.unit
    def test_workspace_import_domain_never_imports_upper_layers(self) -> None:
        """workspace import 纯域只依赖标准库与 dayu.investment.domain。

        S15-CTRL-06：``dayu.investment.domain.workspace_import`` 禁止
        import ``dayu.fins.*``、CLI、Service、ORM 与 Web/Host/Agent；
        该收窄只发生在 CLI staging adapter。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        module_path = _INVESTMENT_SRC / "domain" / "workspace_import.py"
        violations = _collect_forbidden_imports(
            module_path,
            _PURE_FORBIDDEN_IMPORT_PREFIXES,
        )
        assert violations == []
        for hit in _collect_escape_violations(module_path):
            violations.append(f"{module_path.name}: {hit}")
        assert violations == []

    @pytest.mark.unit
    def test_escape_guard_catches_qualified_names_and_aliases(self) -> None:
        """escape guard 必须拦截限定名与别名逃逸（自测反例）。

        在临时文件中分别注入：``typing.Any`` / ``typing.cast`` /
        ``import typing as t; t.cast`` / ``from typing import cast as c;
        c(...)`` / ``from builtins import getattr as read_attr;
        read_attr(...)`` / ``type: ignore[misc]``，断言 guard 全部命中；
        同时注入合法用法（``typing.Text``、别名指向非逃逸目标）断言不
        误报。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        cases = {
            "x: typing.Any = 1": "禁止属性访问 Any",
            "y = typing.cast(str, x)": "禁止属性访问并调用 cast()",
            "import typing as t\nz = t.cast(str, x)": "禁止调用 cast()",
            "from typing import cast as c\nz = c(str, x)": "禁止调用 cast()",
            "from builtins import getattr as read_attr\nread_attr(x, 'a')": "禁止调用 getattr()",
            "from typing import Any as T\nx: T = 1": "禁止使用别名 T",
            "x: object = 1": "禁止使用 object",
            "import hasattr as h\nh(x, 'a')": "禁止调用 hasattr()",
            "x = 1  # type: ignore[misc]": "禁止 type: ignore",
        }
        for source, expected_hit in cases.items():
            violations = _collect_escape_violations_from_source(source)
            assert any(expected_hit in hit for hit in violations), (source, violations)

        clean_cases = [
            "import typing\nx: typing.Text = 'a'",
            "import os as o\npath = o.path.join('a', 'b')",
            "from typing import Text\nx: Text = 'a'",
        ]
        for source in clean_cases:
            violations = _collect_escape_violations_from_source(source)
            assert violations == [], (source, violations)

    @pytest.mark.unit
    def test_escape_guard_resolves_attribute_chain_and_module_alias(self) -> None:
        """escape guard 解析属性链与模块别名（自测反例）。

        覆盖 ``typing.cast`` 经模块别名（``import typing as t``）、
        以及 ``from builtins import getattr`` 别名化后调用等写法。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        source = (
            "import typing as t\n"
            "from builtins import getattr as g\n"
            "import hasattr as h\n"
            "a = t.cast(str, x)\n"
            "b = g(x, 'k')\n"
            "c = h(x, 'k')\n"
        )
        violations = _collect_escape_violations_from_source(source)
        assert "禁止调用 cast()" in violations
        assert "禁止调用 getattr()" in violations
        assert "禁止调用 hasattr()" in violations

    @pytest.mark.unit
    def test_frozen_slots_object_setattr_is_allowed(self) -> None:
        """frozen+slots dataclass __post_init__ 内精确 object.__setattr__ 豁免。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        source = (
            "from dataclasses import dataclass\n"
            "@dataclass(frozen=True, slots=True)\n"
            "class Foo:\n"
            "    value: str\n"
            "    def __post_init__(self) -> None:\n"
            "        object.__setattr__(self, 'value', 'x')\n"
        )
        violations = _collect_escape_violations_from_source(source)
        assert "禁止使用 object" not in violations

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "source",
        [
            # 裸 object 类型标注仍拒绝。
            "x: object = 1",
            # object 作为注解。
            "def f() -> object:\n    return None",
            # object.__new__ 调用（非 __setattr__）。
            "x = object.__new__(cls)",
            # 其它 receiver（非 self）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(other, 'value', 'x')\n"
            ),
            # 未知字段名。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'unknown', 'x')\n"
            ),
            # 方法体之外（类体顶层）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    x = object.__setattr__(self, 'value', 'y')\n"
            ),
            # 非 dataclass。
            (
                "class Foo:\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # non-frozen 或 non-slots dataclass。
            (
                "from dataclasses import dataclass\n"
                "@dataclass\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # 存储引用（非调用上下文）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        f = object.__setattr__\n"
            ),
            # keyword 多余。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x', __no_such=True)\n"
            ),
            # 参数个数不对（2 个）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value')\n"
            ),
            # 字段名为变量而非字面量。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, name, 'x')\n"
            ),
            # 嵌套函数内的调用（TERRA-003）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        def helper() -> None:\n"
                "            object.__setattr__(self, 'value', 'x')\n"
                "        helper()\n"
            ),
            # 嵌套类方法内的调用（TERRA-003）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        class Inner:\n"
                "            def f(self) -> None:\n"
                "                object.__setattr__(self, 'value', 'x')\n"
            ),
            # 跨类字段名（字段声明在另一个 frozen+slots class）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'other', 'x')\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Bar:\n"
                "    other: str\n"
            ),
            # 非 self 参数（嵌套上下文之外仍拒绝）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self, other: str) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # lambda 内的调用（TERRA-S12-RR-002）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        callback = lambda: object.__setattr__(self, 'value', 'x')\n"
            ),
            # list comprehension 内的调用（TERRA-S12-RR-002）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        _ = [object.__setattr__(self, 'value', 'x') for _ in range(1)]\n"
            ),
            # 参数名非 self（TERRA-S12-RR-002）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(owner) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # posonly 参数（TERRA-S12-RR-002）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self, /) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # vararg 参数（TERRA-S12-RR-002）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self, *args) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # kwonly 参数（TERRA-S12-RR-002）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self, *, extra: str) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # kwargs 参数（TERRA-S12-RR-002）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self, **kwargs) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # frozen=1 / slots=1 真值常量不算精确 True（TERRA-S12-RR-002）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=1, slots=1)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # 模块级同名伪 decorator（无标准导入，TERRA-S12-FRR-001）。
            (
                "def dataclass(cls):\n"
                "    return cls\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # attribute callee fake.dataclass（TERRA-S12-FRR-001）。
            (
                "import fake\n"
                "@fake.dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # frozen/slots 分散在两个标准 dataclass call（TERRA-S12-FRR-001）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True)\n"
                "@dataclass(slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # 标准 import 后模块级重绑定 dataclass（TERRA-S12-FRR-001）。
            (
                "from dataclasses import dataclass\n"
                "def fake_dataclass(cls):\n"
                "    return cls\n"
                "dataclass = fake_dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # 重复 frozen 关键字 fail closed（TERRA-S12-FRR-001）。
            (
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True, frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # 标准 import 后 import-as 重绑定 dataclass（TERRA-S12-FRR-001）。
            (
                "from dataclasses import dataclass\n"
                "import fake as dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # 标准 import 后 from-import 重绑定 dataclass（TERRA-S12-FRR-001）。
            (
                "from dataclasses import dataclass\n"
                "from fake import dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # 函数内局部同名伪 decorator + nested class（TERRA-S12-FRR-001）。
            (
                "from dataclasses import dataclass\n"
                "def helper() -> None:\n"
                "    def dataclass(cls):\n"
                "        return cls\n"
                "    @dataclass(frozen=True, slots=True)\n"
                "    class Foo:\n"
                "        value: str\n"
                "        def __post_init__(self) -> None:\n"
                "            object.__setattr__(self, 'value', 'x')\n"
            ),
            # 模块级 match/case capture 重绑定 dataclass（TERRA-S12-FC-001）。
            (
                "from dataclasses import dataclass\n"
                "match fake:\n"
                "    case dataclass:\n"
                "        pass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
            # del 绑定 dataclass（符号表边界，TERRA-S12-FC-001）。
            (
                "from dataclasses import dataclass\n"
                "del dataclass\n"
                "@dataclass(frozen=True, slots=True)\n"
                "class Foo:\n"
                "    value: str\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'value', 'x')\n"
            ),
        ],
    )
    def test_frozen_slots_object_setattr_negatives(self, source: str) -> None:
        """非精确豁免上下文一律拒绝。

        Args:
            source: 待扫描源码。

        Returns:
            无。

        Raises:
            无。
        """

        violations = _collect_escape_violations_from_source(source)
        assert "禁止使用 object" in violations, source


class TestIdentifiers:
    """强标识与主体/租户范围严格测试。"""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("factory", "raw"),
        [
            (make_tenant_id, "tenant-a"),
            (make_company_id, "company-a"),
            (make_security_id, "security-a"),
            (make_portfolio_id, "portfolio-a"),
            (make_account_id, "account-a"),
        ],
    )
    def test_identifier_factories_accept_valid_values(self, factory: _IdentifierFactory, raw: str) -> None:
        """合法标识构造成功且保留原值。

        Args:
            factory: 五个标识工厂之一。
            raw: 合法标识原始字符串。

        Returns:
            无。

        Raises:
            无。
        """

        assert str(factory(raw)) == raw

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "factory",
        [
            make_tenant_id,
            make_company_id,
            make_security_id,
            make_portfolio_id,
            make_account_id,
        ],
    )
    @pytest.mark.parametrize("raw", ["", "   ", " abc", "abc ", "\tabc"])
    def test_identifier_factories_reject_invalid_values(self, factory: _IdentifierFactory, raw: str) -> None:
        """空/空白/首尾空白标识经工厂构造一律 fail closed。

        Args:
            factory: 五个标识工厂之一。
            raw: 非法标识原始字符串。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            factory(raw)

    @pytest.mark.unit
    @pytest.mark.parametrize("raw", ["", "   ", " abc", "abc ", "\tabc"])
    def test_identifier_direct_construction_rejects_invalid(self, raw: str) -> None:
        """不经工厂直接构造标识同样拒绝非法输入。

        Args:
            raw: 非法标识原始字符串。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            TenantId(raw)

    @pytest.mark.unit
    def test_identifier_value_objects_are_distinct_and_value_semantic(self) -> None:
        """五个标识互不相同的运行时类型，同值相等、跨类型不等。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        tenant = make_tenant_id("t1")
        assert str(tenant) == "t1"
        assert tenant.value == "t1"
        assert TenantId("t1") == make_tenant_id("t1")
        assert TenantId("t1") != TenantId("t2")
        assert TenantId("t1") != CompanyId("t1")
        assert TenantId is not CompanyId
        assert TenantId is not SecurityId
        assert CompanyId is not PortfolioId
        assert PortfolioId is not AccountId

    @pytest.mark.unit
    def test_identifier_factory_and_direct_construction_agree(self) -> None:
        """工厂与直接构造对合法值等价，对非法值同样失败。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        assert make_tenant_id("other-tenant") == TenantId("other-tenant")
        with pytest.raises(ValueError):
            make_tenant_id("  bad  ")
        with pytest.raises(ValueError):
            TenantId("  bad  ")

    @pytest.mark.unit
    def test_principal_derives_tenant_scope(self) -> None:
        """主体可派生与其租户一致的租户范围。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        principal = Principal(tenant_id=TenantId("t-1"), user_id="u-1")
        scope = principal.to_scope()
        assert scope.tenant_id == principal.tenant_id
        assert scope.tenant_id == TenantId("t-1")
        assert str(scope.tenant_id) == "t-1"

    @pytest.mark.unit
    def test_principal_to_scope_preserves_non_default_tenant(self) -> None:
        """非默认租户经主体派生后保留原租户。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        principal = Principal(tenant_id=TenantId("other-tenant"), user_id="u-1")
        scope = principal.to_scope()
        assert scope.tenant_id == TenantId("other-tenant")

    @pytest.mark.unit
    @pytest.mark.parametrize("tenant_id", ["", "  ", " t-1"])
    def test_principal_rejects_invalid_tenant(self, tenant_id: str) -> None:
        """主体携带非法租户标识时 fail closed。

        Args:
            tenant_id: 非法租户标识原始字符串。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            Principal(tenant_id=TenantId(tenant_id), user_id="u-1")

    @pytest.mark.unit
    @pytest.mark.parametrize("user_id", ["", "  ", " u-1"])
    def test_principal_rejects_invalid_user(self, user_id: str) -> None:
        """主体携带非法用户标识时 fail closed。

        Args:
            user_id: 非法用户标识原始字符串。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            Principal(tenant_id=TenantId("t-1"), user_id=user_id)

    @pytest.mark.unit
    def test_principal_rejects_raw_string_tenant(self) -> None:
        """原始字符串租户输入在构造期 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        principal = Principal(tenant_id=TenantId("t-1"), user_id="u-1")
        with pytest.raises(TypeError):
            replace(principal, tenant_id="raw")

    @pytest.mark.unit
    def test_tenant_scope_direct_construction_rejected(self) -> None:
        """有效租户标识也不能公开直接构造租户范围。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(TypeError):
            TenantScope(tenant_id=TenantId("other-tenant"))

    @pytest.mark.unit
    def test_tenant_scope_is_immutable_after_creation(self) -> None:
        """创建后的租户范围禁止任何属性改写。

        租户范围是仓储/RLS 租户边界实施所依赖的不可变契约，创建后
        必须不可变；直接赋值会被静态类型检查拒绝，故用 ``setattr``
        验证运行时 ``__setattr__`` 拒绝行为。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        scope = Principal(tenant_id=TenantId("t-1"), user_id="u-1").to_scope()
        with pytest.raises(AttributeError):
            setattr(scope, "tenant_id", TenantId("other-tenant"))

    @pytest.mark.unit
    def test_tenant_scope_rejects_forged_sentinel(self) -> None:
        """模块内新哨兵实例（非单例）不能绕过受控构造。

        哨兵校验以单例身份（``is``）进行：即使调用方拿到模块私有的
        ``_TenantScopeToken`` 类型并构造新实例，身份不等于模块单例，
        构造仍被拒绝。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        forged_token = _TenantScopeToken()
        with pytest.raises(TypeError):
            TenantScope(tenant_id=TenantId("other-tenant"), _token=forged_token)

    @pytest.mark.unit
    def test_tenant_scope_rejects_raw_string_tenant_even_with_real_sentinel(self) -> None:
        """即使携带模块内真实单例哨兵，原始字符串租户仍被防御性拒绝。

        导入真实 ``_TENANT_SCOPE_TOKEN`` 不是公开契约，仅在本测试的
        模块内边界验证：哨兵通过对象身份校验后，``tenant_id`` 仍必须
        是 ``TenantId`` 实例，原始字符串一律 fail closed。该哨兵只是
        公开 API misuse guard，不是认证能力。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        scope = TenantScope(tenant_id=TenantId("t-1"), _token=_TENANT_SCOPE_TOKEN)
        with pytest.raises(TypeError):
            replace(scope, tenant_id="raw", _token=_TENANT_SCOPE_TOKEN)

    @pytest.mark.unit
    def test_tenant_scope_accepts_real_sentinel_with_valid_identifier(self) -> None:
        """真实单例哨兵配合合法 ``TenantId`` 可完成受控构造。

        与上一测试互为对照：哨兵校验与 ``TenantId`` 类型防御是两层
        独立检查，合法标识携带真实单例时正常通过。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        scope = TenantScope(tenant_id=TenantId("t-1"), _token=_TENANT_SCOPE_TOKEN)
        assert scope.tenant_id == TenantId("t-1")


class TestMoney:
    """金额值对象严格测试。"""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("amount", "currency"),
        [
            (Decimal("0"), "USD"),
            (Decimal("100.50"), "USD"),
            (Decimal("1E+3"), "HKD"),
            (Decimal("0.0001"), "CNY"),
        ],
    )
    def test_money_accepts_finite_non_negative_decimals(self, amount: Decimal, currency: str) -> None:
        """有限非负 Decimal 与合法货币构造成功。

        Args:
            amount: 有限非负的金额。
            currency: 三位大写货币代码。

        Returns:
            无。

        Raises:
            无。
        """

        money = Money(amount=amount, currency=currency)
        assert money.amount == amount
        assert money.currency == currency

    @pytest.mark.unit
    @pytest.mark.parametrize("bad_amount", [1.5, 100, True, False, "100"])
    def test_money_rejects_non_decimal_amount(self, bad_amount: int | float | bool | str) -> None:
        """float/bool/int/str 金额一律 fail closed。

        Args:
            bad_amount: 非 Decimal 的非法金额输入。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(TypeError):
            replace(Money(amount=Decimal("1"), currency="USD"), amount=bad_amount)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "bad_amount",
        [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("-0.01")],
    )
    def test_money_rejects_non_finite_or_negative_amount(self, bad_amount: Decimal) -> None:
        """NaN/Infinity/负金额一律 fail closed。

        Args:
            bad_amount: 非有限或负的金额。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            Money(amount=bad_amount, currency="USD")

    @pytest.mark.unit
    @pytest.mark.parametrize("bad_currency", ["usd", "US", "USDD", "", "USD ", "US$"])
    def test_money_rejects_invalid_currency(self, bad_currency: str) -> None:
        """非三位大写货币代码一律 fail closed。

        Args:
            bad_currency: 非法货币代码。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            Money(amount=Decimal("1"), currency=bad_currency)

    @pytest.mark.unit
    def test_money_rejects_non_string_currency(self) -> None:
        """非字符串货币一律 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(TypeError):
            replace(Money(amount=Decimal("1"), currency="USD"), currency=123)

    @pytest.mark.unit
    def test_money_equality_and_hash(self) -> None:
        """相同金额与货币的 Money 相等且可哈希。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        left = Money(amount=Decimal("1.50"), currency="USD")
        right = Money(amount=Decimal("1.50"), currency="USD")
        other = Money(amount=Decimal("1.50"), currency="HKD")
        assert left == right
        assert left != other
        assert hash(left) == hash(right)
        assert len({left, right, other}) == 2

    @pytest.mark.unit
    def test_money_add_same_currency(self) -> None:
        """同货币金额相加返回正确结果。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        total = Money(amount=Decimal("10"), currency="USD").add(Money(amount=Decimal("5.5"), currency="USD"))
        assert total == Money(amount=Decimal("15.5"), currency="USD")

    @pytest.mark.unit
    def test_money_add_rejects_cross_currency(self) -> None:
        """不同货币金额相加 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            Money(amount=Decimal("10"), currency="USD").add(Money(amount=Decimal("5"), currency="HKD"))

    @pytest.mark.unit
    def test_money_subtract_same_currency(self) -> None:
        """同货币金额相减返回正确结果。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        diff = Money(amount=Decimal("10"), currency="USD").subtract(Money(amount=Decimal("4"), currency="USD"))
        assert diff == Money(amount=Decimal("6"), currency="USD")

    @pytest.mark.unit
    def test_money_subtract_rejects_negative_result(self) -> None:
        """相减结果为负时 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            Money(amount=Decimal("4"), currency="USD").subtract(Money(amount=Decimal("10"), currency="USD"))

    @pytest.mark.unit
    def test_money_subtract_rejects_cross_currency(self) -> None:
        """不同货币金额相减 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            Money(amount=Decimal("10"), currency="USD").subtract(Money(amount=Decimal("4"), currency="HKD"))

    @pytest.mark.unit
    def test_money_less_than_same_currency(self) -> None:
        """同货币金额支持小于比较。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        assert Money(amount=Decimal("1"), currency="USD") < Money(amount=Decimal("2"), currency="USD")
        assert not Money(amount=Decimal("2"), currency="USD") < Money(amount=Decimal("1"), currency="USD")

    @pytest.mark.unit
    def test_money_less_than_rejects_cross_currency(self) -> None:
        """不同货币金额比较 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            _ = Money(amount=Decimal("1"), currency="USD") < Money(amount=Decimal("2"), currency="HKD")


class TestQuantity:
    """数量值对象严格测试。"""

    @pytest.mark.unit
    @pytest.mark.parametrize("value", [Decimal("0"), Decimal("100"), Decimal("0.5"), Decimal("1E+2")])
    def test_quantity_accepts_finite_non_negative_decimals(self, value: Decimal) -> None:
        """有限非负 Decimal 数量构造成功。

        Args:
            value: 有限非负的数量。

        Returns:
            无。

        Raises:
            无。
        """

        quantity = Quantity(value=value)
        assert quantity.value == value

    @pytest.mark.unit
    @pytest.mark.parametrize("bad_value", [1, 2.5, True, False, "3"])
    def test_quantity_rejects_non_decimal_value(self, bad_value: int | float | bool | str) -> None:
        """float/bool/int/str 数量一律 fail closed。

        Args:
            bad_value: 非 Decimal 的非法数量输入。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(TypeError):
            replace(Quantity(value=Decimal("1")), value=bad_value)

    @pytest.mark.unit
    @pytest.mark.parametrize("bad_value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("-1")])
    def test_quantity_rejects_non_finite_or_negative_value(self, bad_value: Decimal) -> None:
        """NaN/Infinity/负数量一律 fail closed。

        Args:
            bad_value: 非有限或负的数量。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            Quantity(value=bad_value)

    @pytest.mark.unit
    def test_quantity_equality_and_hash(self) -> None:
        """相同数值的 Quantity 相等且可哈希。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        assert Quantity(value=Decimal("3")) == Quantity(value=Decimal("3"))
        assert Quantity(value=Decimal("3")) != Quantity(value=Decimal("4"))
        assert hash(Quantity(value=Decimal("3"))) == hash(Quantity(value=Decimal("3")))

    @pytest.mark.unit
    def test_quantity_arithmetic(self) -> None:
        """数量加减与比较按 Decimal 语义工作。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        base = Quantity(value=Decimal("10"))
        assert base.add(Quantity(value=Decimal("2.5"))) == Quantity(value=Decimal("12.5"))
        assert base.subtract(Quantity(value=Decimal("3"))) == Quantity(value=Decimal("7"))
        assert Quantity(value=Decimal("1")) < Quantity(value=Decimal("2"))
        assert not Quantity(value=Decimal("2")) < Quantity(value=Decimal("1"))

    @pytest.mark.unit
    def test_quantity_subtract_rejects_negative_result(self) -> None:
        """数量相减结果为负时 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            Quantity(value=Decimal("3")).subtract(Quantity(value=Decimal("10")))


class TestUtcHelpers:
    """UTC 时间工具严格测试。"""

    @pytest.mark.unit
    def test_utc_now_returns_aware_utc(self) -> None:
        """当前时间必须带 UTC 时区。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        now = utc_now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timezone.utc.utcoffset(None)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "raw",
        [
            "2026-08-10T07:46:02+00:00",
            "2026-08-10T07:46:02Z",
            "2026-08-10T15:46:02+08:00",
        ],
    )
    def test_parse_utc_accepts_aware_input(self, raw: str) -> None:
        """带时区信息的 ISO 字符串解析为 UTC 时刻。

        Args:
            raw: 携带时区偏移的 ISO 8601 时间字符串。

        Returns:
            无。

        Raises:
            无。
        """

        parsed = parse_utc(raw)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timezone.utc.utcoffset(None)

    @pytest.mark.unit
    @pytest.mark.parametrize("raw", ["2026-08-10T07:46:02", "not-a-time", ""])
    def test_parse_utc_rejects_naive_or_malformed_input(self, raw: str) -> None:
        """naive 或畸形时间字符串 fail closed。

        Args:
            raw: naive 或畸形的时间字符串。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            parse_utc(raw)

    @pytest.mark.unit
    def test_to_utc_iso_serializes_aware_datetime(self) -> None:
        """带时区时刻序列化为 UTC ISO 字符串。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        parsed = parse_utc("2026-08-10T15:46:02+08:00")
        assert to_utc_iso(parsed) == "2026-08-10T07:46:02+00:00"

    @pytest.mark.unit
    def test_to_utc_iso_rejects_naive_datetime(self) -> None:
        """naive 时刻序列化 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        naive = parse_utc("2026-08-10T07:46:02+00:00").replace(tzinfo=None)
        with pytest.raises(ValueError):
            to_utc_iso(naive)

    @pytest.mark.unit
    def test_to_utc_iso_rejects_semantic_naive_datetime(self) -> None:
        """tzinfo 非空但 utcoffset 为空的时刻一律 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        semantic_naive = datetime(2026, 8, 10, 7, 46, 2, tzinfo=_NoOffsetTimezone())
        with pytest.raises(ValueError):
            to_utc_iso(semantic_naive)


class TestPublicExports:
    """包级导出一致性。"""

    @pytest.mark.unit
    def test_package_reexports_domain_symbols(self) -> None:
        """包级导出与 domain 层符号一致。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        assert DomainMoney is Money
        assert DomainQuantity is Quantity
        assert DomainTenantScope is TenantScope
        assert DomainAccountId is AccountId

    @pytest.mark.unit
    def test_all_exports_resolve_to_attributes(self) -> None:
        """``__all__`` 声明的每个符号都能从对应包解析。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for package in (investment_pkg, domain_pkg):
            for symbol_name in package.__all__:
                assert symbol_name in vars(package), f"{package.__name__} 缺少 {symbol_name}"
