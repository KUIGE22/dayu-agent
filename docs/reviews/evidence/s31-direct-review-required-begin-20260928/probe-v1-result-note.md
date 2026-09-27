# Direct review-required begin probe V1 原始失败记录

- 原始执行：stdin Python，pytest collector 把已收集19项替换为一项独立 direct edge probe；工具session13344。
- 原始源码已完整保存为同目录 probe-v1.py，SHA bd78661df8ee4b4b3a57d0bf4c73663e43d8800d65c5d72b6219dcdefacf402a，3103 bytes/35 LF。
- 工具返回：exit1；1 failed / 1 warning / 2.45s。错误位置 `<stdin>:19`，`AttributeError: 'ClaimSnapshot' object has no attribute 'claim_id'`。
- 发生在生产 begin_claim_revision 已成功返回之后。reviewer probe 使用了错误字段，实际 Snapshot 字段为 id；不能把这个失败归类为生产finding或成功验证。
- fixture的完整0001→0007 setup及0007→base teardown正常完成。PytestAssertRewriteWarning是stdin先import anyio后pytest.main引起，非生产失败。
- V2只将同一断言 begun.claim_id/draft.claim_id/required.claim_id 改为各自 .id；其它probe字节相同。V2完整输出另存probe-v2-output.txt，1 passed/1 warning/2.34s。此note是对工具返回的摘录记录，不冒称原始stdout字节副本。
