#!/bin/bash
# iflow-bot 管理脚本
# 用法: ./iflow-bot.sh [start|stop|restart|status] [--workspace <path>]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 默认配置
DEFAULT_WORKSPACE="$HOME/.iflow-bot/workspace"
PID_FILE="$HOME/.iflow-bot/gateway.pid"
LOG_FILE="$HOME/.iflow-bot/gateway.log"

# 打印 Banner
print_banner() {
    echo -e "${CYAN}"
    echo "  /$$ /$$$$$$$$ /$$                                 /$$$$$$$              /$$    "
    echo " |__/| $$_____/| $$                                | \$\$__  \$\$            | \$\$    "
    echo "  /$$| $$      | \$\$  /$$$$$$  /$$  /$$  /$$        | \$\$  \ \$\$  /$$$$$$  /$$$$$$  "
    echo " | \$\$| \$\$\$\$\$   | \$\$ /\$\$__  \$\$| \$\$ | \$\$ | \$\$ /$$$$\$\$| \$\$\$\$\$\$\$  /\$\$__  \$\$|_  \$\$_/  "
    echo " | \$\$| \$\$__    | \$\$| \$\$  \ \$\$| \$\$ | \$\$ | \$\$|______/| \$\$__  \$\$| \$\$  \ \$\$  | \$\$    "
    echo " | \$\$| \$\$      | \$\$| \$\$  | \$\$| \$\$ | \$\$ | \$\$        | \$\$  \ \$\$| \$\$  | \$\$  | \$\$ /\$\$"
    echo " | \$\$| \$\$      | \$\$|  \$\$\$\$\$\$/|  \$\$\$\$\$/ \$\$\$\$/        | \$\$\$\$\$\$\$/|  \$\$\$\$\$/  |  \$\$\$\$/"
    echo " |__/|__/      |__/ \______/  \_____/\___/         |_______/  \______/    \___/  "
    echo -e "${NC}"
    echo -e "  ${GREEN}Multi-channel AI Assistant (powered by iflow)${NC}"
    echo
}

# 打印帮助
print_help() {
    echo "用法: $0 [命令] [选项]"
    echo
    echo "Gateway 服务命令:"
    echo "  start [--workspace <path>]  启动 Gateway 服务（可指定工作目录）"
    echo "  stop                        停止服务"
    echo "  restart [--workspace <path>] 重启服务"
    echo "  status                      查看服务状态"
    echo "  logs                        查看日志（tail -f）"
    echo
    echo "Interactive 模式命令:"
    echo "  interactive start [--session <name>]  启动 iflow CLI 交互模式"
    echo "  interactive status [--session <name>]  查看 iflow CLI 交互模式状态"
    echo "  interactive stop [--session <name>]   停止 iflow CLI 交互模式"
    echo
    echo "通用:"
    echo "  help                        显示帮助信息"
    echo
    echo "选项:"
    echo "  --workspace, -w <path>      指定工作目录（默认: ~/.iflow-bot/workspace）"
    echo "  --daemon, -d                后台运行（默认）"
    echo "  --foreground, -f            前台运行（调试模式）"
    echo "  --session, -s <name>        指定 tmux 会话名称（默认: iflow）"
    echo
    echo "示例:"
    echo "  $0 start                              # 启动 Gateway 服务"
    echo "  $0 interactive start                  # 启动 iflow CLI 交互模式"
    echo "  $0 interactive start -s my-session    # 启动交互模式，指定会话名"
    echo "  $0 stop                               # 停止服务"
    echo "  $0 status                             # 查看状态"
}

# 检查服务是否运行
is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

# 获取 PID
get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE" 2>/dev/null
    fi
}

# 启动服务
do_start() {
    local workspace=""
    local daemon=true
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --workspace|-w)
                workspace="$2"
                shift 2
                ;;
            --foreground|-f)
                daemon=false
                shift
                ;;
            --daemon|-d)
                daemon=true
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
    
    # 设置工作目录
    if [ -n "$workspace" ]; then
        # 展开波浪号
        workspace="${workspace/#\~/$HOME}"
        export IFLOW_BOT_WORKSPACE="$workspace"
    fi
    
    print_banner
    
    # 检查是否已运行
    if is_running; then
        echo -e "${YELLOW}服务已在运行中 (PID: $(get_pid))${NC}"
        echo "使用 $0 restart 重启服务"
        exit 0
    fi
    
    # 清理旧 PID 文件
    [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
    
    # 创建日志目录
    mkdir -p "$(dirname "$LOG_FILE")"
    
    if [ "$daemon" = true ]; then
        # 后台启动
        echo -e "${CYAN}正在启动 iflow-bot...${NC}"
        
        if [ -n "$workspace" ]; then
            echo -e "工作目录: ${CYAN}$workspace${NC}"
            # 更新配置文件中的 workspace
            python3 -c "
import json
from pathlib import Path
config_path = Path.home() / '.iflow-bot' / 'config.json'
if config_path.exists():
    with open(config_path, 'r') as f:
        config = json.load(f)
else:
    config = {}
config['workspace'] = '$workspace'
config_path.parent.mkdir(parents=True, exist_ok=True)
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
" 2>/dev/null || true
        fi
        
        # 后台运行启动命令
        python3 -m iflow_bot.cli.commands gateway start --daemon > "$LOG_FILE" 2>&1 &
        local bg_pid=$!
        
        # 等待 PID 文件创建（最多等待 30 秒）
        local count=0
        while [ $count -lt 30 ]; do
            if [ -f "$PID_FILE" ]; then
                break
            fi
            sleep 1
            count=$((count + 1))
        done
        
        # 等待服务完全启动
        sleep 2
        
        if is_running; then
            echo -e "${GREEN}✓ iflow-bot 已启动 (PID: $(get_pid))${NC}"
            echo -e "日志文件: ${CYAN}$LOG_FILE${NC}"
        else
            echo -e "${RED}✗ iflow-bot 启动失败，请查看日志${NC}"
            echo -e "日志文件: ${CYAN}$LOG_FILE${NC}"
            exit 1
        fi
    else
        # 前台运行
        if [ -n "$workspace" ]; then
            echo -e "工作目录: ${CYAN}$workspace${NC}"
            python3 -c "
import json
from pathlib import Path
config_path = Path.home() / '.iflow-bot' / 'config.json'
if config_path.exists():
    with open(config_path, 'r') as f:
        config = json.load(f)
else:
    config = {}
config['workspace'] = '$workspace'
config_path.parent.mkdir(parents=True, exist_ok=True)
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
" 2>/dev/null || true
        fi
        python3 -m iflow_bot.cli.commands gateway run
    fi
}

# 停止服务
do_stop() {
    echo -e "${CYAN}正在停止 iflow-bot...${NC}"
    
    if ! is_running; then
        echo -e "${YELLOW}服务未运行${NC}"
        [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
        exit 0
    fi
    
    local pid=$(get_pid)
    
    # 发送企业微信停止通知
    _send_wechat_shutdown_notification
    
    # 发送 SIGTERM
    kill "$pid" 2>/dev/null
    
    # 等待进程结束
    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
        sleep 1
        count=$((count + 1))
    done
    
    # 如果还在运行，强制终止
    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${YELLOW}正在强制终止...${NC}"
        kill -9 "$pid" 2>/dev/null
    fi
    
    rm -f "$PID_FILE"
    echo -e "${GREEN}✓ iflow-bot 已停止${NC}"
}

# 发送企业微信停止通知
_send_wechat_shutdown_notification() {
    local config_file="$HOME/.iflow-bot/config.json"
    
    if [ ! -f "$config_file" ]; then
        return
    fi
    
    # 检查企业微信是否启用
    local enabled=$(python3 -c "
import json
with open('$config_file', 'r') as f:
    config = json.load(f)
print(config.get('channels', {}).get('wechat_work', {}).get('enabled', False))
" 2>/dev/null || echo "False")
    
    if [ "$enabled" != "True" ]; then
        return
    fi
    
    # 获取企业微信配置
    local corp_id=$(python3 -c "
import json
with open('$config_file', 'r') as f:
    config = json.load(f)
print(config.get('channels', {}).get('wechat_work', {}).get('corp_id', ''))
" 2>/dev/null)
    
    local secret=$(python3 -c "
import json
with open('$config_file', 'r') as f:
    config = json.load(f)
print(config.get('channels', {}).get('wechat_work', {}).get('secret', ''))
" 2>/dev/null)
    
    local agent_id=$(python3 -c "
import json
with open('$config_file', 'r') as f:
    config = json.load(f)
print(config.get('channels', {}).get('wechat_work', {}).get('agent_id', ''))
" 2>/dev/null)
    
    if [ -z "$corp_id" ] || [ -z "$secret" ] || [ -z "$agent_id" ]; then
        return
    fi
    
    # 发送停止通知
    python3 -c "
import asyncio
import httpx
from datetime import datetime

async def send_shutdown_notification():
    try:
        # 获取 access_token
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                'https://qyapi.weixin.qq.com/cgi-bin/gettoken',
                params={
                    'corpid': '$corp_id',
                    'corpsecret': '$secret',
                }
            )
            data = resp.json()
            if data.get('errcode', 0) != 0:
                return
            
            token = data.get('access_token')
            
            # 发送通知消息
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            msg_data = {
                'touser': '@all',
                'msgtype': 'markdown',
                'agentid': int('$agent_id'),
                'markdown': {
                    'content': f'**iFlow-Bot 服务已停止** 👋\n\n时间: {now}\n\n服务已关闭，期待下次见面！'
                },
                'safe': 0,
            }
            
            resp = await client.post(
                f'https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}',
                json=msg_data
            )
            result = resp.json()
            if result.get('errcode', 0) != 0:
                print(f'Failed to send notification: {result.get(\"errmsg\")}')
    except Exception as e:
        print(f'Failed to send shutdown notification: {e}')

asyncio.run(send_shutdown_notification())
" 2>/dev/null
}

# 重启服务
do_restart() {
    do_stop
    echo
    do_start "$@"
}

# 查看状态
do_status() {
    print_banner
    
    echo -e "${BOLD}服务状态:${NC}"
    if is_running; then
        echo -e "  Gateway: ${GREEN}运行中${NC} (PID: $(get_pid))"
    else
        echo -e "  Gateway: ${YELLOW}未运行${NC}"
    fi
    
    echo
    
    # 显示配置信息
    echo -e "${BOLD}配置信息:${NC}"
    local config_file="$HOME/.iflow-bot/config.json"
    if [ -f "$config_file" ]; then
        local workspace=$(python3 -c "
import json
with open('$config_file', 'r') as f:
    config = json.load(f)
print(config.get('workspace', '$DEFAULT_WORKSPACE'))
" 2>/dev/null || echo "$DEFAULT_WORKSPACE")
        local model=$(python3 -c "
import json
with open('$config_file', 'r') as f:
    config = json.load(f)
print(config.get('model', '未知'))
" 2>/dev/null || echo "未知")
        
        echo -e "  配置文件: ${CYAN}$config_file${NC}"
        echo -e "  工作目录: ${CYAN}$workspace${NC}"
        echo -e "  模型: ${CYAN}$model${NC}"
    else
        echo -e "  配置文件: ${YELLOW}未创建${NC}"
    fi
    
    echo
    
    # 显示启用的渠道
    echo -e "${BOLD}启用的渠道:${NC}"
    python3 -c "
import json
config_path = '$HOME/.iflow-bot/config.json'
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
    channels = config.get('channels', {})
    enabled = [name for name, cfg in channels.items() if cfg.get('enabled', False)]
    if enabled:
        print('  ' + ', '.join(enabled))
    else:
        print('  无')
except:
    print('  无法读取')
" 2>/dev/null || echo "  无法读取"
}

# 查看日志
do_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}日志文件不存在: $LOG_FILE${NC}"
        exit 1
    fi
    
    echo -e "${CYAN}日志文件: $LOG_FILE${NC}"
    echo -e "${CYAN}按 Ctrl+C 退出${NC}"
    echo
    tail -f "$LOG_FILE"
}

# ============================================================================
# Interactive 模式命令
# ============================================================================

do_interactive_start() {
    local session="iflow"
    local workspace="$HOME/.iflow"
    local auto_start=true
    local model="kimi-k2.5"
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --session|-s)
                session="$2"
                shift 2
                ;;
            --workspace|-w)
                workspace="$2"
                shift 2
                ;;
            --model|-m)
                model="$2"
                shift 2
                ;;
            --no-auto-start)
                auto_start=false
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
    
    print_banner
    echo -e "${CYAN}启动 iflow CLI 交互模式...${NC}"
    echo
    echo -e "tmux 会话: ${CYAN}$session${NC}"
    echo -e "工作目录: ${CYAN}$workspace${NC}"
    echo -e "模型: ${CYAN}$model${NC}"
    echo
    
    python3 -m iflow_bot.cli.commands interactive start \
        --session "$session" \
        --workspace "$workspace" \
        --model "$model" \
        $([ "$auto_start" = true ] && echo "--auto-start" || echo "--no-auto-start")
}

do_interactive_status() {
    local session="iflow"
    local workspace="$HOME/.iflow"
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --session|-s)
                session="$2"
                shift 2
                ;;
            --workspace|-w)
                workspace="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    
    python3 -m iflow_bot.cli.commands interactive status \
        --session "$session" \
        --workspace "$workspace"
}

do_interactive_stop() {
    local session="iflow"
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --session|-s)
                session="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    
    python3 -m iflow_bot.cli.commands interactive stop \
        --session "$session"
}

# 主入口
case "${1:-help}" in
    start)
        shift
        do_start "$@"
        ;;
    stop)
        do_stop
        ;;
    restart)
        shift
        do_restart "$@"
        ;;
    status)
        do_status
        ;;
    logs)
        do_logs
        ;;
    interactive)
        shift
        case "${1:-help}" in
            start)
                shift
                do_interactive_start "$@"
                ;;
            status)
                shift
                do_interactive_status "$@"
                ;;
            stop)
                shift
                do_interactive_stop "$@"
                ;;
            *)
                echo -e "${RED}未知命令: $0 interactive $1${NC}"
                echo
                echo "用法: $0 interactive [start|status|stop] [选项]"
                exit 1
                ;;
        esac
        ;;
    help|--help|-h)
        print_banner
        print_help
        ;;
    *)
        echo -e "${RED}未知命令: $1${NC}"
        echo
        print_help
        exit 1
        ;;
esac
