# Vibe Coding 开发记录

## 项目目标

基于 Open-AutoGLM，用 Vibe Coding 方式快速实现一个可在安卓手机运行的 Phone Agent 控制 App。

## Day 1：环境与真机链路

### 完成内容

1. 安装 ADB（platform-tools）到 D 盘
2. Android 手机开启开发者模式、USB 调试、传输文件模式
3. 安装并启用 ADB Keyboard
4. Clone Open-AutoGLM，创建 Python 虚拟环境
5. 配置智谱 BigModel `autoglm-phone` API
6. 命令行成功执行：`打开设置查看WLAN`

### 关键问题

- C 盘空间不足 → 项目迁移到 `D:\autoglm-mobile-work`
- Windows CMD 中文编码 → `chcp 65001` + `PYTHONUTF8=1`
- API Key 不写入代码 → 使用 `.env` 管理

## Day 2：后端 + 移动端 + 打包

### 后端（FastAPI）

- `/health` `/devices` `/tasks` 任务系统
- Mock / Real 双模式
- 后台线程执行 Open-AutoGLM
- 日志轮询与状态管理

### 移动端（Expo / React Native）

- 后端地址配置
- 连接测试
- 任务输入 + 模式切换
- 技能模板
- Agent 日志展示

### Android 打包

- 安装 Android Studio + SDK（D:\AndroidSdk）
- `expo prebuild` 生成原生工程
- 修复 NDK 不完整、Gradle 中文路径问题
- Debug APK 红屏 → 改打 Release APK
- CLEARTEXT HTTP 被拦截 → 添加 `network_security_config.xml`

### 联调

- 手机开热点时无法访问电脑 → 使用 USB + `adb reverse`
- Windows 防火墙拦截 → 放行 8000 端口
- 最终 App 连接成功

## AI 辅助方式

| 环节 | AI 作用 |
|------|---------|
| 需求拆解 | 分析 JD 与作业要求，确定 App + 后端架构 |
| 环境排查 | ADB、编码、NDK、防火墙问题定位 |
| 代码生成 | FastAPI 接口、Expo UI、Gradle 配置 |
| 迭代修复 | APK 红屏、HTTP 明文、连接失败 |
| 文档整理 | README、演示脚本、面试问答 |

## 交付物

- [x] APK：`dist/AutoGLM-Mobile-Copilot.apk`
- [x] 后端代码：`server/`
- [x] 移动端代码：`mobile-app/`
- [x] README
- [x] Vibe Coding 记录
- [ ] 演示视频（待录制）

## 面试可讲亮点

1. 把命令行 Phone Agent 产品化为移动端控制台
2. 模型推理 + ADB 控制放后端，移动端负责交互与可观测性
3. Mock / Real 双模式，保证 Demo 稳定性
4. 完整解决 Android 工程化问题（打包、网络安全、USB 转发）
