# WiFi v1 Quick Start

## 1. Install Dependencies

```bash
cd Open-AutoGLM
pip install -r requirements.txt
pip install -e .

cd ..\server
pip install -r requirements.txt
```

## 2. Configure Environment Variables

Copy:

```text
server/.env.example -> server/.env
```

Fill in:

```text
BIGMODEL_API_KEY=your_bigmodel_api_key
AUTOGLM_WORK_ROOT=your_project_path
ADB_PATH=your_adb_exe_path
```

## 3. Start the Backend

```cmd
server\start_server.bat
```

## 4. Connect the Phone over WiFi

Usually you need USB once to enable ADB over TCP:

```cmd
adb tcpip 5555
```

Then, under the same WiFi:

```cmd
set PHONE_IP=192.168.x.x
server\connect_phone_wifi.bat
```

## 5. Configure the Mobile App

Set the App base URL to:

```text
http://PC_LAN_IP:8000
```

Tap `Connect Test`, then run tasks.
