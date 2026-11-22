# 回绕录制的标定交班

白班从冻结卷发行指定通道的一组选中测次。标定单可能在白班关库以后才到。夜班凭固定件判定标定值是否可以同时出现在一条原轨上，并标明仍待补测的选中位置。普通门槛复核继续由 README.md 中的 V1 接口办理。

## 冻结发行

在 `lab.py` 增加 `issue_unwrap(source, registry, revision_id, channel, modulus, bounds, max_step, positions)`，返回和 `issue_packet` 相同的 `FixedPacket`。`revision_id` 指定现有冻结修订。`channel` 是该修订中有测次的通道名。`modulus` 为正整数，`bounds` 为闭量程 `[lo, hi]`，接受列表或元组，两个端点均为整数，`lo <= hi`。`max_step` 为非负整数。`positions` 为非空列表或元组，元素是互异的零基原卷位置，且都属于指定通道。按原位升序发行，输入顺序无关。参数中的整数均拒绝布尔值。

单位为 mV。把指定通道从头至尾的原读当作余数，要求每读为 `[0, modulus)` 内的整数。原读可沿用冻结记录的 `Fraction`，分母须为 1。可能原轨的每拍实值是闭量程内和该拍余数同余的整数。同一通道相邻两拍的实值差绝对值至多为 `max_step`，中间夹有别通道的行也按同道相邻两拍处理。整条指定通道均须参与核定，包括选中位置之前、之间和之后的拍。补读不参与。整轨无解时拒发。

V2 使用现有规范 JSON 外层、清单摘要、出站号和完整包摘要规则。外层 `version` 取 `2`，清单字段为 `kind`、`recording_id`、`revision_id`、`channel`、`modulus`、`bounds`、`max_step`、`selected` 和 `evidence`。`kind` 为 `unwrap`。`selected` 按原位升序，每项为 `position`、整数 `residue` 和 `source`，出处沿用 `artifact`、`start`、`end` 的原读半开区间。`evidence` 的编码由实现选择，须在交付说明中写明结构和含义。证据须精确表达全部且仅有能延伸为合法整轨的选中位实值组合。未选测次的逐拍余数、测次身份和出处留站。允许全量计算。

原 `reissue_packet` 按出站号补发原字节。沿用 `receive_packet(inventory, payload, digest, expected_outbound_id)` 点收 V2，用可信交付单核对身份、摘要及规范字节，核对选中行和联合证据的结构与一致性后才实收。收件端无须访问白班或重建未选原据。保留既有点收编号及错误约定。只把 V1 外层版本改为 2 的件仍按 `version` 类错件拒收。

## 夜班标定和领取

在 `lab.py` 增加 `sign_unwrap(inventory, reports, acceptance_id, anchors)`，返回 `SignedReport`。`anchors` 是所选原位到量程内整数实值的映射，可为空，位置和值均拒绝布尔值。位外和量程外属于非法输入。量程内的标定若与余数或共同轨迹矛盾，属于可签存的 `conflict`。只用指定的 V2 实收件，全部标定必须落在同一条相容原轨。存在共同轨迹时，对每个所选原位检查所有相容轨迹，只有全体实值相同才签唯一值，其余签多解。

报告使用原有 `report_id`、`request_digest` 和 `packet`，其中 `packet` 固定原出站号、修订号和完整包摘要。`request` 含 `kind`（`unwrap`）、`acceptance_id` 和 `anchors`，其中 `anchors` 按原位升序记为 `[位置, 实值]` 对的数组。`outcome` 为 `conflict` 或 `consistent`。冲突时 `rows` 为空；相容时按 `selected` 原序交付，每行保留选中位的三个字段，另有 `status` 和 `value`。唯一时 `status` 为 `unique`，`value` 为整数；多解时 `status` 为 `ambiguous`，`value` 为 `null`。

同一实收号和等价标定复领原签报。报告和首执同次提交。`read_report` 和 `read_receipt` 按原号领取固化结果，重开后也能领取。普通 `sign_review` 拒用 V2，`sign_unwrap` 拒用 V1。参数非法、整轨无解和送错复核入口抛 `ValueError`。未知编号沿用 `KeyError`，错件沿用 `PacketRejected`，数据库错误沿用各原入口约定，签报提交失败抛 `ReportCommitError`。失败操作不留下本次新增的发行件、实收或半份签存。成功的先前业务仍可领取。

## 对照录制

`unwrap_examples.py` 的 `EXAMPLES` 保存发行参数和外站标定输入。`freeze_example(source, name)` 用现有登记与冻结入口准备指定录制并返回冻结修订。`dict(example.anchors)` 得到示例标定映射。直接运行该文件可先核对这些录制能沿 V1 完成发行、补发、实收及原门槛签报。

| 录制 | 余数原序 | `modulus` | `bounds` | `max_step` | 所选原位 | 标定和签报 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `middle-five` | 0, 5, 0 | 10 | [0, 20] | 6 | 0, 2 | `{0: 0, 2: 10}` 签相容，实值为 0、10 |
| `middle-zero` | 0, 0, 0 | 10 | [0, 20] | 6 | 0, 2 | 同一张标定签冲突 |
| `hidden-prefix` | 4, 0 | 10 | [0, 10] | 4 | 1 | 空标相容，末位唯一为 0。步限改为 3 则拒发 |

前两卷只标首位 0 时，第一卷末位多解，第二卷末位唯一为 0。两卷空标时两个所选位均多解。第一卷把首尾分别标为 0、20 时签冲突。相容报告的原出处取自实际选中的原读。错摘要或错出站号不登记实收，位外标定或混用新旧入口不签报。签报提交失败后可重开核对账册，再办理同一请求。

沿用根目录 `.pointwise-runtime.json` 的版本 1 和 `cli` 类型。`setup` 列准备命令的参数数组，可为空。`verify` 和 `demo` 各为一条命令的参数数组。交付时让核验执行原回归及标定交班的端到端检查，失败返回非零。演示用前两卷展示关闭白班后同一合标的不同裁决，再重开报告库领取原结果及首执。
