#!/data/data/com.termux/files/usr/bin/bash
# iPhone ADB 控制台 —— 零电脑模式启动脚本
#
# 在 Termux 里执行：  bash termux/start.sh
# 让「服务端 + adb」直接跑在 Android 设备上，iPhone 只需同 WiFi 打开网页。
#
# 可选环境变量：
#   ADB_TARGET   要连接的 adbd 地址，默认 127.0.0.1:5555（连本机自己）
#                若 Termux 跑在另一台安卓机上、要管的是别的设备，填 目标IP:5555
#   PORT         HTTP 端口，默认 8000
#   IADC_TOKEN   访问口令，强烈建议设置
#
# 例： IADC_TOKEN=abc123 ADB_TARGET=192.168.1.50:5555 bash termux/start.sh

set -u

PORT="${PORT:-8000}"
ADB_TARGET="${ADB_TARGET:-127.0.0.1:5555}"
TOKEN="${IADC_TOKEN:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "============================================================"
echo "  iPhone ADB 控制台 - 零电脑模式 (Termux)"
echo "============================================================"

# 1) 依赖：Python 与 adb 客户端（Termux 的 android-tools 包自带 adb）
if ! command -v python3 >/dev/null 2>&1 || ! command -v adb >/dev/null 2>&1; then
    echo "正在安装 python / android-tools ..."
    pkg install -y python android-tools || { echo "依赖安装失败，请检查 Termux 软件源"; exit 1; }
fi

# 2) 连接 adbd（本机自连，或连接到另一台 5555 设备）
echo "连接 adbd: $ADB_TARGET"
adb connect "$ADB_TARGET" || true
adb devices || true
echo
echo "  显示 unauthorized -> 在设备弹出的『允许 USB 调试 / 无线调试』对话框点允许"
echo "  连接失败         -> 设备尚未监听 5555，见 README『模式 B』里的开启办法"
echo "                      （Android 11+ 可先 adb pair <IP>:<配对端口> 完成配对）"
echo

# 3) 取本机 WiFi IP（UDP connect 技巧，不发实际数据包，无需额外包）
IP="$(python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(('223.5.5.5', 80))
    print(s.getsockname()[0])
except OSError:
    print('')
finally:
    s.close()
" 2>/dev/null || true)"
[ -z "$IP" ] && IP="<本机WiFi IP>"

# 4) 启动 HTTP 服务
echo "iPhone Safari 打开： http://$IP:$PORT"
echo "（iPhone 与这台设备需在同一 WiFi；路由器请勿开启 AP 客户端隔离）"
echo "停止服务：按 Ctrl+C"
echo "============================================================"

cd "$ROOT"
if [ -n "$TOKEN" ]; then
    exec python3 server.py --port "$PORT" --token "$TOKEN"
else
    echo "提示：未设置口令，建议用 IADC_TOKEN=你的口令 bash termux/start.sh 启动"
    exec python3 server.py --port "$PORT"
fi
