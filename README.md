# iPhone ADB 控制台（iPhone ADB Console）

在 **iPhone 的 Safari** 里打开一个网页，可视化地给开放了 **ADB over TCP/IP（默认 5555 端口）** 的 Android 设备**安装 APK、列出并卸载应用**。后端零第三方依赖，只需要 Python 3.8+ 和本机 `adb`。

```
[ iPhone Safari ]  --HTTP-->  [ 电脑 / 服务器: server.py ]  --adb connect IP:5555-->  [ Android 设备 ]
   只负责显示界面             真正执行 adb install / uninstall          手机 / 盒子 / 模拟器
```

## 先弄清一个前提

**ADB 是 Android 专用协议，iPhone 不支持 ADB，iOS Safari 也不支持 WebUSB。** 所以 iPhone 不能直连 5555 端口，必须由一台电脑（Mac / Windows / Linux 均可）运行 `server.py`，由它调用本机的 `adb` 去连设备；iPhone 只是通过浏览器操作这个界面。

如果你要管理的是 **iPhone 自身的应用**（安装/卸载 `.ipa`），那需要的是 `libimobiledevice` / `ideviceinstaller` / iDescriptor，与本项目无关。

## 快速开始

### 1. 让 Android 设备开放 5555

- **已 root 或曾 USB 连过电脑**（最经典）：USB 连上电脑，执行 `adb tcpip 5555`，然后拔掉数据线。之后设备就在 `<手机IP>:5555` 上监听。
- **部分电视盒子 / 模拟器 / 开发板**：出厂就默认监听 5555，直接用即可。
- **Android 11+ 原生「无线调试」**：端口是随机的并且需要先 `adb pair <IP>:<配对端口> <配对码>` 配对，之后才能 `adb connect <IP>:<调试端口>`。本工具目前只做 `connect`，请先用电脑完成配对，或改用上面的 `adb tcpip 5555` 方式。

> 手机和电脑必须在**同一个局域网**。记下设备 IP（如 `192.168.1.20`）。

### 2. 电脑上安装 adb 并启动服务

```bash
# macOS
brew install android-platform-tools

# Ubuntu / Debian
sudo apt install android-sdk-platform-tools

# Windows：从 https://developer.android.com/studio/releases/platform-tools 下载解压
```

```bash
git clone https://github.com/wanggood88/iphone-adb-console.git
cd iphone-adb-console
python3 server.py --token 换成你自己的口令
```

不需要 `pip install`，标准库就够了。启动后会打印：

```
iPhone Safari 打开：  http://192.168.1.8:8000
adb：                 /opt/homebrew/bin/adb
```

### 3. iPhone 打开

Safari 访问 `http://<电脑局域网IP>:8000`（**用 http，不要 https**），填入访问口令，然后：

1. 输入设备 IP 和端口（默认 5555），点「连接该设备」；
2. 在设备列表里点选一台设备作为当前设备；
3. 「安装应用」选 `.apk` → 安装；「卸载应用」搜索包名 → 卸载。

## 功能

| 功能 | 说明 |
| --- | --- |
| 连接 / 断开 | `adb connect IP:PORT`、`adb disconnect`，自动列出设备（型号、状态） |
| 安装 APK | iPhone 上选择 `.apk`，上传到电脑后执行 `adb install -r`（覆盖安装，最大 512 MB） |
| 应用列表 | `pm list packages`，支持「用户应用 / 全部 / 系统应用」与前端搜索 |
| 卸载应用 | `adb uninstall <包名>`，二次确认；也支持手动输入包名 |
| 访问口令 | `--token` 开启后，所有操作接口都要带口令，避免同 WiFi 下他人误操作 |
| 自定义 shell | 可选 `--allow-shell`，默认关闭 |
| 操作记录 | 每条操作都显示 adb 原始输出，便于排错 |

界面按 iPhone 做了适配：大触控区、安全区（刘海/底部）、深色模式、输入框 16px 防自动缩放，离线可用（无 CDN、无外部资源）。

## 启动参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--host` | `0.0.0.0` | 监听地址，保持默认 iPhone 才能访问 |
| `--port` | `8000` | 网页端口 |
| `--token` | 空 | 访问口令；也可用环境变量 `IADC_TOKEN` |
| `--adb` | 自动查找 | 指定 adb 路径；也可用环境变量 `ADB_PATH` |
| `--allow-shell` | 关闭 | 开启自定义 adb shell 命令 |
| `--verbose` | 关闭 | 打印访问日志与 adb 命令 |

查找顺序：`--adb` → `ADB_PATH` → `PATH` 里的 `adb`。

## HTTP 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/status` | 服务与 adb 状态（无需口令） |
| GET | `/api/devices` | 设备列表 |
| GET | `/api/packages?device=...&scope=user\|all\|system` | 应用包名列表 |
| POST | `/api/connect` | `{host, port}` 连接设备 |
| POST | `/api/disconnect` | `{device}` 断开 |
| POST | `/api/install` | APK 二进制；请求头 `X-Device`、`Content-Type: application/octet-stream` |
| POST | `/api/uninstall` | `{device, package}` |
| POST | `/api/shell` | `{device, command}`，需 `--allow-shell` |

启用口令后，除 `/api/status` 外的接口都需要请求头 `X-Access-Token: <口令>`。

## 安全须知（务必阅读）

- **ADB over TCP/IP 是明文且无认证的**：任何能连到设备 5555 端口的人，都能读取短信、安装软件、恢复出厂设置。请只在可信的家庭 / 办公 WiFi 使用。
- **不要把 8000 端口或设备的 5555 端口映射到公网**，不要配置端口转发、内网穿透或反向代理到公网。
- 用完请在开发者选项里**关闭无线调试 / USB 调试**，或执行 `adb usb` 切回 USB 模式。
- 建议始终设置 `--token`，并使用随机口令。
- 自定义 shell 默认关闭；开启后等同于把设备 shell 暴露给能访问网页的人。
- 卸载系统应用可能导致系统功能异常；`adb uninstall` 对纯系统应用通常无效，需要 `pm uninstall -k --user 0 <包名>`（可用 `--allow-shell` 执行，风险自负）。
- 服务端对所有用户输入做了正则白名单校验，且所有 adb 调用都使用参数数组、不使用 `shell=True`；但这不能替代网络层面的隔离。

## 常见问题

**iPhone 打不开页面？** 确认电脑和 iPhone 在同一 WiFi；电脑防火墙放行 8000；用 `http://` 而不是 `https://`；Windows 需在「专用网络」下允许 Python 通过防火墙。不要把本页放进 HTTPS 站点去调用本地 HTTP 服务，浏览器会拦截混合内容。

**连不上 5555？** 确认设备已开启 USB/无线调试并授权过；IP 是否变化；端口是否是 5555（Android 11+ 原生无线调试端口是随机的）；可先在电脑上手工执行 `adb connect IP:5555` 验证。

**提示「缺少 ADB」？** 电脑没装 platform-tools，或 adb 不在 PATH；用 `--adb /绝对路径/adb` 指定。

**安装失败？** 查看操作记录里的 adb 原始输出，常见原因是签名冲突（已装同包名但签名不同，需先卸载）、存储空间不足、APK 的 minSdk 高于设备系统版本、或设备弹出了安装确认框需要手动点允许。

**卸载系统预装？** 本工具用的是 `adb uninstall`，只适合用户应用。批量清理预装建议配合 [Universal Android Debloater](https://github.com/0x192/universal-android-debloater)。

## 相关开源项目

本项目是独立实现（Python 标准库后端 + 单文件移动端 Web UI），调研时参考了这些项目：

- [0x192/universal-android-debloater](https://github.com/0x192/universal-android-debloater) — 批量卸载系统预装
- [liriliri/aya](https://github.com/liriliri/aya)、[ludoven/QADB](https://github.com/ludoven/QADB) — 桌面 ADB GUI
- [oop7/Android-debloater](https://github.com/oop7/Android-debloater) — Tauri + React，自带 ADB
- [GoogleChromeLabs/ya-webadb](https://github.com/GoogleChromeLabs/ya-webadb) — 浏览器 WebUSB 方案（iOS Safari 不支持 WebUSB，这也是本项目采用「电脑跑服务」架构的原因）
- [libimobiledevice/ideviceinstaller](https://github.com/libimobiledevice/ideviceinstaller) — 若目标换成 iPhone 本身，应看这个

## 许可证

MIT
