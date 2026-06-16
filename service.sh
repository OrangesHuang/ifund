#!/usr/bin/env bash
# iFund 后端常驻服务管理（macOS launchd）。
#
# 只让「后端 :8000」常驻——它已服务打包后的前端（backend/static），OpenClaw 也只依赖它；
# 前端 :9000 dev 仅调试热更新用，常驻不需要。用 waitress 跑生产 WSGI，launchd 负责
# 「登录自启 + 崩溃自动重启」。
#
# 用法：
#   ./service.sh install     安装并启动常驻（生成 LaunchAgent + 加载，开机自启）
#   ./service.sh start       启动常驻
#   ./service.sh stop        停止常驻（调试前用：腾出 :8000 给 start.sh）
#   ./service.sh restart     重启常驻（改了后端代码、想让常驻生效时用）
#   ./service.sh status      查看运行状态
#   ./service.sh logs        跟踪日志（Ctrl-C 退出）
#   ./service.sh uninstall   卸载常驻（移除 LaunchAgent）
#
# 日常调试：./service.sh stop  →  ./start.sh （照常热重载）→ 调完 Ctrl-C  →  ./service.sh start
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
WAITRESS="$BACKEND/venv/bin/waitress-serve"
PORT=8000
LABEL="com.ifund.backend"
UID_NUM="$(id -u)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGDIR="$ROOT/logs"
DOMAIN="gui/$UID_NUM"

write_plist() {
  mkdir -p "$LOGDIR" "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$WAITRESS</string>
    <string>--listen=127.0.0.1:$PORT</string>
    <string>app.main:app</string>
  </array>
  <key>WorkingDirectory</key><string>$BACKEND</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOGDIR/backend.out.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/backend.err.log</string>
  <key>EnvironmentVariables</key>
  <dict><key>PYTHONUNBUFFERED</key><string>1</string></dict>
</dict>
</plist>
PLIST
}

case "${1:-}" in
  install)
    [ -x "$WAITRESS" ] || { echo "缺少 waitress，先装：$BACKEND/venv/bin/pip install -r $BACKEND/requirements.txt"; exit 1; }
    write_plist
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    echo "已安装并启动常驻：http://127.0.0.1:$PORT （开机自启 + 崩溃自动重启）"
    echo "日志：$LOGDIR/backend.{out,err}.log"
    ;;
  start)
    [ -f "$PLIST" ] || { echo "尚未 install，请先：./service.sh install"; exit 1; }
    launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null || launchctl kickstart "$DOMAIN/$LABEL"
    echo "常驻已启动：http://127.0.0.1:$PORT"
    ;;
  stop)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null && echo "常驻已停止（:$PORT 已释放，可用 ./start.sh 调试）" || echo "常驻未在运行"
    ;;
  restart)
    [ -f "$PLIST" ] || { echo "尚未 install"; exit 1; }
    launchctl kickstart -k "$DOMAIN/$LABEL" && echo "常驻已重启"
    ;;
  status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      echo "● 已加载（launchd 管理中）"
      launchctl print "$DOMAIN/$LABEL" | grep -E "state =|pid =" | sed 's/^/  /'
    else
      echo "○ 未加载"
    fi
    curl -s -o /dev/null -w "  探测 :$PORT -> HTTP %{http_code}\n" "http://127.0.0.1:$PORT/api/fund/types" 2>/dev/null || echo "  :$PORT 无响应"
    ;;
  logs)
    tail -f "$LOGDIR/backend.out.log" "$LOGDIR/backend.err.log"
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "已卸载常驻（LaunchAgent 已移除）。logs/ 保留。"
    ;;
  *)
    echo "用法：./service.sh {install|start|stop|restart|status|logs|uninstall}"
    exit 1
    ;;
esac
