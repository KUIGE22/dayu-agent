# Slice 1.1 schema/environment plan-gap fix

- **Work unit**：Investment Platform Restoration / Slice 1.1
- **Controller**：Codex
- **状态**：**ACCEPTED / DUAL PLAN RE-REVIEW PASS / CLOSED**
- **Production/tests edited**：无
- **External actions**：未安装依赖、未拉取镜像、未启动/停止容器

## 1. Stop evidence

DeepSeek Flash 在 pre-edit gate 零编辑停报。当前 accepted Slice 1.1 同时存在
四个不可实施边界：

1. `tests/investment/test_architecture_boundaries.py` 递归扫描整个
   `dayu.investment`，把 SQLAlchemy 列为全包禁用依赖；Slice 1.1 又要求新增
   SQL storage implementation，且 guard/投资域 README 不在 allowlist。
2. 当前环境没有 SQLAlchemy、psycopg、Alembic；Slice allowlist 没有
   `constraints/**`，无法满足 Python 3.11 min/lock gate。
3. 当前机器只有另一个项目正在运行的 PG17/pgvector stack；Slice 1.1 要求真实
   PostgreSQL 16，不能复用或改动该 stack。
4. master plan 要求 PostgreSQL integration tests 归
   `tests/integration/investment/`，但 Slice allowlist 只列 unit test 文件。

## 2. Controller adjudication

四项均为 **ACCEPTED / PLAN GAP / FIXED IN CANDIDATE PLAN**。修复只更新
Slice 1.1 的 allowlist、依赖/架构/数据库/角色/RLS/测试契约，不改变 37-slice
DAG、产品范围、平台 owner 或 live gate。

## 3. Fixed contract

- `S11-CTRL-01`：加入 `constraints/**`，锁定 SQLAlchemy 2.0.51、psycopg
  3.3.4、Alembic 1.18.5 的兼容窗与 Python 3.11 minimum pins。
- `S11-CTRL-02`：pure domain/config/composition 继续禁 ORM；storage SQL
  implementation 获准依赖 SQLAlchemy/psycopg/Alembic，但不得反向依赖上层。
- `S11-CTRL-03`：固定 Slice 1.1 exact table inventory、public/private tenant
  边界与 deterministic default organization。
- `S11-CTRL-04`：固定 bootstrap/application/audit 三类 role、FORCE RLS 与
  unset/cross-tenant default-deny。
- `S11-CTRL-05`：固定 transactional Alembic、无 `create_all`、无 DSN 回显。
- `S11-CTRL-06`：固定官方 `postgres:16.14-bookworm`，accepted implementation
  pull 后按 resolved digest 启动独立、随机、Slice-owned integration environment；
  严禁触碰既有 PG17 stack。
- `S11-CTRL-07`：unit 与真实 PG16 integration 分文件、分 marker；RLS/migration
  不得由 SQLite 或 fake 证明。

## 4. Primary-source dependency evidence

2026-08-10 查阅官方 package/image registry：SQLAlchemy 当前稳定 2.0.51
（2.1 为 beta）、psycopg 当前 3.3.4、Alembic 当前 1.18.5；三者均支持
Python 3.11。Docker Official Image 当前提供 `postgres:16.14-bookworm`。
最终 implementation 仍须由 resolver 和真实 Python 3.11/PG16 lane 复证，registry
信息本身不替代安装与运行证据。

## 5. Re-review request

Terra 与 MiM Native 必须独立核对：architecture guard 是否仍保护 pure layer；
table/tenant/RLS/role 是否可实现且 default-deny；Alembic downgrade/rollback 是否
不会触碰非本 slice owner；PG16 integration 是否与既有 PG17 完全隔离；依赖 lock
与 Python 3.11 gate 是否闭合。任一路 open H/M/L 非零则不得恢复 implementation。

## 6. Initial dual review adjudication

- Terra `plan-review-20260810-slice-1.1-schema-environment-terra.md`：FAIL，
  open H/M/L=`1/1/0`。001（缺列级 exact schema）与 002（缺对象权限/成员矩阵）
  均 **ACCEPTED / FIXED**。
- MiM Native `plan-review-20260810-slice-1.1-schema-environment-mimo-native.md`：
  PASS-WITH-RISKS，open H/M/L=`0/2/2`。001（guard 路径分组）、002（fixture
  lifecycle）、003（resolver 真值）、004（downgrade seed/object）均
  **ACCEPTED / FIXED**；MiM 把 M-level 描述为“不构成 blocker”与 Gateflow
  open0 规则不一致，因此仍按 open finding 修复后进入 final dual re-review。

修复后的计划新增：逐表 column/FK/unique/check/index/version 真源、
`dayu_platform` schema、app/audit group role 与逐对象权限/default privilege/
membership negative matrix、完整无 CASCADE downgrade、基于 Docker CLI 的
session cluster + per-lifecycle database fixture、相对路径 pure/storage guard，及以
CI pip constraints 命令为唯一 resolver 真值。当前 Controller open H/M/L=`0/0/0`，
但在 Terra + MiM final re-review 均 PASS/open0 前仍冻结 implementation。

## 7. Final re-review observation

- MiM Native
  `plan-final-rereview-20260810-slice-1.1-schema-environment-mimo-native.md`：
  PASS，open H/M/L=`0/0/0`。
- Terra `plan-final-rereview-20260810-slice-1.1-schema-environment-terra.md`：
  FAIL，open H/M/L=`1/0/0`。Final 001 指出普通 `CREATEROLE` principal
  不能创建 `BYPASSRLS` audit role，**ACCEPTED / FIXED**。

Corrective contract 要求 migration bootstrap 是外部提供、短生命周期的 PostgreSQL
superuser；Alembic 在任何 DDL/role/schema side effect 前精确检查当前角色
`rolsuper IS TRUE`，否则稳定 fail closed 且零对象变化。该 DSN 只存在于 migration
进程，绝不进入 runtime composition。真实 PG16 integration 同时锁定 limited
`CREATEROLE NOBYPASSRLS` negative admission 与 official-container superuser
positive upgrade。当前 Controller open H/M/L=`0/0/0`；corrective dual re-review
PASS/open0 前仍不安装依赖、不拉镜像、不编辑实现。

## 8. Corrective closure

- Terra
  `plan-corrective-rereview-20260810-slice-1.1-schema-environment-terra.md`：
  PASS，open H/M/L=`0/0/0`。
- MiM Native
  `plan-corrective-rereview-20260810-slice-1.1-schema-environment-mimo-native.md`：
  PASS，open H/M/L=`0/0/0`。

全部 original/re-review observations 已 CLOSED，Controller open H/M/L=`0/0/0`。
Slice 1.1 erratum accepted，可进入依赖安装、官方 PG16.14 独立环境与代码实施；
不得触碰既有 PG17 stack，也不代表 live data/model/broker authorization。
