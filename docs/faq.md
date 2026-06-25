# WiFi v1 FAQ

## 1. What is the difference between this project and the cloud version?

WiFi v1 runs entirely on a local Windows PC and controls the phone through wireless ADB on the same WiFi network. The cloud version runs the backend on a remote server and typically uses Tailscale plus remote ADB to reach the phone.

## 2. Does the PC need to stay on?

Yes. This version depends on the local FastAPI backend running on your PC, so the terminal running `server/start_server.bat` must stay open during execution.

## 3. Do I need a cloud server?

No. WiFi v1 is a local deployment version and does not require a cloud server.

## 4. Why should the App not use `http://127.0.0.1:8000`?

Because WiFi v1 does not use `adb reverse`. The phone must access the PC through the PC's LAN IP, for example `http://192.168.x.x:8000`.

## 5. What if REAL mode shows no device?

Check the following:

1. The phone and the PC are on the same WiFi.
2. Wireless debugging is enabled on the phone.
3. `adb connect phone_ip:5555` succeeds.
4. `adb devices` shows `phone_ip:5555    device`.
5. The backend is running before you tap `Connect Test`.

## 6. Can I commit the API key to GitHub?

No. Only commit `.env.example`. The real `server/.env` file must stay ignored by Git.

## 7. Is ADB Keyboard required?

It is not strictly required for every simple task, but it is strongly recommended for stable text input, especially for Chinese text and search tasks.

## 8. What is the main validation target of this version?

The baseline goal of WiFi v1 is to prove that the full local pipeline works:

App -> FastAPI -> Open-AutoGLM -> WiFi ADB -> real Android phone
