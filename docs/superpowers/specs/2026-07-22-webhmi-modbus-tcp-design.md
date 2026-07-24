# WebHMI Modbus TCP 通讯改造设计

## 目标与范围

将 LMM 的 PLC 通讯从自定义 TCP/JSON 改为原生 Modbus TCP，同时保持浏览器现有 WebSocket/JSON 变量绑定方式。

本次只修改 HMI 通讯层、变量映射、Gateway、测试和相关文档，不修改轴控制、自动流程、力跟随、力采集及安全输入逻辑。

## 架构

```text
WebHMI
  │ WebSocket + JSON（现有 HMI_* 符号）
  ▼
Node.js Gateway / Modbus TCP Server
  ▲ PLC周期执行 FC03/FC16
  │
PLC 原生 Modbus TCP Master
  │ 连续 WORD 过程映像
  ▼
PRG_TcpHmi → Tcp_* 影子变量 → PRG_Logic 仲裁
```

浏览器不感知 Modbus 地址、字节序或 PLC 型号。Gateway 是唯一 Modbus TCP Server 和变量名转换层，PLC 原生 Modbus TCP Master 主动轮询。PLC 仍是命令校验、控制源仲裁和安全停机的最终裁决者。

## 方案选择

采用连续寄存器快照，不采用“每个变量一次 Modbus 请求”，原因如下：

- PLC Master 用 FC03 一次读取完整命令快照，降低请求数量和混合新旧参数的概率。
- PLC Master 用 FC16 一次写回完整状态快照，Gateway 统一发布给所有 WebSocket 客户端。
- 固定长度数据区便于协议版本、快照序号、心跳和诊断扩展。
- PLC 只编解码 WORD 过程映像，不处理字符串和 JSON。

不在 PLC 中继续运行自定义 `FB_TCPServer`。按设备树落地为 PLC Master + Gateway Server。

## 地址与数据表示

### 数据区

| 方向 | Gateway Holding Register | PLC过程映像 | 长度 | 写者 |
|---|---:|---:|---:|---|
| Gateway → PLC 命令（PLC FC03读） | `1000..1063` | `%IW103..%IW166` | 64 WORD | Gateway |
| PLC → Gateway 状态（PLC FC16写） | `1100..1163` | `%QW44..%QW107` | 64 WORD | `PRG_TcpHmi` |

Gateway内部使用零基PDU地址 `1000/1100`。InoProShop设备树按更新后 `LMM.xml` 的十进制偏移填写。过程映像起点根据现有 COM0 后的自动分配确定；现场编译时必须核对 `%IW103/%QW44`，不一致时只调整 GVL AT 地址，不改变 Modbus协议地址。

### 类型

- `BOOL`：打包在 WORD 位域中，位值只允许 `0/1`。
- `INT/UINT`：一个 WORD。
- `DINT/UDINT`：两个连续 WORD，高字在前。
- PLC `REAL` 不直接传 IEEE-754；协议统一传有符号缩放 `DINT`，避免不同设备的浮点字序差异。
- 位置、速度、距离、增益和角度误差缩放1000倍；力值缩放100倍。
- 所有保留寄存器写零，接收端忽略其内容。

### 单一映射源

新增 `config/modbus-map.json` 作为变量名、方向、偏移、位号、类型和缩放规则的唯一来源。

生成脚本输出：

- `gateway/modbus-map.generated.js`：Gateway 编解码表。
- `docs/plc/MODBUS_MAP.md`：现场调试地址表。
- PLC ST 映射片段，由重构脚本写入 `LMM.xml`。

生成文件带协议版本与源文件摘要。测试必须验证生成结果没有地址重叠、越界、重复变量或非法类型。

## 命令快照

命令区固定包含：

1. 协议魔数。
2. 协议主版本和次版本。
3. 快照序号起始值。
4. Gateway 心跳计数。
5. 命令位域。
6. 模式、回零轴和自动次数。
7. 点动、旋转、自动、力控和纠偏参数。
8. 保留区。
9. 快照序号结束值。

Gateway 每100 ms更新一次完整64 WORD命令镜像。PLC每100 ms以内通过FC03读取；Web值变化时允许Gateway立即更新内存，但网络请求由PLC主站周期决定。

PLC 仅在以下条件同时成立时接收新快照：

- 魔数正确。
- 主版本兼容。
- 起始序号等于结束序号。
- 序号不同于上一次已接受序号。
- 所有枚举和参数均在 PLC 允许范围内。

快照非法时，PLC 保留最后一组数值参数，但清除启动、点动、回零、去皮等动作命令，并记录通讯诊断码。

## 状态快照

状态区固定包含：

1. 协议魔数和版本。
2. PLC 状态序号。
3. 最近接受的命令序号。
4. Gateway 心跳回显。
5. 通讯状态和诊断码。
6. 设备状态、模式、报警和自动步骤。
7. 自动、回零、力传感和轴就绪位域。
8. 实际力、M1/M2/Y/Z/R位置。
9. M1/M2速度命令。
10. 保留区及尾部状态序号。

`PRG_TcpHmi` 每个 MainTask 周期更新本地状态镜像，PLC通过FC16周期写入Gateway。Gateway收到完整状态区后向浏览器广播现有 `t:"s"` JSON。

## 命令语义与仲裁

- WebHMI 继续发送 `t:"w"` 和现有 `HMI_*` 符号。
- Gateway 保留写白名单，拒绝 `AxisCmd_*`、设备派生状态和未知变量。
- Gateway 将 Web写入合并到完整命令镜像，而不是单独写某个 PLC 变量。
- `PRG_TcpHmi` 将有效命令快照解码到 `Tcp_*`，不直接写 `AxisCmd_*`。
- `PRG_Logic` 保持“面板/远程整组互斥”的控制源仲裁。
- PLC 端参数继续执行范围限制；Gateway 校验只用于尽早反馈，不替代 PLC 校验。

动作类变量采用电平加快照序号传输。PLC 对启动、复位、自动启动、回零执行和去皮在本地做上升沿检测；点动、停止和自动中止保持电平语义。

## 心跳、失联与恢复

Gateway 每100 ms递增16位心跳计数并更新命令区，回绕合法。PLC通过FC03读入并记录最后一次心跳变化时间。

超过1秒无有效心跳时：

- `Tcp_xConnected := FALSE`。
- `Tcp_xTimeout := TRUE`。
- 清除全部远程点动、启动、回零和去皮命令。
- 强制远程停止和自动中止至少一个PLC周期。
- `PRG_Logic` 退出远程控制源并回到面板源。

连接恢复后，只有收到魔数、版本和双序号均有效的完整新快照，才能重新置 `Tcp_xConnected`。恢复不会自动重启自动流程或恢复点动。

Gateway 连接失败时不得自动切换到会运动的 Mock。生产模式显示断线并持续退避重连；Mock 仅在显式 `MOCK_PLC=1` 时启用。

## 安全边界

- 物理急停输入及硬接线安全回路是唯一安全急停。
- Web/Modbus“急停”只能作为非安全等级的停止请求，不得在文档或界面中宣称安全功能。
- Modbus TCP没有认证和加密。PLC 502端口仅允许 Gateway 所在控制网访问。
- 浏览器不能直连 PLC。
- 通讯程序不得直接调用 `PRG_Axis_Control`，轴任务仍只通过 GVL 交换命令和反馈。

## PLC 改动

- GVL 新增两个64 WORD Modbus镜像区及通讯诊断变量，写者唯一。
- 保留 POU 名称 `PRG_TcpHmi`，将职责改为寄存器校验、编解码、心跳和状态快照。
- 从 `PLC_PRG` 保持 `PRG_TcpHmi(); PRG_Logic();` 的执行顺序。
- 删除 `FB_TCPServer` 的实例、类型及对象树条目。
- 删除 PLC 自定义 TCP/JSON 接收、发送和字符串解析代码。
- 保留更新后设备树中的 `MODBUS_TCP` Master 和 `modbusTcp` Slave。
- 将输入通道改为FC03读取 `1000..1063`，映射 `%IW103..%IW166`。
- 将输出通道改为FC16写入 `1100..1163`，映射 `%QW44..%QW107`。
- 远端地址保持用户样例中的 `192.168.1.1:502`，现场可在设备树中按Gateway实际IP修改。

设备树节点、GUID、类型和父子关系全部复用更新后的XML样例；脚本只修改现有两个通道的方向、偏移、长度和数组上界，不创建未知设备节点。

## Gateway 改动

- 使用维护中的 Node.js `modbus-serial` Modbus TCP Server。
- 将 Modbus传输、映射编解码、WebSocket协议和Mock拆成独立模块。
- 生产模式断线不再回退Mock。
- 保持现有 WebSocket消息格式和Web页面变量名不变。
- 对非法类型、越界参数、未知变量和只读变量返回结构化错误。
- 暴露 `_gateway`、PLC连接状态、往返时间、最近异常码和协议版本。

## 测试与验收

### 自动化测试

- 映射生成：地址无重叠、64 WORD边界、变量唯一、版本一致。
- 编解码：BOOL位域、INT、UDINT、REAL及心跳回绕。
- Gateway写入：白名单、完整FC16快照、写节流和序号递增。
- Gateway读取：FC03状态解码及现有 `t:"s"` JSON兼容。
- 故障：拒绝错误魔数/版本/双序号，断线不进入Mock，重连不恢复动作命令。
- PLC静态检查：新镜像变量、`PRG_TcpHmi`调用、旧 `FB_TCPServer` 完整移除、XML良构。

### 现场联调

1. InoProShop编译无错误。
2. Modbus调试器可读写指定寄存器区。
3. Gateway显示PLC在线且版本匹配。
4. 手动模式逐轴点动，松开按钮立即停止。
5. 拔网线，1秒内远程动作清零且自动流程中止。
6. 恢复网络后设备不自行运动。
7. 面板在远程掉线后仍可按现有安全条件接管。
8. 力值、轴位置、报警和自动步骤与PLC监控值一致。

## 完成标准

- Web页面无需使用任何Modbus地址。
- PLC不再解析JSON或维护TCP Socket状态机。
- Gateway与PLC只通过版本化连续寄存器快照通讯，PLC是Master，Gateway是Server。
- 单一映射源能够重复生成Gateway映射、PLC映射片段和地址文档。
- 自动化测试通过，XML良构，Node语法检查通过。
- Gate D联调检查通过前，不进行自动循环烧录。
