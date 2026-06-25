# WiFi v1 演示脚本

## 1. 演示目标

展示 Windows 本地后端通过无线 ADB 控制真实 Android 手机，App 经局域网访问 FastAPI 并执行 Real 模式任务。

推荐任务：

```text
打开设置查看WLAN
```

也可演示：

```text
打开美团搜索蜜雪冰城
```

## 2. 演示前准备

1. 电脑已安装 Python 依赖
2. 手机开启开发者选项和无线调试
3. 手机与电脑同一 WiFi
4. 运行 `server/start_server.bat`
5. 运行 `server/connect_phone_wifi.bat`，确认 `adb devices` 有设备
6. App 填 `http://电脑局域网IP:8000`

## 3. 录屏建议

文件名：`demo/demo_wifi_v1.mp4`

画面包含：后端运行 → adb connect 成功 → App 发任务 → 真实手机操作 → Trace 与结果。

## 4. 答辩讲解顺序

### 一句话

本地无线调试版：电脑跑后端，同 WiFi 下无线 ADB 控手机，App 展示完整执行过程。

### 架构

```text
App → 局域网 FastAPI → Open-AutoGLM PhoneAgent → WiFi ADB → Android 手机
```

### 亮点

- 对应官方远程调试能力
- 无需云服务器、无需一直插 USB
- 完整 App + FastAPI + Open-AutoGLM 链路
- Trace 可视化 Agent 观察、思考、动作

## 5. 视频说明文字

> 本视频展示 AutoGLM Mobile Copilot WiFi v1。Windows 电脑运行 FastAPI 后端，Android 手机通过同 WiFi 无线 ADB 连接，App 向本地服务发任务并在 Real 模式下展示 Agent Trace。
