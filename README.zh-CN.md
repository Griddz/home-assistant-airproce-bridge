# AirProce for Home Assistant

[English](README.md) | **简体中文**

这是一个适用于艾泊斯（AirProce）空气净化器的 Home Assistant 原生自定义集成。它利用净化器内部 USR 串口转网络模块提供的第二路透明 TCP 连接（Socket B），在保留 Socket A 官方云端连接和官方 App 的同时，让净化器直接接入 Home Assistant。

**新版本不需要 MQTT Broker，也不需要 Home Assistant 的 MQTT 集成。**

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

成功登录后，应能看到“有人物联网”管理页面，并在透传参数中看到 Socket A 和 Socket B。若该网页无法打开、登录信息已被修改且未知，或者页面中没有 Socket B，本集成不能按本文方案工作。

下面是根据已验证页面重新绘制并脱敏后的示意图；实际界面可能因 USR 固件版本略有差异：

![USR 透传管理网页示意图](docs/usr-web-interface.svg)

## 原生 Home Assistant 实体

每台净化器在 Home Assistant 中作为一个原生设备，包含：

- `fan`：开关、6 个硬件风速档、自动模式、睡眠模式
- 温度 Sensor
- 湿度 Sensor
- PM2.5 Sensor
- VOC Sensor

Home Assistant 原生 Fan 规范使用百分比表示风速，所以 1～6 档会显示为 6 个百分比档位；Fan 实体的 `hardware_speed` 属性仍会显示净化器真实的 `1`～`6` 档。

Socket B 断开或看门狗判定 TCP 假连接时，实体会直接显示为“不可用”。中间不再经过 MQTT Discovery。

## 工作架构

```text
Socket A → AirProce 官方云端
           官方 App 保持可用

Socket B → Home Assistant TCP 监听端口
           → AirProce 协议解析与控制
           → 原生 Fan + Sensor 实体
```

控制和状态反馈全部在净化器与 Home Assistant 之间本地完成。发送命令后，集成等待净化器 ACK，再立即查询状态，并使用净化器确认返回的真实状态更新 Home Assistant。

## 使用要求

1. 建议使用 Home Assistant 2026.6 或更新版本。
2. USR 模块必须能访问 Home Assistant 主机的局域网 IP 和 Socket B 监听端口。
3. 同一个 TCP 监听端口只能由一个程序占用；安装本集成前应停止旧的独立 AirProce 桥接脚本或服务。
4. 必须能登录净化器的 USR 管理网页并手动配置 Socket B。

**不需要 MQTT。**

## 安装

### 使用 HACS 自定义仓库

1. 打开 HACS。
2. 添加以下自定义仓库，类别选择 **Integration**：

```text
https://github.com/Griddz/home-assistant-airproce-bridge
```

3. 安装 **AirProce**。
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
AirProce
```

配置页面已经简化。正常使用时，主页面只需要填写：

- 设备名称
- 净化器型号
- USR 模块 IP 地址
- Socket B 监听端口

折叠的 **高级设置** 中才包含：

- 稳定设备 ID
- USR 网页端口
- USR 用户名和密码
- 是否验证 USR 登录
- Socket B 监听地址
- 看门狗时间参数

首次添加时“稳定设备 ID”可以留空，集成会根据 USR IP 自动生成并保存。建立后建议不要再修改，以保持 Home Assistant 中的设备和实体 ID 稳定。

### 配置 Socket B

请在 USR 网页中手动将 Socket B 设置为：

```text
协议：TCP-Client
服务器地址：<Home Assistant 局域网 IP>
端口：<AirProce 集成中设置的监听端口，第一台默认 9001>
```

Socket A 保持官方设置，例如：

```text
协议：TCP-Client
服务器地址：d2.airproce.com
端口：8800
```

Home Assistant 中填写的 USR 登录信息只用于验证管理网页是否可访问、用户名和密码是否正确。本集成不会自动修改 USR 网页中的参数。

## 第二台及更多净化器

每台净化器添加一个独立的 AirProce 配置项。以下三项必须不同：

| 配置项 | 第一台示例 | 第二台示例 |
|---|---|---|
| 稳定设备 ID | `airproce_ai600_bedroom` | `airproce_ai300_livingroom` |
| USR 模块 IP | `192.168.1.112` | `192.168.1.113` |
| Socket B 监听端口 | `9001` | `9002` |

多台设备可以共用：

- 同一个 Home Assistant 局域网 IP
- 相同的 USR 默认用户名和密码
- 相同的看门狗参数

第二台净化器的 Socket B 设置为：

```text
协议：TCP-Client
服务器地址：<同一个 Home Assistant 局域网 IP>
端口：9002
```

配置界面会检查监听端口；如果另一台 AirProce 已经使用该端口，会直接提示冲突，不必等到集成加载失败后才发现。

## 控制和状态反馈

- 净化器真实手动风速为 1～6 档。
- Home Assistant 原生 Fan 按规范使用 6 个百分比档位控制这些硬件速度。
- `auto` 和 `sleep` 作为 Fan 的预设模式。
- 设置手动风速时会退出预设模式。
- 自动和睡眠命令的第一个控制字节仍使用最近有效的风速上下文，保留此前实测确认的协议特征。
- 下发控制后，集成等待命令 ACK，随后立即发送状态查询，并以净化器返回的真实状态更新 Home Assistant，而不是乐观更新。

## 看门狗与可用性

净化器正常情况下大约每 15 秒主动上报一次状态。默认看门狗在连续 45 秒没有收到有效状态帧后主动查询；查询失败会再重试一次。如果仍没有有效回复，集成会关闭疑似假连接的 Socket B 会话。

Socket B 断开后，原生 Fan 和 Sensor 会显示“不可用”。USR 模块重新连入后，集成会自动请求一次最新状态。

## 从 0.1.x 版本升级

0.1.x 内部使用 MQTT Bridge + MQTT Discovery。0.2.0 起彻底改成原生 Home Assistant 实体，AirProce 本身不再需要 MQTT。

升级时集成会：

- 从 AirProce 配置项中移除旧 MQTT 参数
- 如果 Home Assistant 当时仍有 MQTT 发布服务，尝试清除旧的 AirProce retained Discovery Topic
- 清理对应的旧 MQTT 实体注册记录
- 尽量保留原来的 `device_id` 和实体 ID

如果升级后仍偶尔看到旧 MQTT AirProce 实体，确认旧 v0.1 桥接程序已经停止后再重启一次 Home Assistant。若 retained Discovery 存在于一个 Home Assistant 已经无法访问的 Broker 上，则需要在该 Broker 上单独清理。

升级完成后，AirProce 不再需要 MQTT；家中其他 Zigbee2MQTT、ESPHome 或设备如果仍使用 MQTT，当然可以继续保留 MQTT 集成。

## 从独立 Python 脚本迁移

1. 停止旧 Python 脚本或 systemd 服务。
2. 确认 Home Assistant 主机上的 `9001` 等监听端口没有被其他程序占用。
3. 安装并配置 AirProce。
4. 将 USR Socket B 的服务器地址改为 Home Assistant 主机局域网 IP。
5. 确认 Fan 和四个 Sensor 能够及时更新。

不需要再配置 MQTT。

## 隐私和安全

仓库不包含私人局域网 IP、MAC 地址、实际用户名和密码、房间名称或用户专属路径。USR 登录信息保存在 Home Assistant Config Entry 中，并会在诊断信息中隐藏。

发布 Home Assistant 配置导出或诊断文件前，仍应自行检查其中是否包含敏感信息。

## 已知限制

- 不同 USR 模块和固件的网页提交接口可能不同，因此本版本不会自动修改 Socket B 参数。
- 控制帧通过逆向分析获得，目前已在 AirProce AI-300 和 AI-600 上验证。
- Home Assistant 原生 Fan 使用百分比表达离散风速；真实硬件档位可通过 `hardware_speed` 属性查看。

## 代码生成说明

本仓库中的全部代码均由 **ChatGPT 5.6** 生成。

## License

MIT
