# WiFi v1 Architecture and Execution Logic

## 1. Overall Call Chain
```text
Mobile App
  -> http://PC_LAN_IP:8000
  -> Windows local FastAPI Server
  -> Open-AutoGLM main.py
  -> PhoneAgent.run(task)
  -> Screenshot / Model Decision / WiFi ADB Action
  -> Real Android Phone
```

The core of WiFi v1 is: the PC runs the backend, the phone and PC stay on the same WiFi, the phone is connected by `adb connect phone_ip:5555`, and the mobile App accesses the local backend through the PC's LAN address.

## 2. Layer Description

| Layer | Location | Purpose |
| --- | --- | --- |
| Mobile side | `mobile-app/App.tsx` | Input task, configure `http://PC_LAN_IP:8000`, display status and Trace |
| Local API | `server/main.py` | Provides task APIs, manages task state, invokes Open-AutoGLM |
| Startup script | `server/start_server.bat` | Starts the local FastAPI service |
| WiFi helper script | `server/connect_phone_wifi.bat` | Checks wireless ADB and prints App base URL |
| Agent entry | `Open-AutoGLM/main.py` | Checks device, keyboard, model API, then starts PhoneAgent |
| Agent loop | `Open-AutoGLM/phone_agent/agent.py` | Observe -> Think -> Act multi-step loop |
| Action execution | `Open-AutoGLM/phone_agent/actions/handler.py` | Executes Launch, Tap, Type, Swipe, Back, Home |
| Device control | `Open-AutoGLM/phone_agent/adb/` | Screenshot, input, tapping, swiping, WiFi ADB connection |

## 3. Real Mode Flow

```text
POST /tasks { task, mode: real }
  -> App sends request to local backend over LAN
  -> Check API key, Python, Open-AutoGLM, wireless ADB device
  -> Optionally wake / unlock / return phone to desktop
  -> Start Open-AutoGLM subprocess
  -> Agent captures current phone screen
  -> VLM understands screen and outputs action
  -> handler executes action through WiFi ADB
  -> Capture next screen to verify result
  -> Finish or timeout and return final task state
```

## 4. WiFi v1 Runtime Requirements

| Requirement | Description |
| --- | --- |
| Windows PC | Runs the local backend |
| PowerShell / CMD | Keep `start_server.bat` open |
| Same WiFi | PC and phone must be on the same LAN |
| Phone wireless debugging | Allow ADB control over network |
| ADB / platform-tools | Used for `adb connect`, tapping, typing, and screenshot |
| BigModel API Key | Required for model inference |

## 5. Difference from the Cloud Version

| Item | WiFi v1 |
| --- | --- |
| Backend location | Local PC |
| Phone connection | WiFi ADB |
| App base URL | `http://PC_LAN_IP:8000` |
| Cloud server required | No |
| Tailscale required | No |
| PC must stay on | Yes |

## 6. One-line Demo Explanation

> WiFi v1 is the local wireless debugging stage of the project: the PC runs the Agent backend, the phone is controlled through wireless ADB on the same WiFi, and the mobile App visualizes the full execution process.
