# AutoGLM Mobile Copilot WiFi v1

> 基于 [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM) 的手机 AI Agent **WiFi 无线调试版**。  
> Windows 电脑跑 FastAPI 后端，手机与电脑在同一 WiFi 下通过无线 ADB 连接，App 用电脑局域网 IP 访问后端。

**📌 给面试官：** 本仓库对应官方 README 中的「远程调试 / WiFi ADB」能力。  
**📖 系列总览：** [USB 主仓库 SERIES.md](https://github.com/ginny-pjj/USB-Autoglm-Mobile-Copilot/blob/main/SERIES.md)  
**📖 本仓库：** [作业对照与面试官导读](docs/作业对照与面试官导读.md) · [phone_agent 目录对照](docs/phone_agent-目录对照.md) · [快速开始](docs/quick-start.md)

---

## 系列项目一览

| 版本 | GitHub 仓库 | 部署方式 | 定位 |
| --- | --- | --- | --- |
| USB v1（主入口） | [USB-Autoglm-Mobile-Copilot](https://github.com/ginny-pjj/USB-Autoglm-Mobile-Copilot) | USB 线 + 电脑本地后端 | ✅ 作业主交付 |
| **WiFi v1（本仓库）** | [WIFI-Autoglm-Mobile-Copilot](https://github.com/ginny-pjj/WIFI-Autoglm-Mobile-Copilot) | 同 WiFi 无线 ADB | ✅ 官方「远程调试」 |
| Cloud | [CLOUD-Autoglm-Mobile-Copilot](https://github.com/ginny-pjj/CLOUD-Autoglm-Mobile-Copilot) | 云 Docker + Tailscale | ⭐ 工程进阶 |

---

## 1. 项目定位

这是 **AutoGLM Mobile Copilot 的 WiFi 无线调试版**。

与 USB 版的核心区别：

- **不用** `adb reverse`，App 填电脑的 **局域网 IP**（如 `http://192.168.1.10:8000`）
- **不用** 一直插 USB 线，手机通过 `adb connect 手机IP:5555` 无线连接
- 仍在本机 Windows 跑后端，**不需要云服务器、Docker、Tailscale**

适合展示：官方文档里的 WiFi 远程 ADB 能力 + 你自己的 App / FastAPI 工程封装。

## 2. 项目背景

[Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM) 官方支持通过 `adb connect 手机IP:5555` 做无线调试。本项目在此基础上做了产品化封装：

1. Windows 电脑运行 FastAPI 后端
2. 手机与电脑在同一 WiFi，无线 ADB 连接
3. Android App 作为任务入口，展示结构化 Trace
4. 提供 `connect_phone_wifi.bat` 一键连接脚本

## 3. 核心功能

| 功能 | 说明 |
| --- | --- |
| 手机 App 控制端 | 输入任务、配置局域网地址、选择 Mock/Real、查看 Trace |
| FastAPI 任务服务 | 提供 `/health`、`/devices`、`/tasks`、`/tasks/{id}/trace` |
| Open-AutoGLM 集成 | 后端 subprocess 调用 `Open-AutoGLM/main.py` |
| WiFi ADB 控制 | 通过 `adb connect 手机IP:5555` 控制真实 Android 手机 |
| 结构化 Trace | 展示 Observe / Think / Action / Result |
| Mock / Real 双模式 | Mock 用于 UI 联调；Real 调用真实 Agent |

## 4. 系统架构

```text
Android App
  输入任务 / 展示 Trace
        ↓ http://电脑局域网IP:8000
Windows PC FastAPI Server
        ↓ subprocess
Open-AutoGLM PhoneAgent
        ↓ WiFi ADB (adb connect)
真实 Android 手机
```

建议补充截图：

```text
assets/architecture-wifi.png
assets/app-home-wifi.png
assets/wifi-demo-result.png
```

## 5. 项目结构

```text
autoglm-mobile-copilot-wifi-v1/
├── README.md
├── NOTICE.md
├── .gitignore
├── ADBKeyboard.apk
├── Open-AutoGLM/              # 官方 Phone Agent + 本项目补丁
├── server/
│   ├── main.py
│   ├── start_server.bat
│   ├── connect_phone_wifi.bat # WiFi 连接主脚本
│   ├── connect_phone.bat      # 首次 USB 开 tcpip 5555 时用
│   └── .env.example
├── mobile-app/
├── docs/
│   ├── 作业对照与面试官导读.md
│   ├── architecture.md
│   ├── quick-start.md
│   ├── demo-script.md
│   └── faq.md
├── assets/
├── demo/
└── dist/
```

## 6. 实现逻辑

```text
App POST /tasks
  → 通过局域网访问电脑 FastAPI
  → server/main.py 创建任务
  → 检查 API Key、Open-AutoGLM、无线 ADB 设备
  → 可选 prepare_device：唤醒、解锁、回桌面
  → subprocess 启动 Open-AutoGLM/main.py
  → PhoneAgent.run(task)：截图 → VLM 决策 → ADB 执行 → 循环
  → server 清洗日志为结构化 Trace
  → App 轮询展示结果
```

一句话：

> WiFi v1 让电脑作为 Agent 后端，通过无线 ADB 控制手机，App 用电脑局域网 IP 访问本地服务。

## 7. 运行条件

| 条件 | 说明 |
| --- | --- |
| Windows 电脑 | 必须运行 FastAPI 后端 |
| PowerShell / CMD | 保持 `start_server.bat` 窗口开启 |
| 同一 WiFi | 手机和电脑必须在同一局域网 |
| 手机无线调试 | 开启开发者选项 + 无线调试 |
| ADB / platform-tools | `adb connect`、`adb devices` 等 |
| 智谱 API Key | 调用 `autoglm-phone` |
| ADB Keyboard | 建议安装，提升中文输入稳定性 |

**不需要** 云服务器、Docker、Tailscale。

## 8. 快速开始

### 8.1 配置环境变量

```text
server/.env.example → server/.env
```

填写：

```text
BIGMODEL_API_KEY=你的智谱APIKey
AUTOGLM_WORK_ROOT=你的项目路径
ADB_PATH=你的adb.exe路径
```

### 8.2 启动本地后端

```cmd
server\start_server.bat
```

保持窗口不要关闭。

### 8.3 连接手机（WiFi ADB）

首次通常需要 USB 一次，开启 TCP 模式：

```cmd
adb tcpip 5555
```

拔掉 USB 后，在同一 WiFi 下：

```cmd
set PHONE_IP=192.168.x.x
server\connect_phone_wifi.bat
```

或手动：

```cmd
adb connect 192.168.1.100:5555
adb devices
```

### 8.4 App 配置

**重要：WiFi 模式不要用 `127.0.0.1`**

```text
http://电脑局域网IP:8000
```

例如 `http://192.168.1.10:8000`，然后连接测试 → 选 Real → 执行任务。

## 9. 与 USB 版的区别

| 对比项 | USB v1 | WiFi v1（本仓库） |
| --- | --- | --- |
| 手机连接 | USB 数据线 | 无线 ADB |
| App 地址 | `http://127.0.0.1:8000` | `http://电脑IP:8000` |
| 是否需要 adb reverse | 需要 | 不需要 |
| 是否需要一直插线 | 需要 | 不需要 |
| 对应官方文档 | USB 部署 | 远程调试 / WiFi ADB |

## 10. 推荐演示任务

```text
打开设置查看WLAN
打开浏览器搜索 Open-AutoGLM
打开美团搜索蜜雪冰城
```

建议先从「打开设置查看 WLAN」开始，成功率高。

## 11. Demo Video（演示视频）

本项目包含真实设备任务执行的录屏演示，视频托管在 **GitHub Releases**。

- **WiFi v1 Demo：** [观看 / 下载演示视频](https://github.com/ginny-pjj/WIFI-Autoglm-Mobile-Copilot/releases)

视频内容包含：

- 本地后端启动
- 无线 ADB 连接（`adb connect`）
- 手机 App 提交任务（Real 模式）
- 真实 Android 手机自动操作
- Agent Trace 与最终结果

**全系列 Demo：** [USB 主仓库 SERIES.md](https://github.com/ginny-pjj/USB-Autoglm-Mobile-Copilot/blob/main/SERIES.md#demo-演示视频)

<!-- 上传 Release 后改为具体链接，例如：
- [WiFi v1 Demo](https://github.com/ginny-pjj/WIFI-Autoglm-Mobile-Copilot/releases/download/v1.0-demo/demo_wifi_v1.mp4)
-->

## 12. phone_agent 目录对照

→ **[docs/phone_agent-目录对照.md](docs/phone_agent-目录对照.md)**（对齐 [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM) 官方结构）

## 13. 对照 Open-AutoGLM 作业要求

| 官方要求 | 本仓库 |
| --- | --- |
| 远程调试：`adb connect IP:5555` | ✅ `connect_phone_wifi.bat` |
| phone_agent 内核 | ✅ [docs/phone_agent-目录对照.md](docs/phone_agent-目录对照.md) |
| 智谱 API + 自然语言控制 | ✅ |
| **扩展：App + FastAPI + Trace** | ✅ |

完整对照 → **[docs/作业对照与面试官导读.md](docs/作业对照与面试官导读.md)**

## 14. 致谢

基于 [zai-org/Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM) 工程封装。请遵守上游 License。

请勿提交真实 API Key 或含隐私的录屏。
