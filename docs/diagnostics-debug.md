# AirProce diagnostics and debug logging

## 简体中文

AirProce 使用 Home Assistant 原生的 Diagnostics 和按集成启用 Debug Logging 的机制，不需要在 `configuration.yaml` 中永久开启全局 debug。

### 下载 Diagnostics

进入：

```text
设置 → 设备与服务 → AirProce → 对应配置项 → 下载诊断信息
```

诊断信息包含当前运行状态、最后一次净化器状态以及集成版本。为了便于公开提交 Issue，以下内容会自动隐藏：

- USR 模块 IP
- USR 用户名和密码
- 设备名称
- 内部稳定设备 ID
- 旧版本遗留的 MQTT 主机、用户名、密码和 Base Topic

### 临时开启 Debug Logging

进入：

```text
设置 → 设备与服务 → AirProce → 右上角 ⋮ → 启用调试日志
```

然后复现一次问题，例如切换开关、修改风速、切换 Auto/Sleep 或等待 Socket B 重连。完成后再次打开菜单并关闭调试日志，Home Assistant 会提供本次调试日志下载。

AirProce debug 日志会记录：

- Socket B 连接与断开
- TX 控制帧和状态查询帧
- RX 协议帧
- 解码后的 power / mode / speed / PM2.5 / temperature / humidity / VOC
- ACK、状态确认和看门狗异常

为了避免日志体积失控，单条 RX 原始协议帧最多只输出前 **64 bytes**。正常运行时不需要保持 debug 开启。

---

## English

AirProce uses Home Assistant's native Diagnostics and per-integration debug logging. Global permanent debug logging in `configuration.yaml` is not required.

### Download diagnostics

Open:

```text
Settings → Devices & services → AirProce → config entry → Download diagnostics
```

Diagnostics include the integration version, runtime connection information, and the last decoded purifier state. USR credentials, USR IP, device name, internal device ID, and legacy MQTT secrets are redacted.

### Enable debug logging temporarily

Open:

```text
Settings → Devices & services → AirProce → ⋮ → Enable debug logging
```

Reproduce the problem, then disable debug logging again and download the generated log file.

Debug logging includes Socket B connectivity, TX commands, RX protocol frames, decoded purifier state, ACK/state confirmation, and watchdog failures. Raw RX frame output is capped at the first **64 bytes per frame** to keep debug logs reasonably small.
