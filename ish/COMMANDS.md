# iSH 车机调试命令速查（含批量执行）

> 适用：**iPhone 装 iSH（App Store 免费） + 车机已开放 5555**。本文只讲两件事：怎么敲命令、怎么一次跑多条。
> iSH 是 Alpine Linux（busybox **ash**），命令遵循标准 shell 语法，所以「一次执行多个命令」是天然支持的。

## ⭐ 最常用：连接 → 安装 → 执行一条 adb 命令，一次跑完

把下面整块**一次粘贴**进 iSH（IP、APK 路径、最后一条命令换成你的）：

```sh
adb connect 192.168.1.50:5555 \
  && adb install -r -g /root/app.apk \
  && adb shell pm list packages -3
```

**用 `&&` 而不是 `;`**：任一步失败就停下，不会「连不上还硬装」「装失败还硬执行下一条」。也可以直接写成三行依次粘贴，iSH 会逐行执行，效果一样且更好读：

```sh
adb connect 192.168.1.50:5555
adb install -r -g /root/app.apk
adb shell pm list packages -3
```

最后那条 adb 命令，按目的替换：

| 你想做什么 | 命令 |
| --- | --- |
| 看装没装上 / 列用户应用 | `adb shell pm list packages -3` |
| 确认刚装的包在不在 | `adb shell pm path com.example.app` |
| 启动刚装的应用 | `adb shell monkey -p com.example.app 1` |
| 查系统版本 / CPU 架构 | `adb shell getprop ro.build.version.release` |
| 看设备是否在线（排查 unauthorized） | `adb devices` |
| 重启车机 | `adb reboot` |

⚠️ **最后一条如果带 `;` / `&&` / 管道 `|`，整串必须加引号**，否则会被 iSH 本地 shell 拆开：

```sh
# 错：分号被 iSH 本地解析，第二条 getprop 在 iPhone 上执行 → not found
adb connect 192.168.1.50:5555 && adb install -r -g /root/app.apk && adb shell getprop a; getprop b

# 对：引号把整串作为一个参数交给车机 sh 解析
adb connect 192.168.1.50:5555 && adb install -r -g /root/app.apk && adb shell "getprop a; getprop b"
```

> 首次连接先在**车机屏幕**点一次「允许 USB 调试」并勾「始终允许」；建议先单独跑一次 `adb connect IP:5555` + `adb devices` 确认状态是 `device` 再跑三连，避免 `unauthorized` 时白装一遍。

## 实战：安装 iPhone 上的 QiPlay.apk，并授 READ_LOGS

### 1. 先把 APK 放进 iSH 能看到的地方（关键）

iSH 是 iOS 沙盒里的 Alpine，**看不到「文件」App 里的任意路径**，必须先挪进去。

#### ✅ 首选：从 iSH 终端里挂载（完全不用在「文件」App 里找 iSH 文件夹）

iSH 内置 `mount -t ios`，会从 App 内部弹出系统文件选择器，把 iOS 侧的文件夹挂进 Linux。这是绕开所有「位置 / 编辑 / 侧边栏」差异的最可靠办法：

```sh
mkdir -p /mnt
mount -t ios . /mnt
```

执行后会弹出**系统文件夹选择器** → 选中 `QiPlay.apk` 所在的那个文件夹（如「下载项」/「我的 iPhone」里某个目录，选**文件夹**不是文件）→ 确定。然后：

```sh
ls -l /mnt/QiPlay.apk                    # 能看到文件就成功了
cp /mnt/QiPlay.apk /root/QiPlay.apk      # 拷进 iSH 自己的目录，后续路径就不依赖挂载
ls -l ~/QiPlay.apk                       # 确认
umount /mnt                              # 用完卸载（可选）
```

挂载是临时的，退出 iSH 会失效；所以**建议 `cp` 到 `/root`**，之后就能一直用 `/root/QiPlay.apk`。

#### 「没有 iSH 文件夹」的两种含义

| 你说的是 | 说明与处理 |
| --- | --- |
| **「文件」App 的「位置」列表里没有 iSH 这一项** | 正常，很多版本不显示。首选上面的 `mount` 方案，完全不需要它。也可从 iSH 内部直接打开：**iSH 齿轮设置 → Filesystems → default → Browse Files**，会跳到「文件」App 并直接定位到 iSH 的文件系统 |
| 进入了 iSH 位置，但里面**没有叫 `root` 的文件夹** | iSH 暴露的就是整个 Alpine 根目录，看到的可能是 `bin`、`etc`、`root`、`home` 等一列文件夹；有 `root` 就进 `root`，没有就直接在当前层粘贴，之后用 `ls` / `find / -iname 'QiPlay*' 2>/dev/null` 找实际位置 |

**关于「… → 编辑」**：那是旧版 iOS / iPad 侧边栏的说法，新版 iPhone 上往往没有。Apple 官方指南里「编辑」在**浏览页屏幕顶部**，且只用于隐藏位置 / 排序，不是启用开关——找不到是正常的，跳过。若确实想让 iSH 出现在侧边栏：「位置」下方点「**更多位置**」（或右上角「…」）→ 打开 iSH；再不行就重开「文件」App / 重启 iPhone 一次。

#### 其他两条备选

- **共享菜单**：在「文件」App / 微信 / QQ 里找到 `QiPlay.apk` → 长按 → 共享 → 「存储到「文件」」→ 目标选 **iSH** → 存到 `root`（前提是上面那个位置存在）。
- **直接下载**：APK 若有链接，连共享菜单都不用：`apk add curl && curl -L -o ~/QiPlay.apk "<URL>"`。

**最终验证（不管走哪条）：**

```sh
ls -l ~/QiPlay.apk
```

有输出就能用 **`/root/QiPlay.apk`**（或 `~/QiPlay.apk`）。**大小写敏感**：`QiPlay.apk` ≠ `qiplay.apk`。别把「我的 iPhone/…」这种 iOS 路径直接写进 adb 命令，iSH 里不存在；若 APK 在微信 / QQ 里而「文件」App 找不到，先在那个 App 里用「共享 → 存储到「文件」」把它放进「下载项」，再挂载那个文件夹。

### 2. 一次跑完：连接 → 安装 → 授权

```sh
adb connect 192.168.1.50:5555 \
  && adb install -r -g /root/QiPlay.apk \
  && adb shell pm grant com.qipay android.permission.READ_LOGS \
  && adb shell am force-stop com.qipay
```

- 只想要「连接 → 安装 → 执行 adb 命令」这三步，删掉最后一行即可；加 `am force-stop` 是因为 **READ_LOGS 授权后要重启 App 才生效**。
- **`-g` 只自动授运行时权限，管不了 READ_LOGS**（它是 `signature|privileged|development` 权限），所以 `pm grant` 那条不能省。
- 顺序不能反：必须先装好、且包名确实是 `com.qipay`，才能 grant。
- `pm grant` 这条没有 `;` / 管道，**不需要加引号**。
- 若第 1 步只做了挂载、没 `cp`，把路径改成 **`/mnt/QiPlay.apk`** 即可（挂载状态下）；建议还是 `cp` 到 `/root`，避免 iSH 重启后挂载失效。

> 为什么这条命令能成立：`READ_LOGS` 虽是系统级权限，但同时属于 **DEVELOPMENT_TOOLS（development）** 组，只要 APK 的 manifest 里声明过 `<uses-permission android:name="android.permission.READ_LOGS"/>`，就能由 `adb shell pm grant` 授予**普通应用，不需要 root**——这是抓日志类工具的通行做法。反过来，若 APK 没声明它，怎么 grant 都失败。

### 3. 验证与排错

```sh
adb shell pm list packages | grep -i qipay                 # 确认真实包名（装完才有）
adb shell dumpsys package com.qipay | grep -i READ_LOGS    # 看到 granted=true 即成功
```

| 报错 / 现象 | 原因与处理 |
| --- | --- |
| `Unknown package: com.qipay` | 包名不对或没装上。用 `pm list packages \| grep -i qi` 查真实包名，替换 grant 里的值 |
| `has not requested permission` / `Operation not allowed` | APK manifest 没声明 READ_LOGS，`pm grant` 无能为力，需换声明过该权限的版本 / 系统签名版 |
| `SecurityException` / `permission denied` | 厂商 ROM 拦截。到车机开发者选项打开「**USB 调试(安全设置)**」或「**禁用权限监控**」，部分机型需重启后再试 |
| 命令没报错但授权不生效 | 执行 `adb shell am force-stop com.qipay` 后重新打开 App |
| 能授权但读不到全局日志 | Android 4.1+ 普通应用本就只能读自己进程的日志；看全局需 root / 系统签名，这是系统限制 |

## 0. 第一次准备（只做一次）

```sh
apk update
apk add android-tools          # 只用命令行的话装这个就够；要跑网页服务再加 python3
adb version
adb connect 192.168.1.50:5555  # 换成车机实际 IP
adb devices                    # 必须显示 device，而不是 unauthorized / offline
```

首次连接要在**车机屏幕上点一次**「允许 USB 调试」并勾「始终允许」。连不上先换组网（车机开热点让 iPhone 连，最稳）。

## 1. 两类命令别混

| 类别 | 写法 | 例子 | 实际在哪跑 |
| --- | --- | --- | --- |
| **本地 adb 命令** | `adb xxx` | `adb connect` / `adb install` / `adb uninstall` / `adb pull` / `adb reboot` | iPhone 的 iSH 里 |
| **车机端命令** | `adb shell "<设备命令>"` | `pm` / `getprop` / `wm` / `am` / `input` / `settings` / `dumpsys` | 车机上 |

单条示例：

```sh
adb shell getprop ro.build.version.release
adb shell getprop ro.product.cpu.abilist
adb shell pm list packages -3
adb install -r -g /root/app.apk            # -g 自动授运行时权限，车机没弹窗时很关键
adb uninstall com.example.app
adb shell pm path com.example.app
```

**APK 怎么进 iSH**：iOS「文件」App → `iSH` → `root`，把 `.apk` 拖进去；iSH 里用 `ls ~` / `ls /root` 确认路径。大包走无线较慢，装的时候别熄火断电。

## 2. 能一次性执行多个命令吗？能，五种方式

### A. 分号 `;` —— 顺序执行，不管前面成不成功

```sh
adb connect 192.168.1.50:5555; adb devices; adb shell getprop ro.product.model
```

### B. `&&` —— 前一条成功才继续（装包推荐）；`||` —— 失败才执行

```sh
adb connect 192.168.1.50:5555 && adb install -r -g /root/app.apk && adb shell pm list packages -3
adb connect 192.168.1.50:5555 || echo 连不上
```

### C. 直接粘贴多行 —— 一次把整块贴进 iSH，逐行执行

```sh
adb connect 192.168.1.50:5555
adb devices
adb shell getprop ro.build.version.release
adb shell getprop ro.product.cpu.abilist
adb shell wm size
```

### D. `for` 循环批量 —— 车机精简预装、批量装包最常用

```sh
# 批量冻结/卸载（包名自己替换，务必先看清单逐个确认）
for p in com.aaa.bbb com.ccc.ddd com.eee.fff; do
  adb shell pm disable-user --user 0 "$p"
done

# 批量安装 /root 下所有 APK
for f in /root/*.apk; do echo "安装 $f"; adb install -r -g "$f"; done
```

### E. 写成脚本，以后一条命令跑完

```sh
cat > /root/my.sh <<'EOF'
#!/bin/sh
adb connect 192.168.1.50:5555 || exit 1
adb shell getprop ro.build.version.release
adb shell pm list packages -3
adb install -r -g /root/app.apk
adb disconnect 192.168.1.50:5555
EOF
sh /root/my.sh
```

## 3. ⚠️ 关键坑：分号到底在「本地」还是「车机」解析

- **不加引号**：`adb shell getprop a; getprop b` → 分号被 **iSH 本地** 拆成两条，第二条 `getprop b` 在 iPhone 上执行 → `not found`。
- **加引号**：`adb shell "getprop a; getprop b"` → 整串作为**一个参数**发给车机，由车机 sh 解析成两条，正确。

```sh
# 想在车机端一次跑多条、复用同一个连接，引号必须加
adb shell "getprop ro.build.version.release; getprop ro.product.cpu.abilist; wm size; wm density; df -h /data"

# 管道同理：加了引号才是在车机上过滤
adb shell "pm list packages -3 | grep map"
```

> 网页里的「自定义 adb shell」输入框**正好相反**——它不需要引号，见第 4 节。

## 4. 网页里的「自定义 adb shell」输入框

启动服务时加 `IADC_SHELL=1` 才会出现：

```sh
IADC_TOKEN=你的口令 IADC_SHELL=1 sh ish/start.sh
```

Safari 打开 `http://127.0.0.1:8000`，选好设备后，框里填的是**车机端 shell 命令（不带 `adb shell` 前缀）**，服务端自动执行 `adb -s <设备> shell "<整串>"`。因为整串交给车机 sh 解析，所以**也能一次跑多条**：

```
getprop ro.build.version.release; getprop ro.product.cpu.abilist; wm size; wm density
```

要点：

- **不要**写 `adb install ...`、`adb connect ...` —— 那是本地命令，车机里没有 `adb`。
- **不要**加外层引号（和 iSH 终端相反），加了反而变成一整个字符串。
- `;`、`&&`、管道 `|` 都能用；输出一次性合并显示在「操作记录」里，不逐条分开。
- 限制：**单行输入、整串 ≤ 500 字符、超时 60 秒**。要批量卸载几十个包，回到 iSH 终端用 `for` 循环。
- 该输入框等于把车机 shell 暴露给网页，务必同时设置 `IADC_TOKEN`。

## 5. 车机实用批量块（改一改就能用）

### 一次性摸底（决定该下哪个版本的 APK）

```sh
adb shell "getprop ro.build.version.release; getprop ro.product.cpu.abilist; getprop ro.product.model; wm size; wm density"
```

老车机多是 32 位 `armeabi-v7a` + Android 6~8，新版 APK 会报「解析包错误 / 与此设备不兼容」，查清架构再下包。

### 精简预装（可逆优先）

```sh
adb shell pm list packages -3                       # 先看清单，逐个确认包名
adb shell pm path com.xxx                           # 记下 APK 路径
adb pull /data/app/~~xxx==/base.apk /root/backup/   # 备份原厂 APK（路径用上一条输出替换）
for p in com.xxx com.yyy; do
  adb shell pm disable-user --user 0 "$p"           # 冻结，随时 adb shell pm enable "$p" 恢复
done
# 或仅对当前用户卸载，恢复出厂可还原：
# adb shell pm uninstall -k --user 0 "$p"
```

**别动原厂桌面和系统/车辆相关应用**：方控按键映射、倒车影像/360 全景常绑在原厂桌面上，误删可能按键失灵、影像延迟甚至卡 Logo 变砖。

### 收尾

```sh
adb disconnect 192.168.1.50:5555
```

## 6. 两个 iSH 专属提醒

- **后台会被 iOS 冻结**：跑长批量任务时保持 iSH 在前台；要切去 Safari，先 `apk add tmux` 并在 tmux 会话里跑，或切回 iSH 一次再切走。
- **Alpine 的 `android-tools` 版本偏老**：连固定 5555 完全够用，但不一定支持 Android 11+ 的 `adb pair`——车机 5555 场景用不到配对。
