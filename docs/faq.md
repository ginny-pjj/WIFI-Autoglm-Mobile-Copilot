# WiFi v1 FAQ

## 1. 和云端版有什么区别？

WiFi v1 在本地 Windows 跑后端，手机通过同 WiFi 无线 ADB 连接。云端版后端在远程服务器，通常用 Tailscale + 远程 ADB。

## 2. 电脑必须一直开着吗？

必须。`start_server.bat` 窗口不能关。

## 3. 需要云服务器吗？

不需要。这是纯本地部署。

## 4. App 为什么不能用 `http://127.0.0.1:8000`？

WiFi 版没有 `adb reverse`。127.0.0.1 是手机自己，必须填电脑的局域网 IP，如 `http://192.168.1.10:8000`。

## 5. REAL 模式显示无设备怎么办？

检查：

1. 手机和电脑是否同一 WiFi
2. 是否开启无线调试
3. `adb connect 手机IP:5555` 是否成功
4. `adb devices` 是否显示 `device`
5. 后端是否已启动

## 6. API Key 能提交 GitHub 吗？

不能。只提交 `.env.example`，真实 `server/.env` 必须在 `.gitignore` 里。

## 7. ADB Keyboard 必须装吗？

建议安装并启用，中文输入更稳定。

## 8. 本版本的验收标准是什么？

跑通：App → FastAPI → Open-AutoGLM → WiFi ADB → 真实手机的完整闭环。
