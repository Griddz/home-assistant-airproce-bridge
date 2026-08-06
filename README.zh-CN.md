# AirProce Socket B Bridge for Home Assistant

[English](README.md) | **简体中文**

这是一个适用于艾泊斯（AirProce）空气净化器的 Home Assistant 自定义集成。它利用净化器内部 USR 串口转网络模块提供的第二路透明 TCP 连接（Socket B），在保留官方 App 和 Socket A 云端连接的同时，将净化器接入 Home Assistant。

艾泊斯官网：[https://airproce.net/](https://airproce.net/)

目前已实际验证可用的型号：

- **AI-300**
- **AI-600**

其他型号是否使用相同协议帧尚未验证。

## 最重要的先决条件

> **只有能够打开净化器内部“有人物联网”透传管理网页的设备，才具备使用本集成的基本条件。**

请先在浏览器打开：

```text
http://<净化器IP>:80
```

常见默认登录信息：

```text
用户名：admin
密码：admin
```

也可以写成：

```text
Username: admin
Password: admin
```

成功登录后，应能看到“有人物联网”管理页面，并在“透传参数”中看到 Socket A 和 Socket B 设置。若该网页无法打开、登录信息已被修改且未知，或者页面中没有 Socket B，本集成不能按本文方案工作。

下面是根据已验证页面重新绘制并脱敏后的示意图；实际界面可能因 USR 固件版本略有差异：

![USR 透传管理网页示意图](docs/usr-web-interface.svg)

## 实体

本集成通过 MQTT Discovery 创建：

- `fan`：开关、手动 1～6 档、自动模式、睡眠模式
- 温度 Sensor
- 湿度 Sensor
- PM2.5 Sensor
- VOC Sensor

Socket B 断开，或主动看门狗检测到 TCP 假连接时，风扇和所有传感器都会显示为“不可用”。

## 工作架构

```text
Socket A → AirProce 官方云端
           官方 App 保持可用

Socket B → Home Assistant TCP 监听端口
           → 协议解析与控制
           → MQTT Broker
           → Home Assistant MQTT Discovery 实体
```

本版本保留了此前独立桥接程序中已经实际验证通过的 MQTT 控制和状态反馈逻辑。自定义集成负责 Socket B 监听、USR/MQTT 配置和桥接进程；最终的风扇和传感器由 MQTT Discovery 创建，因此会显示在 Home Assistant 的 MQTT 集成设备中。

## 使用要求

1. 建议使用 Home Assistant 2026.6 或更新版本。
2. Home Assistant 已配置 MQTT 集成，并连接到与本集成中填写的同一个 Broker。
3. USR 模块必须能访问 Home Assistant 主机的局域网 IP 和 Socket B 监听端口。
4. 同一个 TCP 监听端口只能由一个程序占用；安装本集成前应停止旧的独立桥接脚本或服务。
5. 必须能登录净化器的 USR 管理网页并手动配置 Socket B。

## 安装

### 使用 HACS 自定义仓库

1. 打开 HACS。
2. 添加以下自定义仓库，类别选择 **Integration**：

```text
https://github.com/Griddz/home-assistant-airproce-bridge
```

3. 安装 **AirProce Socket B Bridge**。
4. 重启 Home Assistant。

### 手动安装

复制：

```text
custom_components/airproce_bridge
```

到：

```text
/config/custom_components/airproce_bridge
```

然后重启 Home Assistant。

## 配置

进入：

```text
设置 → 设备与服务 → 添加集成
```

搜索：

```text
AirProce Socket B Bridge
```

### USR 模块和净化器

配置页面包括：

- 设备名称
- 净化器型号
- 稳定设备 ID
- USR 模块 IP 地址
- USR 网页端口
- USR 用户名和密码，常见默认值为 `admin` / `admin`
- Socket B 监听地址和监听端口

USR 登录信息仅用于验证管理网页是否可访问以及用户名、密码是否正确。v0.1.0 **不会自动修改 USR 网页中的参数**。

请在 USR 网页中手动将 Socket B 设置为：

```text
协议：TCP-Client
服务器地址：<Home Assistant 局域网 IP>
端口：<本集成中配置的监听端口，第一台默认 9001>
```

Socket A 保持官方设置，例如：

```text
协议：TCP-Client
服务器地址：d2.airproce.com
端口：8800
```

### MQTT Broker

需要填写：

- Broker 地址和端口
- MQTT 用户名和密码
- MQTT Base Topic
- Discovery Prefix

每台净化器必须使用独立的 MQTT Base Topic 和稳定设备 ID。

### 主动看门狗

净化器正常情况下大约每 15 秒上报一次状态。默认看门狗在连续 45 秒没有收到有效状态帧后才主动查询一次；查询失败会再重试一次。如果仍无有效回复，集成会关闭疑似假连接的 Socket B 会话并发布 `offline`。

## 第二台及更多净化器

添加第二台净化器时，以下四项**必须不同**：

| 配置项 | 第一台示例 | 第二台示例 |
|---|---|---|
| 稳定设备 ID | `airproce_ai600_bedroom` | `airproce_ai300_livingroom` |
| USR 模块 IP | `192.168.1.112` | `192.168.1.113` |
| Socket B 监听端口 | `9001` | `9002` |
| MQTT Base Topic | `airproce/bedroom` | `airproce/livingroom` |

两台设备可以共用：

- 同一个 Home Assistant 主机 IP
- 同一个 MQTT Broker
- 相同的 MQTT 用户名和密码
- 相同的 Discovery Prefix
- 相同的 USR 默认用户名和密码

第二台净化器的 USR Socket B 应设置为：

```text
协议：TCP-Client
服务器地址：<同一个 Home Assistant 局域网 IP>
端口：9002
```

不要让两台净化器使用同一个 Socket B 监听端口，也不要使用相同的 MQTT Base Topic，否则会导致端口占用冲突，或者两台设备的状态和控制相互覆盖。

设备名称也建议按房间区分，例如“AirProce 主卧”和“AirProce 客厅”。稳定设备 ID 建立后尽量不要修改，否则 Home Assistant 可能将其识别为一套新实体。

## 控制和状态反馈

- 手动风速为 1～6 档。
- `auto` 和 `sleep` 作为 Fan 实体的预设模式。
- 设置手动风速时会退出预设模式。
- 自动和睡眠命令的第一个控制字节使用最近有效的风速上下文，以保留实测发现的协议特征：睡眠模式控制帧与当时 Fan 状态有关。
- 下发控制后，桥接程序等待命令 ACK，随后立即发送状态查询，并以净化器返回的真实状态更新 Home Assistant。

## 从独立脚本迁移

1. 停止旧的 Python 脚本或 systemd 服务。
2. 确认 Home Assistant 主机上的 `9001` 等监听端口没有被其他程序占用。
3. 安装并配置本集成。
4. 将 USR Socket B 的服务器地址改为 Home Assistant 主机的局域网 IP。
5. 确认风扇和传感器状态能够及时更新。
6. 如果以前使用了不同的 MQTT Object ID，可清理旧的保留 Discovery Topic。

## 隐私和安全

仓库不包含私人局域网 IP、MAC 地址、实际 MQTT 用户名和密码、房间名称或用户专属路径。凭据保存在 Home Assistant Config Entry 中；诊断信息会隐藏 USR/MQTT 地址、用户名、密码和 MQTT Base Topic。

发布 Home Assistant 配置导出或诊断文件前，仍应自行检查其中是否包含敏感信息。

## 已知限制

- 不同 USR 模块和固件的网页提交接口可能不同，因此本版本不会自动修改 Socket B 参数。
- 控制帧通过逆向分析获得，目前已在 AirProce AI-300 和 AI-600 上验证。
- 本版本为了保留已经验证稳定的桥接逻辑，创建的是 MQTT Discovery 实体，而不是原生 Home Assistant 平台实体。

## 代码生成说明

本仓库中的全部代码均由 **ChatGPT 5.6** 生成。

## License

MIT
