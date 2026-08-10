# Slice 1.1 schema/environment erratum acceptance

- **Work unit**：Investment Platform Restoration / Slice 1.1
- **Controller**：Codex
- **状态**：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **Open H/M/L**：`0/0/0`
- **Production/tests edited**：无
- **External actions during plan gate**：未安装依赖、未拉取镜像、未启动或停止容器

## Accepted correction

本 erratum 不改变完整投资平台的 37-slice DAG 或产品范围，只把 Slice 1.1 修到
code-generation-ready：

1. pip constraints 真源与 SQLAlchemy 2.0.51 / psycopg 3.3.4 / Alembic 1.18.5
   Python 3.11 边界；
2. pure domain 与 SQL storage implementation 的相对路径 architecture guard；
3. `dayu_platform` 13-table column/FK/unique/check/index exact schema；
4. tenant FORCE RLS、app/audit 对象权限和 membership negative matrix；
5. transactional Alembic、无 `create_all`、无 CASCADE、完整 downgrade；
6. 一次性 superuser bootstrap admission 与 runtime DSN 隔离；
7. 官方 `postgres:16.14-bookworm` resolved-digest、Slice-owned Docker CLI
   integration fixture 和真实 unit/integration split。

## Review chain

- Initial：Terra FAIL `1/1/0`；MiM PASS-WITH-RISKS `0/2/2`。
- Final：MiM PASS `0/0/0`；Terra FAIL `1/0/0`（bootstrap BYPASSRLS 前提）。
- Corrective：Terra PASS `0/0/0`；MiM PASS `0/0/0`。

Terra 001/002、MiM 001–004 与 Terra final 001 均已在 master plan 和 Controller
fix artifact 逐项接受、修复、复审并 CLOSED。

## Implementation handoff

DeepSeek Flash 可基于本 accepted plan 恢复 Slice 1.1。允许的外部准备仅包括：
clean Python 3.11 dependency resolution/install，以及 pull 官方 PG16.14 image 后记录
本机架构 resolved digest。所有容器必须为随机、带 owner label 的独立资源；禁止
连接、停止、修改或清理现有 PG17/pgvector stack。真实数据、付费模型、通知、券商
和 live execution 均未授权。
