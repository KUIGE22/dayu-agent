# Slice 2.3 Item 7 startup registration plan Controller acceptance

- 日期：2026-08-22
- 角色：Codex Controller-acceptance metadata writer；记录Controller已给出的裁决，不是Controller、plan reviewer或implementation writer
- 状态：``CONTROLLER ACCEPTED / FRESH SAME-SHA DUAL PASS / OPEN 0/0/0 / DOCS-ONLY LOCAL ACCEPTED PLAN COMMIT NEXT``
- 当前gate：Item 7 corrective plan accepted；下一步仅为exact-ten docs-only local accepted plan commit
- 边界：零implementation、零test/PG/Docker/network、零Git/stage/commit/push/PR；未修改任何review artifact、WIP、README、代码或测试

## 1. Reviewed semantic snapshot

Round-3两路fresh reviewer锁定并证明的是下列同一semantic snapshot；SA26 metadata writeback不把post-metadata
identity冒充review输入：

| 对象 | Reviewed SHA-256 | 行 | 字节 |
|---|---|---:|---:|
| ``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`` | ``6f809046d09a649ba306f55d0d6348e9d56eb99c8fad2c640716e912e5c5bf6f`` | 3903 | 312988 |
| ``docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md`` | ``bd741b02eca4f493d183f72f99d7c9eda50861f383aaf0eab2e030ced8769d5b`` | 196 | 15624 |
| ``dayu/services/startup_preparation.py``（preserved WIP） | ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` | 1689 | 63289 |
| ``tests/application/test_service_startup_preparation.py``（preserved WIP） | ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`` | 4044 | 127443 |

Review baseline为branch ``codex/investment-platform``、HEAD
``d604d8df7613db0103076b3a727156fd74dd9e1b``。两项WIP在本acceptance work unit中只读冻结、明确不进入
docs-only stage；它们尚未执行Item 7 validation、code review或implementation acceptance。

## 2. Fresh same-SHA dual review

| Lane | Immutable artifact identity | Actual model / route | Verdict |
|---|---|---|---|
| DeepSeek V4 Pro Round-3 | ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro-round3.md`` = ``945cecd1329a22576d2132d5e22a465d0bbceec96d8d11c3c31f9aa3218686e8`` / 228 / 19879 | ``deepseek-v4-pro[1m]`` / ``local Claude Code CLI user-dispatch`` | ``PASS / open H/M/L=0/0/0`` |
| MiMo Round-3 | ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-mimo-round3.md`` = ``b015293d8ef980ccb8a63b71840093aedf792d7170b714239da7250da92d32f2`` / 259 / 17265 | ``xiaomi/mimo-v2.5`` / ``MiMoCode native (mimo agent, xiaomi/mimo-v2.5)`` | ``PASS / open H/M/L=0/0/0`` |

两路均从byte0 fresh复审相同master/fix identities；不存在HTTP 402、model/cwd/SHA不明、qualified pass或另一
reviewer输出替代。Round-3新增material finding精确为0。

## 3. Immutable review lineage

下列历史artifact保持immutable；FAIL/PASS只证明各自冻结字节，后轮不会改写前轮结论：

1. Initial DeepSeek review：
   ``docs/reviews/plan-review-20260817-slice-2.3-item7-startup-registration-deepseek-v4-pro.md`` =
   ``714dfa4f51d5ec70a40574ff9cf6fa0d7547d69a082a6e5258ec567fe6d2d38d`` / 115 / 9071，
   ``FAIL / open H/M/L=0/0/1``。
2. Initial MiMo review：
   ``docs/reviews/plan-review-20260822-slice-2.3-item7-startup-registration-mimo.md`` =
   ``989ee6197f752a7800f374bde7566a0a6f03702061d448e12ae67d2ef296e8b9`` / 129 / 12617，
   ``PASS / open H/M/L=0/0/0``。
3. DeepSeek rereview：
   ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro.md`` =
   ``07b918fe6ce8b48c2d3bd67f702589018c9a77cf8ca13611cf6f8481197fea0f`` / 203 / 17178，
   ``FAIL / open H/M/L=0/1/1``。
4. DeepSeek Round-2：
   ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro-round2.md`` =
   ``a6e7044062da0e56c839e1b237a052fc53593d3fc624c412bd282d55aa2f6ae5`` / 320 / 29220，
   ``FAIL / open H/M/L=0/1/2``。
5. MiMo Round-2：
   ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-mimo-round2.md`` =
   ``5606010369b3a566599e88b66a9ceaa988a7d3729f7cb30417973a0ac41944cf`` / 183 / 11298，
   ``PASS / open H/M/L=0/0/0``。
6. DeepSeek Round-3与MiMo Round-3 identities、models、routes、verdicts以§2为准。

## 4. Controller finding adjudication

| Finding / observation | Severity | Controller disposition | Closure |
|---|---:|---|---|
| ``S23-I7-DSV4P-01`` | Low | accepted | SA23 exact-four historical-name residual audit写回后CLOSED |
| ``S23-I7-DSV4P-RR-01`` | Medium | accepted | SA24 exact-seven/root README与Item 7/8边界写回后CLOSED |
| ``S23-I7-DSV4P-RR-02`` | Low | accepted | SA24 review/stage bookkeeping写回后CLOSED |
| ``S23-I7-PR-01`` | review observation | rejected-with-reason | current WIP不是frozen HEAD；negative AST historical-name set是有意regression guard |
| ``S23-I7-PR-02`` | review observation | rejected-with-reason | docstring修复已在allowed test path且由``AGENTS.md``要求，不是scope expansion |
| ``S23-I7-DSV4P-RR2-01`` | Medium | accepted | SA25 §10.1四README逐项职责与exact-seven一致，Round-3双路fresh CLOSED |
| ``S23-I7-DSV4P-RR2-02`` | Low | accepted | SA25 historical 174 / final 176阶段限定，Round-3双路fresh CLOSED |
| ``S23-I7-DSV4P-RR2-03`` | Low | accepted | SA25 ``production Compose`` / ``production composition``区分，Round-3双路fresh CLOSED |
| MiMo ``OBS-RR3-01`` | non-finding | informational only | plan-fix §9已明确supersede历史exact-six wording；不计H/M/L、不改operative contract |

DeepSeek Round-3五条信息性说明均不计finding。最终accepted open H/M/L精确为``0/0/0``；无blocking question、
deferred、needs-more-evidence或unclassified finding。

## 5. Accepted mechanical contract

- preserved input：exact-two WIP identities以§1为准；不得reset/rewrite/discard。
- implementation writer scope：master §11 exact-seven且仅exact-seven；本acceptance不dispatch writer。
- startup truth：exact-one Source Sync handler、exact-four service mapping、PG black-box exact-four。
- README truth：root ``README.md``、``tests/README.md``、``dayu/README.md``、
  ``dayu/investment/README.md``四份职责分离；root只改冻结单段，Item 8 final-nine-lane继续defer。
- named-test truth：Item 7五个startup names exact once，四个historical old names exact zero；aggregate final 176。
- validation truth：master §14.0八步及fail-closed boundary不变；本metadata work unit未执行任何一步，也不把它们写成PASS。
- artifact truth：review/fix/acceptance lineage immutable；任何review identity/model/route漂移都必须STOP。

## 6. Post-metadata closure identities and semantic reverse audit

SA26 post-metadata closure：

| 对象 | Post-metadata SHA-256 | 行 | 字节 | Metadata-only surface |
|---|---|---:|---:|---|
| master | ``13dee18b9fcd0ea470b3cf4333904aceb0f82db87098472d1b5b43ce14c03194`` | 3917 | 314076 | header status、Gate、§17.2 |
| plan-fix | ``a57ec452e71f7f8136b96f7da855546a3ff29cbd0f43d3101f83f62658e5640d`` | 236 | 19145 | top status、唯一§11 SA26 section |
| 本acceptance artifact | final readback tuple | final readback | final readback | new file；自身SHA不嵌入自身preimage，exact identity由writer final report与Controller readback冻结 |

Master operative semantic reverse audit以reviewed START与post-metadata END逐section比较，结果必须逐值相同：

| Operative section | SHA-256 | 行 | 字节 | Result |
|---|---|---:|---:|---|
| §10.1 | ``ddda833e4ab16446b22f41e8c8d19dc05652f40b6cbd655b295b6d9c83fcd638`` | 46 | 4116 | unchanged |
| §11 | ``0c85b634b968687fa04fc6b500a12301e88963993d296320601a051c2258f9d2`` | 232 | 20374 | unchanged |
| §12 | ``2d1462cfc962123ba1ecd58dcb9c00efbdb2193d4ab8f8c1bdf1524af6a37f3e`` | 98 | 8997 | unchanged |
| §14 | ``8795602e80f31883be02682b0cab455ca74b9732ed9f7b4517a8b55ead097a99`` | 283 | 20975 | unchanged |
| §15 | ``f419f0f10ba0fa7e65e03bcace8ecb585b06c4aa7a966467f241af275ddf400b`` | 70 | 6656 | unchanged |

## 7. Exact future docs-only stage manifest

下一local accepted plan commit的stage集合必须exact-equal下列十个path：

1. ``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md``
2. ``docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md``
3. ``docs/reviews/plan-review-20260817-slice-2.3-item7-startup-registration-deepseek-v4-pro.md``
4. ``docs/reviews/plan-review-20260822-slice-2.3-item7-startup-registration-mimo.md``
5. ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro.md``
6. ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro-round2.md``
7. ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-mimo-round2.md``
8. ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro-round3.md``
9. ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-mimo-round3.md``
10. ``docs/reviews/plan-acceptance-20260822-slice-2.3-item7-startup-registration-codex.md``

明确排除``dayu/services/startup_preparation.py``、
``tests/application/test_service_startup_preparation.py``两项preserved WIP，以及所有implementation/test/README/
workflow path和非本manifest review artifact。该stage只能创建local docs-only accepted plan commit；不得push或开PR。

## 8. Controller acceptance and next gate

Controller decision：Round-2 accepted Medium/Low/Low均由两路fresh same-SHA review CLOSED；Round-3新增material finding=0；
accepted open H/M/L=``0/0/0``。因此Item 7 corrective plan状态为：

``CONTROLLER ACCEPTED / FRESH SAME-SHA DUAL PASS / OPEN 0/0/0 / DOCS-ONLY LOCAL ACCEPTED PLAN COMMIT NEXT``

这只关闭plan-review gate。下一动作只能是§7 exact-ten docs-only local accepted plan commit；commit成功前不得dispatch
exact-seven implementation writer。implementation/test/PG、code review、deployment、push与PR均未完成也未获本artifact授权。
