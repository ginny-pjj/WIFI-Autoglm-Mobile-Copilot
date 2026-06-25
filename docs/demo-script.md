# WiFi v1 Demo Script

## 1. Demo Goal

Show that a Windows local backend can control a real Android phone through wireless ADB, while the mobile App communicates with the local FastAPI service over LAN and runs Real-mode tasks.

Recommended task:
```text
Open Settings and view WLAN
```

Also suitable:

```text
Open Meituan and search Mixue Bingcheng
```

## 2. Demo Preparation
1. Python dependencies are installed on the Windows PC.
2. Developer options and Wireless debugging are enabled on the phone.
3. The phone and PC are on the same WiFi.
4. Run `server/start_server.bat` and keep the backend running.
5. Run `server/connect_phone_wifi.bat` and confirm `adb devices` shows `phone_ip:5555 device`.
6. Set the App base URL to `http://PC_LAN_IP:8000`.

## 3. Recording Suggestion

Recommended file name:

```text
demo/demo_wifi_v1.mp4
```

Suggested recording content:
1. Backend terminal is running.
2. `adb connect phone_ip:5555` succeeds.
3. Task is entered in the App.
4. Connect Test succeeds.
5. Real mode is selected.
6. The real phone is automatically operated.
7. App Trace and final result are shown.

## 4. Defense / Presentation Order

### One-sentence positioning

This is the local wireless debugging version of the project. The PC runs the backend, the real Android phone is controlled through wireless ADB on the same WiFi, and the mobile App displays the full task execution process.

### Architecture summary

```text
App -> LAN FastAPI -> Open-AutoGLM PhoneAgent -> WiFi ADB -> Android phone
```

### Key highlights

- No cloud server is required.
- No permanent USB cable is required.
- Keeps the full App + FastAPI + Open-AutoGLM pipeline.
- Trace makes the Agent's observation, reasoning, and action visible.

## 5. Video Description Text

> This video demonstrates AutoGLM Mobile Copilot WiFi v1. The Windows PC runs a local FastAPI backend, the Android phone is connected through wireless ADB on the same WiFi, and the mobile App sends tasks to the local service and displays the execution trace in Real mode.
