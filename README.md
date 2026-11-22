# 材料试验室录制卷交班

白班操作员登记工单、试样批次和仪器，接纳顺序测次，冻结修订后为夜班发行固定件。夜班技师点收指定件，等工艺单给出参考和门槛后离线核账。质量负责人按报告中的原读、采用证据、参考出处和待核项审阅结果。勘误另成修订，历史签报仍可按号领取。

## 运行

需要 Python 3.11，使用标准库。由平台物化的项目根目录运行完整回归及演示。

```text
python3 -B check_project.py
python3 -B demo.py
```

`demo.py` 从 `samples/shift.json` 接纳三次测量，关闭白班库后实收、用两个门槛签报，再重开报告库复领。门槛 10 的差值是 `7, 12, 4`，门槛 11 的差值是 `7, 11, 30`。

## Python 接口

`lab.py` 导出以下正常业务入口。存储对象是上下文管理器，也可显式 `close()`。示例中的路径由调用方选择。报告库与其夜班实收账配对使用，历史领取只打开报告库即可。

| 操作 | 调用和结果 |
| --- | --- |
| 登记录制 | `register_recording(source, recording_id, work_order, batch_id, instrument_id, channels)` 返回录制定义 |
| 接纳与冻结 | `accept_recording(source, recording_id, draft_id, occurrences)` 接纳草稿，可用 `append_occurrence(source, draft_id, occurrence)` 接续；`freeze_revision(source, draft_id, revision_id)` 返回冻结修订 |
| 一次办理接纳和冻结 | `record_revision(source, recording_id, draft_id, revision_id, occurrences)` 依次办理上述两步。接纳失败不生成草稿，冻结失败时已接纳草稿可重试 |
| 勘误 | `create_correction_revision(source, base_revision_id, revision_id, occurrences)` 以完整更正测次建立新修订，原修订继续可发 |
| 发行及补发 | `issue_packet(source, registry, revision_id)` 返回含 `outbound_id`、`digest`、`payload` 的固定件；`reissue_packet(registry, outbound_id)` 保存补发记录并返回原件 |
| 夜班实收 | `receive_packet(inventory, payload, digest, expected_outbound_id)` 返回实收记录，其 `acceptance_id` 用于核账。编号和摘要来自交付单。同件重复点收分配不同实收号 |
| 签报 | `sign_review(inventory, reports, acceptance_id, initial_references, threshold)` 返回 `SignedReport`，含报告字典和成功回执。相同收件及请求复用原签报 |
| 领取 | `read_report(reports, report_id)` 返回原报告及原成功回执；`read_receipt(reports, report_id)` 返回对应回执 |
| 回绕发行（V2） | `issue_unwrap(source, registry, revision_id, channel, modulus, bounds, max_step, positions)` 返回与 `issue_packet` 同形的 `FixedPacket`；按冻结卷指定通道的整轨核定，无合法整轨拒发 |
| 标定签报（V2） | `sign_unwrap(inventory, reports, acceptance_id, anchors)` 对 V2 实收支应用整张标定单，返回 `SignedReport`；`anchors` 为所选原位到量程内整数实值的映射，可为空 |

存储类型为 `RecordStore`、`IssueRegistry`、`ReceiveStore` 和 `ReportStore`。首次打开创建缺失表和索引，重复打开保留数据。接纳、冻结、勘误、发行、实收及签报各有自己的持久化边界。

## 数据和判定

`record.measurements` 提供 `SourceRef`、`ReadingCandidate`、`MeasurementOccurrence` 和 `MeasurementSequence`。每条 `SourceRef` 记录原据标识和非空半开字节范围。位置从零起，必须和原序一致。录制通道具有唯一名称，测次号在当前修订内唯一。模板可复用，原读和可选补读各自携带来源。空草稿可接续，冻结至少需要一条测次。`sequence_from_data` 可将样例形状的字典转为接纳对象。

仪器对象中的值用 `Fraction` 表示。工艺单和样例转换可接受 `Fraction`、整数或精确字符串，例如 `5`、`9/2`、`0.5`。单位为 mV。复核需要所有有测次通道的初始参考，也允许给已登记但本卷未测的通道提供参考。未知通道、缺少必需参考和负门槛均拒绝。

每行使用其通道的入行参考。仅当原读与参考的绝对差严格超过统一门槛，才采用本次补读，签出补读减旧参考，并推进参考及其出处。其余行签出原读减当前参考，保持参考。必需补读缺失时，首条待核行保留其已知入行参考，出行参考为空。后续同通道的待核行继续保留原读和阻塞测次号，采用值、差值和未知参考为空。报告顺序与录制一致。

V1 包外层含版本、出站号、清单及清单摘要。传递校验使用完整包字节的 SHA-256 摘要。实收核对预期身份、两层内容关系、规范编码和测次结构后才登记。摘要用于完整性校验，交付单提供正确的身份和摘要。报告及成功回执同事务落库，回执绑定报告、实收号及请求摘要。重新打开、改变工艺单或另行勘误后，旧报告和首执仍原样领取。

非法录制及复核参数抛出 `ValueError`，错件抛出带 `code` 的 `PacketRejected`，未知编号抛出 `KeyError`。白班和点收的数据库写入错误沿用 `sqlite3.Error`，签报的数据库错误以 `ReportCommitError` 返回。失败的持久操作无新记录。待核属于可签存的业务结果。

## 回绕标定交班（V2）

`issue_unwrap` 把指定通道从头至尾的原读当作模数 `modulus` 下的余数，仅接受分母为 1 且落在 `[0, modulus)` 的整数原读；补读不参与核定。候选实值是闭量程 `[lo, hi]` 内与该拍余数同余的整数，同道相邻两拍实值差绝对值至多为 `max_step`（夹有别通道行时仍按同道相邻处理）。整条通道均须参与，任一无解即拒发。整数参数一律拒绝布尔值。

V2 外层仍为规范 JSON，含 `version=2`、`outbound_id`、`content_digest` 和 `manifest`，出站号与两层摘要规则与 V1 相同。清单字段为 `kind`（固定 `unwrap`）、`recording_id`、`revision_id`、`channel`、`modulus`、`bounds`、`max_step`、`selected` 和 `evidence`。`selected` 按原位升序，每项含 `position`、整数 `residue` 与原读半开出处 `source`；未选测次的逐拍余数、身份和出处不进包，留站保存。

`evidence` 是精确联合可行证据：一个按字典序排序、去重的整数数组数组，每个内层数组与 `selected` 等长，第 `i` 个值是第 `i` 个选中位在某条合法整轨上的实值；整体恰好覆盖全部且仅有能延伸为合法整轨的选中位实值组合。收件端不访问白班、也不重建未选原据，只核对该结构与选中行的一致性后实收。

`sign_unwrap` 只用 V2 实收件，`sign_review` 拒用 V2。位外或量程外标定是非法参数（`ValueError`）；量程内标定与余数或共同轨迹矛盾时签存 `outcome="conflict"` 且 `rows` 为空。相容时 `rows` 按 `selected` 原序，每行保留 `position`、`residue`、`source`，另有 `status`（`unique`/`ambiguous`）和 `value`（多解为 `null`）。同一实收号与等价标定复领原签报；报告与首执同事务落库，重开报告库即可原样领取。只把 V1 外层版本改成 2 的件按版本类错件拒收，错摘要或错出站号不登记实收。
