# Phase 1 Vertical Integration Acceptance

- Controller: Codex
- Branch / baseline: `codex/investment-platform` / `b9e5b56`
- Status: **ACCEPTED / DUAL CORRECTIVE RE-REVIEW PASS**
- Scope: Investment Platform Restoration Phase 1（Slices 1.1–1.5）

## Accepted result

Phase 1 的 PostgreSQL 与材料对象存储纵向闭环已完成：

- PostgreSQL 16 migrations/RLS/grants：33 passed；
- identity/source repositories 与 production startup black-box：16 passed；
- MinIO S3 blob/recovery/lease：11 passed；
- workspace import/transaction/RLS/CLI vertical：14 passed；
- 合计：**74/74 passed**。

Docker/Colima 使用本地已存在的 pinned PostgreSQL 与 MinIO digest，未隐式 pull；测试结束
后 owned container、network 与 cluster role 均为 0。相关测试 scoped pyright 0，Ruff
F/I/default 与 `git diff --check` 全部通过。全仓 pyright 的 17 项既有、非 Phase 1 问题未
新增或扩散。

## Review closure

- Spark 静态验收的 Docker 环境限制由 Flash 真实容器证据取代；其静态证据继续有效。
- 真实 Docker 初验发现旧 integration test 的 S3 占位契约漂移，Controller 接受为测试
  缺陷，production 保持冻结。
- 初始 Spark 补丁、Flash 运行修正、Terra/MiM 初审、Controller 裁决、corrective fix 与
  最终复审均有独立 artifact。
- Terra 最终 PASS、MiM corrective PASS；最终 open H/M/L = `0/0/0`。

## Boundary carried into Phase 2

Phase 2 必须复用既有 strict platform settings、PostgreSQL composition、tenant/RLS、S3
object owner 与 workspace locator。Durable Job/queue 不得引入 PostgreSQL 与 Host 的双写
真源，不得修改 Phase 1 production contract 来绕过 lease、idempotency、recovery 或
cross-store correlation 设计。

本 acceptance 只授权本地 Phase 1 closure commit；未授权 push、PR、live market、模型、
broker 或用户数据动作。
