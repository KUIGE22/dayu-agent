# S31 暂存证据格式裁定（待独立复核）

- 原Controller aggregate acceptance SHA `c25d6c84e3d7eb9cffaaed8644a6cb9ab5ce1ec38c37f8c1a9cf67924702b26a`保留。首次19件实际nonempty index身份相等，但全cached diffcheck返回exit2，唯一项是冻结的 implementation V2 第32行有新空白EOF；没有提交或push。未把该失败改写为PASS。
- 原V2字节SHA `d46cc852c7dc59667c751a403d932a4eaf0a1d5b05f12b5c1d293f278f0b8b2b`、4456bytes/32LF，保持原.md磁盘文件不变且移出本次index。既有独立fullaggregate报告输入身份继续成立，不改review report或生产/tests五pins。
- 本版新增不可变base64原字节证据 `evidence/s31-aggregate-retry-fix-v2-frozen-original.json`，包含source path/SHA/bytes/LF/完整raw base64，解码严格等于原文件；远程可完整恢复原冻结字节。另存 `implementation-20260928-s31-aggregate-retry-fix-v2-normalized-transcription.md`，只移除原最后一枚多余LF，所有其余4455bytes相等。可读转写不是旧冻结SHA或新实现。
- 暂存范围按原19件减去原V2 .md，增加JSON原字节证据、可读转写、本裁定和本裁定独立复核报告。独立确认原始保留/逐字转写/五pins与fullaggregate范围未漂移后，再核精确nonempty index全集及每件disk/index SHA，并重新实际cached diffcheck；不降checker、增加git whitespace例外或覆盖旧证据。
- 原实现报告仍是输入历史；本裁定只处理其Git暂存格式，不改变M1/M2/L1关闭、77PG/264unit或未来S32/十shape开放状态。当前entry为本三件新artifact独立复核，不声称staged gate已通过。
