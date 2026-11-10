#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iPhone ADB Console / iPhone ADB 可视化控制台 —— 服务端

零第三方依赖，只使用 Python 3 标准库（Python 3.8+）。

工作方式：
    [iPhone Safari] --HTTP--> [本脚本(电脑)] --ADB over TCP/IP:5555--> [Android 设备]

iPhone 本身不支持 ADB，也不支持 WebUSB，所以它需要一台电脑/服务器运行本脚本，
由脚本调用本机的 adb 去连接开放了 5555 无线调试端口的 Android 设备。

启动：
    python3 server.py
    python3 server.py --port 8000 --token my-secret
    python3 server.py --adb /opt/platform-tools/adb --allow-shell

安全说明见 README.md。ADB over TCP/IP 是明文且无认证的协议，请只在可信局域网使用。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

APP_NAME = "iPhone ADB Console"
APP_VERSION = "1.0.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_UPLOAD = 512 * 1024 * 1024  # 单个 APK 上限
MAX_JSON_BODY = 1024 * 1024

SERIAL_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
PACKAGE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,256}$")
HOST_RE = re.compile(r"^[A-Za-z0-9._-]{1,253}$")

# 运行时配置，由 main() 填充
ADB_BIN = None
ACCESS_TOKEN = ""
ALLOW_SHELL = False
VERBOSE = False


class AdbError(Exception):
    """ADB 相关错误，消息会直接展示在页面日志里。"""


# ---------------------------------------------------------------------------
# ADB 封装
# ---------------------------------------------------------------------------

def find_adb(cli_value=None):
    """按 --adb / ADB_PATH / PATH 的顺序查找 adb 可执行文件。"""
    candidates = [cli_value, os.environ.get("ADB_PATH"), "adb"]
    for candidate in candidates:
        if not candidate:
            continue
        path = shutil.which(candidate)
        if not path and os.path.sep in candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            path = candidate
        if path:
            return os.path.abspath(path)
    return None


def adb_help_text():
    return (
        "未找到 adb。请先安装 Android SDK Platform-Tools：\n"
        "  macOS:   brew install android-platform-tools\n"
        "  Ubuntu:  sudo apt install android-sdk-platform-tools\n"
        "  Windows: 从 developer.android.com/studio/releases/platform-tools 下载并解压\n"
        "也可以通过 --adb /绝对路径/adb 或环境变量 ADB_PATH 指定。"
    )


def run_adb(args, timeout=60):
    """以参数数组方式调用 adb（绝不使用 shell=True，避免命令注入）。"""
    if not ADB_BIN:
        raise AdbError(adb_help_text())
    cmd = [ADB_BIN] + list(args)
    if VERBOSE:
        print("[adb] " + " ".join(cmd), file=sys.stderr)
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise AdbError("adb 命令执行超时（%d 秒）：%s" % (timeout, " ".join(cmd)))
    except OSError as exc:
        raise AdbError("无法执行 adb：%s" % exc)
    out = proc.stdout.decode("utf-8", "replace").strip()
    err = proc.stderr.decode("utf-8", "replace").strip()
    return proc.returncode, out, err


def merged_output(out, err):
    parts = [p for p in (out, err) if p]
    return "\n".join(parts) if parts else "(adb 无输出)"


def is_success(rc, out, err):
    """adb 有些失败场景仍返回 0，需要结合输出关键词判断。"""
    text = (out + "\n" + err).lower()
    if rc != 0:
        return False
    for word in ("failure", "failed to", "unable to", "error:", "no devices", "not found", "permission denied"):
        if word in text:
            return False
    return True


def parse_devices(text):
    """解析 `adb devices -l` 的输出。"""
    devices = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("list of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        info = {}
        for token in parts[2:]:
            if ":" in token:
                key, _, value = token.partition(":")
                info[key] = value
        devices.append({
            "serial": serial,
            "state": state,
            "model": info.get("model", ""),
            "product": info.get("product", ""),
            "device": info.get("device", ""),
            "transport_id": info.get("transport_id", ""),
        })
    return devices


def parse_packages(text):
    """解析 `pm list packages` 的输出。"""
    packages = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            pkg = line[len("package:"):].strip()
            if pkg and PACKAGE_RE.match(pkg):
                packages.append(pkg)
    return sorted(set(packages))


def lan_ip():
    """猜一个可用于局域网访问的本机 IP（不实际发包）。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("223.5.5.5", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# HTTP 处理
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "iPhoneADBConsole/" + APP_VERSION
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # -- 基础响应 ----------------------------------------------------------

    def log_message(self, fmt, *args):
        if VERBOSE:
            super().log_message(fmt, *args)

    def _send_bytes(self, body, status=200, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, status=200):
        self._send_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"), status)

    def _ok(self, **kwargs):
        data = {"ok": True}
        data.update(kwargs)
        self._json(data)

    def _fail(self, message, status=200):
        self._json({"ok": False, "error": str(message)}, status)

    def _auth_ok(self):
        if not ACCESS_TOKEN:
            return True
        if self.headers.get("X-Access-Token", "") == ACCESS_TOKEN:
            return True
        self._fail("访问口令错误或缺失，请在页面顶部填写。", 401)
        return False

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_JSON_BODY:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data

    @staticmethod
    def _need_string(data, key, pattern=None, label=None):
        value = str(data.get(key, "") or "").strip()
        if not value:
            raise ValueError("缺少参数：%s" % (label or key))
        if pattern and not pattern.match(value):
            raise ValueError("参数 %s 含有非法字符：%s" % (label or key, value))
        return value

    # -- 路由 --------------------------------------------------------------

    def do_GET(self):
        self._wrap(self._get)

    def do_POST(self):
        self._wrap(self._post)

    def do_OPTIONS(self):
        self._send_bytes(b"", 204, "text/plain; charset=utf-8")

    def _wrap(self, fn):
        try:
            fn()
        except AdbError as exc:
            self._fail(str(exc))
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._fail(str(exc))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001
            if VERBOSE:
                traceback.print_exc()
            self._fail("%s: %s" % (type(exc).__name__, exc))

    def _get(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self._serve_page()
        if path == "/api/status":
            # 状态接口无需口令，前端据此决定是否显示口令输入框
            rc, out, err = (0, "", "")
            adb_version = ""
            if ADB_BIN:
                try:
                    rc, out, err = run_adb(["version"], timeout=10)
                    adb_version = out.splitlines()[0] if out else ""
                except AdbError:
                    adb_version = ""
            return self._ok(
                app=APP_NAME,
                version=APP_VERSION,
                adb_found=bool(ADB_BIN),
                adb_path=ADB_BIN or "",
                adb_version=adb_version,
                require_token=bool(ACCESS_TOKEN),
                allow_shell=ALLOW_SHELL,
                max_upload_mb=MAX_UPLOAD // (1024 * 1024),
            )
        if not self._auth_ok():
            return
        if path == "/api/devices":
            return self._api_devices()
        if path == "/api/packages":
            return self._api_packages(query)
        self._fail("未知接口：%s" % path, 404)

    def _post(self):
        path = urlparse(self.path).path.rstrip("/")
        if not self._auth_ok():
            return
        if path == "/api/connect":
            return self._api_connect()
        if path == "/api/disconnect":
            return self._api_disconnect()
        if path == "/api/install":
            return self._api_install()
        if path == "/api/uninstall":
            return self._api_uninstall()
        if path == "/api/shell":
            return self._api_shell()
        self._fail("未知接口：%s" % path, 404)

    def _serve_page(self):
        target = os.path.join(BASE_DIR, "index.html")
        if not os.path.isfile(target):
            return self._fail("找不到 index.html，请确保它与 server.py 在同一目录。", 500)
        with open(target, "rb") as fh:
            body = fh.read()
        self._send_bytes(body, 200, "text/html; charset=utf-8")

    # -- 具体接口 ----------------------------------------------------------

    def _api_devices(self):
        rc, out, err = run_adb(["devices", "-l"], timeout=20)
        return self._ok(devices=parse_devices(out), output=merged_output(out, err))

    def _api_connect(self):
        data = self._json_body()
        host = self._need_string(data, "host", HOST_RE, "设备 IP / 主机名")
        try:
            port = int(data.get("port", 5555))
        except (TypeError, ValueError):
            raise ValueError("端口必须是 1-65535 的整数")
        if not 1 <= port <= 65535:
            raise ValueError("端口必须是 1-65535 的整数")
        target = "%s:%d" % (host, port)
        rc, out, err = run_adb(["connect", target], timeout=30)
        text = merged_output(out, err)
        return self._ok(
            target=target,
            connected=is_success(rc, out, err),
            output=text,
        )

    def _api_disconnect(self):
        data = self._json_body()
        device = self._need_string(data, "device", SERIAL_RE, "设备序列号")
        rc, out, err = run_adb(["disconnect", device], timeout=20)
        return self._ok(output=merged_output(out, err), success=is_success(rc, out, err))

    def _api_packages(self, query):
        device = (query.get("device", [""])[0] or "").strip()
        if not device or not SERIAL_RE.match(device):
            raise ValueError("请先选择一个有效设备")
        scope = (query.get("scope", ["user"])[0] or "user").strip()
        args = ["-s", device, "shell", "pm", "list", "packages"]
        if scope == "user":
            args.append("-3")
        elif scope == "system":
            args.append("-s")
        elif scope != "all":
            raise ValueError("scope 只能是 user / system / all")
        rc, out, err = run_adb(args, timeout=90)
        packages = parse_packages(out)
        return self._ok(
            device=device,
            scope=scope,
            packages=packages,
            count=len(packages),
            output=merged_output(out, err),
        )

    def _api_install(self):
        device = (self.headers.get("X-Device") or "").strip()
        if not device or not SERIAL_RE.match(device):
            raise ValueError("请先选择一个有效设备（X-Device 请求头）")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("Content-Length 无效")
        if length <= 0:
            raise ValueError("没有收到 APK 文件内容")
        if length > MAX_UPLOAD:
            raise ValueError("APK 超过 %d MB 上限" % (MAX_UPLOAD // (1024 * 1024)))

        tmpdir = tempfile.mkdtemp(prefix="iphone-adb-console-")
        apk_path = os.path.join(tmpdir, "upload.apk")
        try:
            remaining = length
            with open(apk_path, "wb") as fh:
                while remaining > 0:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    fh.write(chunk)
                    remaining -= len(chunk)
            if remaining > 0:
                raise ValueError("APK 传输中断，请重试")
            if os.path.getsize(apk_path) < 1024:
                raise ValueError("文件太小，不像是一个 APK")

            rc, out, err = run_adb(["-s", device, "install", "-r", apk_path], timeout=600)
            text = merged_output(out, err)
            return self._ok(
                device=device,
                success=is_success(rc, out, err),
                output=text,
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _api_uninstall(self):
        data = self._json_body()
        device = self._need_string(data, "device", SERIAL_RE, "设备序列号")
        package = self._need_string(data, "package", PACKAGE_RE, "应用包名")
        rc, out, err = run_adb(["-s", device, "uninstall", package], timeout=120)
        return self._ok(
            device=device,
            package=package,
            success=is_success(rc, out, err),
            output=merged_output(out, err),
        )

    def _api_shell(self):
        if not ALLOW_SHELL:
            raise AdbError("自定义 shell 命令未启用。如确需使用，启动时加 --allow-shell（有安全风险）。")
        data = self._json_body()
        device = self._need_string(data, "device", SERIAL_RE, "设备序列号")
        command = str(data.get("command", "") or "").strip()
        if not command or len(command) > 500:
            raise ValueError("命令不能为空且不得超过 500 字符")
        rc, out, err = run_adb(["-s", device, "shell", command], timeout=60)
        return self._ok(
            device=device,
            command=command,
            success=is_success(rc, out, err),
            output=merged_output(out, err),
        )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    global ADB_BIN, ACCESS_TOKEN, ALLOW_SHELL, VERBOSE

    parser = argparse.ArgumentParser(
        description="%s v%s —— 在 iPhone 浏览器里可视化管理 5555 端口的 ADB 设备" % (APP_NAME, APP_VERSION),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default="0.0.0.0", help="监听地址，默认 0.0.0.0（局域网可访问）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口，默认 8000")
    parser.add_argument("--token", default=os.environ.get("IADC_TOKEN", ""), help="访问口令，也可用环境变量 IADC_TOKEN")
    parser.add_argument("--adb", default=None, help="adb 可执行文件路径，也可用环境变量 ADB_PATH")
    parser.add_argument("--allow-shell", action="store_true", help="启用自定义 adb shell 命令（有安全风险，默认关闭）")
    parser.add_argument("--verbose", action="store_true", help="打印访问日志与 adb 命令")
    args = parser.parse_args()

    ADB_BIN = find_adb(args.adb)
    ACCESS_TOKEN = args.token or ""
    ALLOW_SHELL = args.allow_shell
    VERBOSE = args.verbose

    print("=" * 62)
    print("  %s v%s" % (APP_NAME, APP_VERSION))
    print("=" * 62)
    print("  iPhone Safari 打开：  http://%s:%d" % (lan_ip(), args.port))
    print("  本机打开：            http://127.0.0.1:%d" % args.port)
    print("  adb：                 %s" % (ADB_BIN or "未找到！" ))
    if not ADB_BIN:
        print()
        print(adb_help_text())
    print("  访问口令：            %s" % ("已启用" if ACCESS_TOKEN else "未启用（建议设置 --token）"))
    print("  自定义 shell：        %s" % ("已启用" if ALLOW_SHELL else "已关闭"))
    print()
    print("  提示：ADB over TCP/IP 明文且无认证，请只在可信 WiFi 下使用，")
    print("        不要把本服务或设备的 5555 端口暴露到公网。用完请关闭无线调试。")
    print("  停止服务：Ctrl+C")
    print("=" * 62)
    sys.stdout.flush()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
