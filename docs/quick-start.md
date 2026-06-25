# WiFi v1 快速开始

## 1. 安装依赖

```bash
cd Open-AutoGLM
pip install -r requirements.txt
pip install -e .

cd ..\server
pip install -r requirements.txt
```

## 2. 配置环境变量

复制：

```text
server/.env.example → server/.env
```

填写：

```text
BIGMODEL_API_KEY=你的智谱APIKey
AUTOGLM_WORK_ROOT=你的项目路径
ADB_PATH=你的adb.exe路径
```

## 3. 启动后端

```cmd
server\start_server.bat
```

保持窗口开启。

## 4. WiFi 连接手机

首次通常需 USB 开启 TCP：

```cmd
adb tcpip 5555
```

同一 WiFi 下：

```cmd
set PHONE_IP=192.168.x.x
server\connect_phone_wifi.bat
```

确认 `adb devices` 显示 `phone_ip:5555    device`。

## 5. 配置 App

地址填：

```text
http://电脑局域网IP:8000
```

**不要用 `127.0.0.1`**。连接测试通过后即可执行任务。
