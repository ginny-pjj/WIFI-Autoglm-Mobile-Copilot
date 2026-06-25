# AutoGLM Mobile Copilot WiFi v1

> A local WiFi debugging version of AutoGLM Mobile Copilot based on [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM). This version runs the backend on a Windows PC, connects to a real Android phone through wireless ADB on the same WiFi, and lets the mobile App send tasks to the local FastAPI service over LAN.

## 1. Project Positioning

This is the **local WiFi debugging first version** of AutoGLM Mobile Copilot.

This repository focuses on **same-WiFi local deployment**. It does not include cloud server deployment, Docker, or Tailscale-based remote ADB. It is intended to be a simpler course-project version than the cloud edition, while still demonstrating real-phone automation without a permanent USB cable.

Value of WiFi v1:

- Runs a complete real Android phone control loop through wireless ADB.
- Verifies the App -> FastAPI -> Open-AutoGLM -> ADB -> phone pipeline in a local setting.
- Serves as the intermediate version between a USB prototype and a cloud remote-control version.

## 2. Project Background

Open-AutoGLM officially supports remote debugging through `adb connect phone_ip:5555`. This project wraps that official capability with:

1. A local FastAPI service layer.
2. A mobile control App.
3. Structured Agent trace display.
4. Simple local WiFi connection scripts.

Unlike the USB version, this project does **not** rely on `adb reverse`. The mobile App directly accesses the PC through a LAN address.

## 3. Core Features

| Feature | Description |
| --- | --- |
| Mobile App control panel | Enter tasks, configure LAN base URL, choose Mock/Real, view Trace |
| FastAPI task service | Provides `/health`, `/devices`, `/tasks`, `/tasks/{id}/trace` |
| Open-AutoGLM integration | Calls `Open-AutoGLM/main.py` through subprocess |
| WiFi ADB control | Controls a real Android phone through `adb connect phone_ip:5555` |
| Structured Trace | Displays Observe / Think / Action / Result |
| Mock / Real modes | Mock for UI debugging, Real for actual agent execution |

## 4. System Architecture

```text
Android App
  task input / trace display
        -> http://PC_LAN_IP:8000
Windows PC FastAPI Server
        -> subprocess
Open-AutoGLM PhoneAgent
        -> WiFi ADB
Real Android Phone
```

Suggested screenshots / diagrams:

```text
assets/architecture-wifi.png
assets/app-home-wifi.png
assets/wifi-demo-result.png
```

## 5. Project Structure

```text
autoglm-mobile-copilot-wifi-v1/
├── README.md
├── NOTICE.md
├── .gitignore
├── ADBKeyboard.apk
├── Open-AutoGLM/              # Official Phone Agent code + local integration patches
├── server/                    # FastAPI service layer
│   ├── main.py
│   ├── requirements.txt
│   ├── start_server.bat
│   ├── connect_phone_wifi.bat
│   ├── connect_phone.bat
│   └── .env.example
├── mobile-app/                # Mobile control App
├── docs/
│   ├── architecture.md
│   ├── demo-script.md
│   ├── quick-start.md
│   ├── faq.md
│   └── vibe-coding-log.md
├── assets/                    # Diagrams and screenshots
├── demo/                      # Demo video files
├── dist/                      # APK output placeholder
└── releases/                  # Release attachment placeholder
```

## 6. Execution Logic

```text
App POST /tasks
  -> local FastAPI service receives the task through LAN
  -> server/main.py creates a task record
  -> checks BIGMODEL_API_KEY, Open-AutoGLM path, and wireless ADB device
  -> optional prepare_device: wake, unlock, return to desktop
  -> starts Open-AutoGLM/main.py through subprocess
  -> PhoneAgent.run(task)
      -> captures the current phone screen
      -> calls the VLM to understand the page and decide actions
      -> executes Launch / Tap / Type / Swipe through handler.py
      -> captures the next screen for the following loop
  -> server cleans raw logs into structured Trace
  -> App polls task status and displays progress + result
```

One-sentence summary:

> WiFi v1 keeps the PC as the local Agent backend, controls the phone through wireless ADB, and lets the mobile App access the local service using the PC's LAN address.

## 7. Runtime Requirements

| Requirement | Description |
| --- | --- |
| Windows PC | Runs the local FastAPI backend |
| PowerShell / CMD | Keep `start_server.bat` running |
| Python environment | Used for backend and Open-AutoGLM |
| Android phone | Enable Developer options and Wireless debugging |
| Same WiFi network | PC and phone must be on the same LAN |
| ADB / platform-tools | Used for `adb connect`, input, tap, and control |
| BigModel API Key | Required for `autoglm-phone` inference |
| ADB Keyboard | Recommended for stable text input |

WiFi v1 **does not require a cloud server, Docker, or Tailscale**.

## 8. Quick Start

### 8.1 Configure environment variables

Copy:

```text
server/.env.example -> server/.env
```

Fill in:

```text
BIGMODEL_API_KEY=your_bigmodel_api_key
AUTOGLM_WORK_ROOT=C:/Users/YourName/Desktop/autoglm-mobile-copilot-wifi-v1
ADB_PATH=C:/Android/platform-tools/adb.exe
```

### 8.2 Start the local backend

```cmd
server\start_server.bat
```

Keep that terminal window open.

### 8.3 Connect the phone over WiFi

Usually you need USB once to switch ADB into TCP mode:

```cmd
adb tcpip 5555
```

Then disconnect USB and run:

```cmd
set PHONE_IP=192.168.x.x
server\connect_phone_wifi.bat
```

Or connect manually:

```cmd
adb connect 192.168.1.100:5555
adb devices
```

### 8.4 Configure the mobile App

Set the App base URL to:

```text
http://PC_LAN_IP:8000
```

Important: **do not use `127.0.0.1`** in WiFi mode.

Then tap `Connect Test`, choose `Real`, and run tasks.

## 9. Recommended Demo Tasks

```text
Open Settings and view WLAN
Open Browser and search Open-AutoGLM
Open Meituan and search Mixue Bingcheng
```

Start with `Open Settings and view WLAN` for the highest success rate. Then move on to Meituan. More complex apps like Xiaohongshu can be demonstrated later.

## 10. Demo Video and Screenshots

Suggested files:

```text
demo/demo_wifi_v1.mp4
assets/architecture-wifi.png
assets/app-home-wifi.png
assets/trace-view-wifi.png
assets/wifi-result.png
```

If the video is large, upload it to GitHub Release or cloud storage and place the link in this README instead of committing raw video into repository history.

## 11. Improvements in This Version

- Wrapped Open-AutoGLM CLI as a FastAPI service.
- Mobile App can submit tasks and view status / trace.
- Supports Mock / Real modes for easier debugging.
- Removes the need for permanent USB connection.
- Keeps the full App + FastAPI + Open-AutoGLM integration chain in a local environment.

## 12. Future Upgrade Direction

WiFi v1 can be upgraded to a cloud version by:

- Moving the backend from the local PC to a cloud server.
- Replacing same-LAN WiFi ADB with Tailscale + remote ADB.
- Deploying with Docker.
- Removing the need to keep the PC always online.
- Adding more handling for remote screenshot delay, keyboard checks, and takeover behavior.

The corresponding final project can be maintained separately as `autoglm-mobile-copilot-cloud`.

## 13. Acknowledgement

This project is based on [zai-org/Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM) and adapts it into a local wireless debugging workflow. Please follow the upstream license and attribution requirements.

Do not commit real API keys or videos containing private information.
