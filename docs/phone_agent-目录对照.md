# phone_agent 目录对照（对齐 Open-AutoGLM 官方结构）

> 官方仓库：[zai-org/Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM)  
> 本系列三个版本共用同一套 `Open-AutoGLM/phone_agent/` 内核，未重写 Agent 核心。

---

## 1. 官方标准结构（作业要求）

Open-AutoGLM README 中的 `phone_agent/` 结构：

```text
phone_agent/
├── __init__.py          # 包导出
├── agent.py             # PhoneAgent 主类（Observe → Think → Act 循环）
├── adb/                 # ADB 工具
│   ├── connection.py    # 远程/本地连接管理
│   ├── screenshot.py    # 屏幕截图
│   ├── input.py         # 文本输入 (ADB Keyboard)
│   └── device.py        # 设备控制 (点击、滑动等)
├── actions/             # 操作处理
│   └── handler.py       # 操作执行器（Launch / Tap / Type / Swipe ...）
├── config/              # 配置
│   ├── apps.py          # 支持的应用映射
│   ├── prompts_zh.py    # 中文系统提示词
│   └── prompts_en.py    # 英文系统提示词
└── model/               # AI 模型客户端
    └── client.py        # OpenAI 兼容客户端（智谱 autoglm-phone）
```

**官方 Agent 一步怎么走：**

```text
截图 (adb/screenshot.py)
  → 调 VLM (model/client.py)
  → 解析动作 (actions/handler.py)
  → ADB 执行 (adb/device.py, adb/input.py)
  → 循环直到 finish
```

---

## 2. 本项目的目录位置

```text
Open-AutoGLM/
├── main.py                 # CLI 入口
└── phone_agent/            # ← 官方结构

server/main.py              # FastAPI 封装（你做的）
mobile-app/App.tsx          # Android App（你做的）
```

---

## 3. 官方结构 vs 本项目实际文件

| 官方模块 | 本项目路径 | 作用 |
| --- | --- | --- |
| `agent.py` | `Open-AutoGLM/phone_agent/agent.py` | Agent 主循环 |
| `adb/connection.py` | 同路径 | WiFi 远程 `adb connect` |
| `adb/screenshot.py` | 同路径 | 屏幕截图 |
| `actions/handler.py` | 同路径 | 动作执行 |
| `config/apps.py` | 同路径 | App 映射 |
| `model/client.py` | 同路径 | 智谱 API |

**额外扩展：** `adb/ui_tree.py`、`device_factory.py`

---

## 4. 三层调用关系

```text
mobile-app/ → server/main.py → Open-AutoGLM/main.py → phone_agent/ → ADB → 手机
```

系列总览 → [USB 主仓库 SERIES.md](https://github.com/ginny-pjj/USB-Autoglm-Mobile-Copilot/blob/main/SERIES.md)
