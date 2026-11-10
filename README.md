# iPhone ADB 控制台（iPhone ADB Console）

在 **iPhone 的 Safari** 里打开一个网页，可视化地给开放了 **ADB over TCP/IP（默认 5555 端口）** 的 Android 设备**安装 APK、列出并卸载应用**。后端零第三方依赖，只需要 Python 3.8+ 和本机 `adb`。

```
[ iPhone Safari ]  --HTTP-->  [ server.py + adb ]  --adb connect IP:5555-->  [ Android 设备 ]
   只负责显示界面          真正执行安装/卸载             车机 / 盒子 / 手机
                          可跑在电脑（模式 A）、Android 设备自己的
                          Termux（模式 B），或 iPhone 自己的 iSH（模式 C）
```

## 先弄清一个前提

**ADB 是 Android 专用协议，iPhone 不支持 ADB，iOS Safari 也不支持 WebUSB。** 更关键的一层是：**普通网页 / PWA 没有裸 TCP Socket 能力**——浏览器只开放 HTTP、WebSocket、WebRTC，Chrome 的 Direct Sockets 仅限隔离式 Web App（IWA），iOS 完全没有；而 ADB 是跑在 TCP 5555 上的私有二进制协议（CNXN / AUTH / OPEN / WRTE 帧），还要完成 RSA 密钥授权握手。所以**网页形态的 iPhone 无法直连 5555，跟它和设备是否在同一 WiFi 无关**——必须有一个能运行 `adb` 的服务端替它说这个协议。

但这个服务端**不一定是电脑**：Mac / Windows / Linux 可以，树莓派 / NAS 可以，**Android 设备自己（Termux）也可以**，见下方「模式 B」，此时 iPhone 和设备同一 WiFi 就完全够用。若要做成 iPhone 直连的**原生 App**（不用任何中间设备），GitHub 上已有把 ADB host 移植到 iOS 的开源实现：[zonghai-li/adb-ios](https://github.com/zonghai-li/adb-ios)（Apache-2.0，支持 connect / installApk / shell）和 [wsvn53/adb-mobile](https://github.com/wsvn53/adb-mobile)（编译 `libadb.a`，附中文文档与 demo），代价是需要 Xcode + 签名侧载，App Store 上没有成品。

如果你要管理的是 **iPhone 自身的应用**（安装/卸载 `.ipa`），那需要的是 `libimobiledevice` / `ideviceinstaller` / iDescriptor，与本项目无关。

## 只想开箱即用？先看这里

**如果你的设备是「一台 iPhone + 一台已经开放 5555 的设备」，本项目其实不是最省事的选择。** 上面说的限制只针对**网页**：iPhone 装一个**原生 App 就能自己跑 adb 客户端**，不必借电脑、不必装 Termux、不必跑任何服务端。

| 方案 | 形态 | 装/卸 APK | 费用 | 说明 |
| --- | --- | --- | --- | --- |
| [ADBox](https://apps.apple.com/cn/app/adbox-tv-device-debug-viewer/id6777080682) | App Store 原生 App，纯本地客户端、无后端无账号 | 支持（另有文件、Shell、logcat、投屏） | 浏览免费；装卸等 Pro 功能月订阅 ¥22 / 终身 ¥88 | **最贴合「iPhone + 只开 5555 的盒子 / 电视」**，需 iOS 17+ |
| [iSH Shell](https://ish.app/) | App Store 免费，在 iOS 上跑 Alpine Linux | `apk add android-tools` 后用 adb 命令 | 免费 | 不付费、能接受命令行 |
| [Scrcpy Remote / scrcpy-mobile](https://github.com/wsvn53/scrcpy-mobile) | App Store 原生 App（MIT 开源） | 以投屏控制为主 | 约 ¥6–10 | 主要想远程操控屏幕 |

> **甲壳虫 ADB 助手只有 Android 版，iPhone 装不了**；ADBox 基本就是它在 iOS 上的对应物。本项目适合的是：想要**免费、无订阅、自己可控、且用 Safari 网页而不是装 App** 的场景——具体做法见「模式 C」：把本项目的服务端直接跑在 iPhone 自己的 iSH 里。

iSH 里连 5555（**不需要配对**）：

```bash
apk add android-tools
adb connect 192.168.1.50:5555   # 首次在设备上点「允许 USB 调试」并勾选始终允许
adb devices
adb install -r /path/app.apk
adb uninstall com.example.app
```

## 模式 A：电脑跑服务（最简单）

### 1. 让 Android 设备开放 5555

- **已 root 或曾 USB 连过电脑**（最经典）：USB 连上电脑，执行 `adb tcpip 5555`，然后拔掉数据线。之后设备就在 `<手机IP>:5555` 上监听。
- **部分电视盒子 / 模拟器 / 开发板**：出厂就默认监听 5555，直接用即可。
- **Android 11+ 原生「无线调试」**：端口是随机的，需先 `adb pair <IP>:<配对端口> <配对码>` 配对，再 `adb connect <IP>:<调试端口>`（**配对端口 ≠ 调试端口**）。本工具只提供 `connect`，配对请在任意能跑 adb 的地方先完成（电脑、iPhone 的 iSH、或设备自己的 Termux 都可以，**不需要电脑**），再把无线调试主页面显示的**调试端口**填进网页连接框——`/api/connect` 支持 1–65535 任意端口。
- **只开 5555 的设备（盒子 / 车机 / 传统 `adb tcpip 5555`）**：**没有配对这一步**。`adb connect <IP>:5555` 直连，首次在设备上点一次「允许 USB 调试」RSA 授权框即可。

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

## 模式 B：零电脑，服务跑在 Android 设备上（Termux）

**这才是不需要电脑的用法**：把 `server.py` 和 `adb` 都放到被调试设备自己身上（Termux），iPhone Safari 直接访问这台设备的 IP。此时 iPhone 与设备**同一 WiFi 就完全够用**，不需要第三台机器。

```
[ iPhone Safari ] --HTTP--> [ 同一台 Android：Termux 跑 server.py + adb ] --127.0.0.1:5555--> 本机 adbd
```

### 步骤

1. 在 Android 设备上装 **Termux**（推荐 F-Droid 或 [GitHub Release](https://github.com/termux/termux-app/releases)，Play 商店版已停更）。
2. 克隆仓库并启动：

```bash
pkg install -y python android-tools git
git clone https://github.com/wanggood88/iphone-adb-console.git
cd iphone-adb-console
IADC_TOKEN=你的口令 bash termux/start.sh
```

`termux/start.sh` 会自动装依赖、`adb connect 127.0.0.1:5555` 自连本机 adbd、算出 WiFi IP 并打印 iPhone 该访问的地址，然后启动服务。

3. iPhone Safari 打开打印出的 `http://<设备IP>:8000`，界面与操作和模式 A 完全一致。

> 首次连接若弹出「允许 USB 调试 / 允许无线调试」，点允许并勾选「始终允许」——Termux 生成的 `adbkey` 就是它自己的调试密钥。

### 设备还没监听 5555 怎么办

- **Android 11+ 无电脑开启**：开发者选项 → 无线调试 →「使用配对码配对设备」，记下 IP、配对端口、配对码；在 Termux 里执行 `adb pair <IP>:<配对端口>` 并输入配对码，再 `adb connect <IP>:<连接端口>`，最后 `adb tcpip 5555` 固定端口。
- **已 root**：`su -c 'setprop service.adb.tcp.port 5555; stop adbd; start adbd'`。
- **传统做法**：第一次仍需 USB 连一次电脑执行 `adb tcpip 5555`，之后就再也不用电脑（但设备重启后设置可能丢失，需重来）。

### 被调试设备装不了 Termux（如部分 Android TV 盒子）

把 Termux 跑在**另一台安卓手机 / 旧手机 / 树莓派**上，用 `ADB_TARGET` 指向盒子：

```bash
ADB_TARGET=192.168.1.50:5555 IADC_TOKEN=你的口令 bash termux/start.sh
```

依然不用电脑，只是多一台常驻的小设备。

### 局限

- 设备重启后 5555 可能关闭；Termux 需保持后台运行（关闭电池优化、后台加锁）。
- 路由器开启「AP 客户端隔离」时 iPhone 访问不到设备的 8000 端口，需关闭隔离。
- `server.py` 与 `index.html` 和模式 A 完全相同，零改动；只是把运行环境从电脑换成了设备自己。
- **车机 / TV 盒子通常装不了也操作不了 Termux，模式 B 不适用**；这类设备请用「只想开箱即用」里的现成 App，或下面的模式 C。

## 模式 C：iPhone 本机跑服务（iSH + Safari，真正只用两台设备）

**浏览器本身不能直连 5555，但服务端可以跑在 iPhone 自己身上。** [iSH Shell](https://ish.app/)（App Store 免费，在 iOS 上跑 Alpine Linux）里能同时装 Python 3 和 adb；用它跑 `server.py`，再用 Safari 打开 `http://127.0.0.1:8000`，网页就能装/卸 APK、列应用、执行 adb 命令。

```
[ iPhone Safari ] --127.0.0.1:8000--> [ 同一台 iPhone：iSH 跑 server.py + adb ] --IP:5555--> [ 车机 ]
   只走本机 loopback                     不经过 WiFi / 热点网络                    只有这一跳跨网络
```

### 步骤

1. 让车机开放 5555 并记下 IP（见模式 A 第 1 节 / 车机专属说明）。
2. iPhone 装 **iSH**；把本仓库放进 iSH 的文件目录：iOS「文件」App → `iSH` → `root`，或直接 `apk add git` 后 `git clone`。
3. 在 iSH 里：

```sh
apk add python3 android-tools
cd ~/iphone-adb-console
sh ish/start.sh
# 建议带口令：IADC_TOKEN=你的口令 sh ish/start.sh
# 想在网页里执行任意 adb 命令：IADC_TOKEN=你的口令 IADC_SHELL=1 sh ish/start.sh
```

4. Safari 打开 **`http://127.0.0.1:8000`**（用 `http`，不要 `https`），填口令 → 输入车机 IP、端口 5555 → 连接 → 装/卸应用。启用 `IADC_SHELL=1` 后页面会出现「自定义 adb shell」输入框。
5. 也可以不通过浏览器，直接在 iSH 终端敲 `adb connect IP:5555`、`adb install -r x.apk`、`adb uninstall 包名`、`adb shell ...`。

> **iSH 里怎么敲命令、怎么一次执行多条**：见 [ish/COMMANDS.md](ish/COMMANDS.md)。最常用的是一条命令串完「连接 → 安装 → 执行 adb 命令」：
> ```sh
> adb connect 192.168.1.50:5555 && adb install -r -g /root/app.apk && adb shell pm list packages -3
> ```
> 用 `&&` 串联（失败即停）；最后一条命令若带 `;` / 管道，整串要加引号，否则会被 iSH 本地 shell 拆开。文档里还有 `for` 循环批量装卸、脚本文件、车机摸底与精简预装的完整示例。

### 组网：别押注在 iPhone 个人热点上

Safari 访问 `127.0.0.1` 是本机 loopback，**与热点/WiFi 怎么组无关**；只有 iSH 里 `adb connect` 那一跳需要能到达车机的 5555。

| 组网 | 建议 |
| --- | --- |
| iPhone 和车机连**同一个普通 WiFi**（家里路由器、便携路由器、另一台设备开的热点） | ✅ 最稳 |
| **车机开热点、iPhone 连它**（车机是网关） | ✅ 通常可行，客户端主动连网关 |
| **iPhone 开个人热点、车机连它**（iPhone 是网关，车机拿 `172.20.10.x`） | ⚠️ iOS 个人热点默认做 NAT + 客户端隔离，Apple 文档明确「不提供客户端之间的通信」；iPhone 本机能否访问热点客户端的端口没有稳定保证，不同 iOS 版本 / USB 共享 /「最大兼容性」表现不一 |

第三种先在 iSH 里试一发 `adb connect 172.20.10.x:5555`；连不上就换前两种，**这不影响网页本身能不能打开**。另外车机连 iPhone 热点时常常因为没有外网而反复重连，会拖垮 adb 会话。

### iSH 的两个坑

- **后台会被冻结**：iOS 切走 iSH 后会暂停其进程，Safari 页面可能一直转圈。切回 iSH 一次再切回 Safari；iPad 用分屏、iPhone 用「引导式访问」，或 `apk add tmux` 后在 tmux 会话里跑脚本。
- iSH 是 x86 模拟环境，上传大 APK 会明显慢于电脑；`adb` 来自 Alpine 的 `android-tools`，连固定 5555 够用，但版本可能偏老，不一定支持 Android 11+ 的 `adb pair`。本项目模式 C 面向**固定 5555** 的车机 / 盒子场景。

> 安全：`--allow-shell` 等于把车机 shell 暴露给能访问 `127.0.0.1:8000` 的人；虽然只有本机可达，仍建议同时设置 `IADC_TOKEN`。用完关闭车机的 5555 / 无线调试。

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

- **传统 `adb tcpip 5555` 传输明文，仅靠 RSA 公钥授权**（首次连接需在设备上点「允许调试」）；Android 11+ 原生无线调试改为 TLS + 配对码，但端口随机。无论哪种，5555 一旦可达，能连上的人就几乎能完全控制设备（读文件、装/卸软件、恢复出厂设置）。请只在可信的家庭 / 办公 WiFi 使用，并确认授权弹窗来自你信任的客户端。
- **不要把 8000 端口或设备的 5555 端口映射到公网**，不要配置端口转发、内网穿透或反向代理到公网。
- 用完请在开发者选项里**关闭无线调试 / USB 调试**，或执行 `adb usb` 切回 USB 模式。
- 建议始终设置 `--token`，并使用随机口令。
- 自定义 shell 默认关闭；开启后等同于把设备 shell 暴露给能访问网页的人。
- 卸载系统应用可能导致系统功能异常；`adb uninstall` 对纯系统应用通常无效，需要 `pm uninstall -k --user 0 <包名>`（可用 `--allow-shell` 执行，风险自负）。
- 服务端对所有用户输入做了正则白名单校验，且所有 adb 调用都使用参数数组、不使用 `shell=True`；但这不能替代网络层面的隔离。

## 常见问题

**iPhone 打不开页面？** 确认 iPhone 与「跑 server.py 的那台机器」（电脑，或装了 Termux 的 Android 设备）在同一 WiFi；关闭路由器的「AP 客户端隔离」；电脑需放行 8000 端口；一律用 `http://` 而不是 `https://`；Windows 需在「专用网络」下允许 Python 通过防火墙。不要把本页放进 HTTPS 站点去调用本地 HTTP 服务，浏览器会拦截混合内容。

**能完全不要电脑吗？同 WiFi 直接连不行吗？** **装原生 App 就可以**：ADBox / iSH / Scrcpy Remote 让 iPhone 自己跑 adb 客户端，同 WiFi 直连 5555，完全不要电脑（见「只想开箱即用」）。**浏览器直接连 5555 不行**——浏览器没有裸 TCP Socket API、iOS Safari 也没有 WebUSB，这与是否同 WiFi 无关。但**网页界面本身可以只用一台 iPhone**：把 `server.py` 跑在 iSH 里、Safari 打开 `http://127.0.0.1:8000`（见模式 C）；否则网页就得另配一个跑服务的地方（电脑，或设备自己的 Termux，见模式 B）。基于 adb-ios / adb-mobile 自编译侧载也能原生直连，但现在有上架成品，通常没必要。

**连不上 5555？** 确认设备已开启 USB/无线调试并授权过；IP 是否变化；端口是否是 5555（Android 11+ 原生无线调试端口是随机的）；可先在服务端机器上手工执行 `adb connect IP:5555` 验证。

**提示「缺少 ADB」？** 跑 server.py 的机器上没有 adb：电脑需装 platform-tools，Termux 执行 `pkg install android-tools`；也可用 `--adb /绝对路径/adb` 指定。

**安装失败？** 查看操作记录里的 adb 原始输出，常见原因是签名冲突（已装同包名但签名不同，需先卸载）、存储空间不足、APK 的 minSdk 高于设备系统版本、或设备弹出了安装确认框需要手动点允许。

**卸载系统预装？** 本工具用的是 `adb uninstall`，只适合用户应用。批量清理预装建议配合 [Universal Android Debloater](https://github.com/0x192/universal-android-debloater)。

## 相关开源项目

本项目是独立实现（Python 标准库后端 + 单文件移动端 Web UI），调研时参考了这些项目：

- [0x192/universal-android-debloater](https://github.com/0x192/universal-android-debloater) — 批量卸载系统预装
- [liriliri/aya](https://github.com/liriliri/aya)、[ludoven/QADB](https://github.com/ludoven/QADB) — 桌面 ADB GUI
- [oop7/Android-debloater](https://github.com/oop7/Android-debloater) — Tauri + React，自带 ADB
- [GoogleChromeLabs/ya-webadb](https://github.com/GoogleChromeLabs/ya-webadb) — 浏览器 WebUSB 方案；其作者明确说明「浏览器没有创建 TCP 连接的 API」，这也是本项目采用「服务端代跑 adb」架构的原因
- [zonghai-li/adb-ios](https://github.com/zonghai-li/adb-ios)、[wsvn53/adb-mobile](https://github.com/wsvn53/adb-mobile) — 把 ADB host 移植成 iOS 静态库，iPhone 可原生直连 5555（需 Xcode 编译签名侧载）；同作者的 [scrcpy-mobile](https://github.com/wsvn53/scrcpy-mobile) 已上架 App Store
- [termux/termux-app](https://github.com/termux/termux-app)、[ish-app/ish](https://github.com/ish-app/ish) — 分别在 Android / iOS 上提供能跑 `adb` 的本地终端，是「零电脑」的关键
- [yume-chan/ya-webadb (Tango ADB)](https://github.com/yume-chan/ya-webadb) — TypeScript 实现的 ADB 协议栈；配合微信小程序的 `wx.createTCPSocket` 可在 iPhone 微信里直连 adbd，同样无需中间设备
- [libimobiledevice/ideviceinstaller](https://github.com/libimobiledevice/ideviceinstaller) — 若目标换成 iPhone 本身，应看这个

## 许可证

MIT
