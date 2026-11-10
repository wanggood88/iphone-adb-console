#!/bin/sh
# iPhone ADB 控制台 —— iPhone 本机模式（iSH Shell + Safari）
#
# 在 iPhone 的 iSH（App Store 免费，Alpine Linux）里执行：
#     sh ish/start.sh
# 然后在 Safari 打开 http://127.0.0.1:8000
#
# 原理：Python 与 adb 都跑在 iPhone 自己身上；Safari 访问的是本机 loopback，
# 不经过 WiFi / 热点网络；只有 adb connect 那一跳需要连到车机的 5555 端口。
#
# 可选环境变量：
#   PORT        网页端口，默认 8000
#   IADC_TOKEN  访问口令，建议设置
#   IADC_SHELL  设为 1 时启用页面的「自定义 adb shell」输入框（有风险）
#
# 例： IADC_TOKEN=abc123 IADC_SHELL=1 sh ish/start.sh

set -u

PORT="${PORT:-8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "============================================================"
echo "  iPhone ADB 控制台 - iPhone 本机模式 (iSH + Safari)"
echo "============================================================"

# 依赖：Alpine 的 python3 与 android-tools（提供 adb），两者可共存
if ! command -v python3 >/dev/null 2>&1 || ! command -v adb >/dev/null 2>&1; then
    echo "正在安装 python3 / android-tools ..."
    apk add --no-cache python3 android-tools || {
        echo "安装失败：请先执行 apk update，或检查 iSH 软件源。"
        exit 1
    }
fi

adb version 2>/dev/null | head -1 || true

# 组装 server.py 参数（用位置参数，口令含空格也不会被拆开）
set -- --port "$PORT"
[ -n "${IADC_TOKEN:-}" ] && set -- "$@" --token "$IADC_TOKEN"
[ "${IADC_SHELL:-0}" = "1" ] && set -- "$@" --allow-shell

echo
echo "  Safari 打开： http://127.0.0.1:$PORT"
echo "  在页面的「连接设备」里填车机 IP 和端口 5555"
echo
echo "  重要：iSH 切到后台会被 iOS 冻结。若 Safari 一直转圈，"
echo "        切回 iSH 一次再切回 Safari；iPad 可用分屏，"
echo "        或 apk add tmux 后在 tmux 会话里运行本脚本。"
echo "  停止服务：回到 iSH 按 Ctrl+C"
echo "============================================================"

cd "$ROOT"
exec python3 server.py "$@"
