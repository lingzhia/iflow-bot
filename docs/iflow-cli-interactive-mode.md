# iFlow CLI 交互模式方案

## 需求描述

在 SSH 终端中启动 iflow-bot 时，能够：
1. 显示 iflow CLI 的原生对话界面
2. 后台同时保持与企业微信的交互
3. 企业微信消息自动填充到 iflow 对话框
4. iflow 的回复自动发送给企业微信
5. 可以在命令行界面直接操作 iflow 对话
6. 命令行输入的消息也能发送给企业微信

## 技术方案

### 使用 pexpect 库实现

pexpect 是一个 Python 库，用于控制和自动化其他程序。它可以：
- 启动子程序（如 iflow CLI）
- 向子程序发送输入
- 捕获子程序的输出
- 在伪终端（PTY）中运行程序，保持交互式

### 核心思路

1. 使用 `pexpect.spawn()` 启动 iflow CLI
2. 将 iflow CLI 的输出实时显示到终端
3. 将用户的终端输入传递给 iflow CLI
4. 企业微信消息通过 `pexpect.send()` 输入到 iflow CLI
5. 捕获 iflow CLI 的输出，解析 AI 回复
6. 将 AI 回复发送给企业微信

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                     SSH 终端 (XShell)                         │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              iflow CLI 界面                           │  │
│  │  > 你好                                                │  │
│  │  你好！有什么可以帮你的吗？                              │  │
│  │  > _                                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│        ↑ 输出显示            ↑ 用户输入                      │
└────────┼────────────────────┼──────────────────────────────┘
         │                    │
         │ pexpect            │ stdin/stdout
         ↓                    ↓
┌─────────────────────────────────────────────────────────────┐
│                  pexpect 子进程 (iflow CLI)                  │
│                                                              │
│  接收输入 → 处理 → 生成回复                                   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
         ↑ 输出              ↑ 输入
         │                  │
         │ 解析             │ send()
         │                  │
┌────────┴──────────────────┴──────────────────────────────────┐
│              后台协调程序 (Python)                            │
│                                                              │
│  1. 监听企业微信消息                                          │
│  2. 将消息 send() 到 iflow CLI                               │
│  3. 捕获 iflow CLI 输出                                      │
│  4. 解析 AI 回复                                             │
│  5. 发送回复到企业微信                                        │
│  6. 将终端输入转发到 iflow CLI                               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
         ↑ 消息              ↓ 回复
         │                  │
┌────────┴──────────────────┴──────────────────────────────────┐
│                   企业微信 API                                 │
│                                                              │
│  接收消息 ←→ 用户 ←→ 发送回复                                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## 实现步骤

### 1. 安装依赖

```bash
pip install pexpect
```

### 2. 创建新的 CLI 命令

在 `iflow_bot/cli/commands.py` 中添加新命令：

```python
@app.command(name="interactive")
def interactive_mode(
    workspace: str = typer.Option(None, "--workspace", "-w", help="工作目录"),
    model: str = typer.Option(None, "--model", "-m", help="模型名称"),
) -> None:
    """启动 iflow CLI 交互模式（支持企业微信）"""
    from iflow_bot.interactive.session import InteractiveSession
    
    config = load_config()
    workspace = workspace or config.get_workspace()
    model = model or config.get_model()
    
    session = InteractiveSession(
        workspace=Path(workspace),
        model=model,
        config=config,
    )
    
    console.print(f"[green]✓[/green] iFlow CLI 交互模式启动中...")
    console.print(f"[dim]Workspace: {workspace}[/dim]")
    console.print(f"[dim]Model: {model}[/dim]")
    console.print(f"[dim]企业微信: {'启用' if config.channels.wechat_work.enabled else '禁用'}[/dim]")
    console.print()
    
    try:
        asyncio.run(session.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]正在退出...[/yellow]")
```

### 3. 创建 InteractiveSession 类

创建新文件 `iflow_bot/interactive/session.py`：

```python
import asyncio
import pexpect
from pathlib import Path
from typing import Optional
from loguru import logger

from iflow_bot.config.schema import Config
from iflow_bot.channels.wechat_work import WechatWorkChannel
from iflow_bot.bus import MessageBus, InboundMessage, OutboundMessage


class InteractiveSession:
    """iflow CLI 交互模式会话"""
    
    def __init__(
        self,
        workspace: Path,
        model: str,
        config: Config,
    ):
        self.workspace = workspace
        self.model = model
        self.config = config
        
        # pexpect 进程
        self.iflow_proc: Optional[pexpect.spawn] = None
        
        # 消息总线
        self.bus = MessageBus()
        
        # 企业微信渠道
        self.wechat_channel: Optional[WechatWorkChannel] = None
        
        # 运行状态
        self.running = False
        
        # 最后一条回复内容
        self.last_response = ""
    
    async def run(self):
        """运行交互模式"""
        self.running = True
        
        # 启动 iflow CLI
        self._start_iflow_cli()
        
        # 启动企业微信渠道（如果启用）
        if self.config.channels.wechat_work.enabled:
            await self._start_wechat_channel()
        
        # 启动输入输出处理
        await asyncio.gather(
            self._handle_iflow_output(),
            self._handle_user_input(),
            self._handle_wechat_messages(),
        )
    
    def _start_iflow_cli(self):
        """启动 iflow CLI"""
        cmd = f"cd {self.workspace} && iflow --model {self.model}"
        self.iflow_proc = pexpect.spawn(cmd, encoding='utf-8', timeout=None)
        logger.info(f"iflow CLI started: pid={self.iflow_proc.pid}")
    
    async def _start_wechat_channel(self):
        """启动企业微信渠道"""
        self.wechat_channel = WechatWorkChannel(
            config=self.config.channels.wechat_work,
            bus=self.bus,
        )
        await self.wechat_channel.start()
        logger.info("WeChat Work channel started")
    
    async def _handle_iflow_output(self):
        """处理 iflow CLI 输出"""
        while self.running:
            try:
                # 读取 iflow 输出
                if self.iflow_proc:
                    line = self.iflow_proc.readline()
                    if line:
                        # 显示到终端
                        print(line, end='', flush=True)
                        
                        # 捕获回复内容
                        self._capture_response(line)
            except Exception as e:
                logger.error(f"Error handling iflow output: {e}")
                await asyncio.sleep(0.1)
    
    async def _handle_user_input(self):
        """处理用户输入"""
        import sys
        
        while self.running:
            try:
                # 读取用户输入
                line = sys.stdin.readline()
                if line:
                    # 发送到 iflow CLI
                    if self.iflow_proc:
                        self.iflow_proc.send(line)
                    
                    # 发送到企业微信（如果启用）
                    if self.wechat_channel:
                        await self.bus.publish_inbound(InboundMessage(
                            channel="wechat_work",
                            chat_id="YuLingZhi",  # 默认用户
                            sender="local_user",
                            content=line.strip(),
                            msg_type="text",
                        ))
            except Exception as e:
                logger.error(f"Error handling user input: {e}")
                await asyncio.sleep(0.1)
    
    async def _handle_wechat_messages(self):
        """处理企业微信消息"""
        if not self.wechat_channel:
            return
        
        while self.running:
            try:
                # 从消息总线接收消息
                msg = await self.bus.inbound_queue.get()
                
                if msg.channel == "wechat_work":
                    # 发送到 iflow CLI
                    if self.iflow_proc:
                        self.iflow_proc.send(msg.content + '\n')
                        print(f"\n[企业微信 {msg.sender}]: {msg.content}\n> ", end='', flush=True)
                    
                    # 记录最后一条回复，用于发送回企业微信
                    self.last_response = ""
                    
            except Exception as e:
                logger.error(f"Error handling wechat message: {e}")
                await asyncio.sleep(0.1)
    
    def _capture_response(self, line: str):
        """捕获 iflow 的回复内容"""
        # 这里需要解析 iflow 的输出，识别 AI 的回复
        # 简单实现：捕获以特定标记开头的行
        # 实际需要更复杂的解析逻辑
        
        # 检测是否是 AI 回复（假设 AI 回复以特定字符开头）
        if line.strip() and not line.startswith('>'):
            self.last_response += line
            
            # 如果回复结束，发送到企业微信
            if self.wechat_channel and self._is_response_complete(line):
                asyncio.create_task(self._send_to_wechat(self.last_response))
                self.last_response = ""
    
    def _is_response_complete(self, line: str) -> bool:
        """判断回复是否完成"""
        # 这里需要根据 iflow CLI 的输出格式来判断
        # 例如：检测到新的提示符 "> "
        return '> ' in line or line.strip().endswith('>')
    
    async def _send_to_wechat(self, content: str):
        """发送回复到企业微信"""
        if not self.wechat_channel:
            return
        
        # 解析回复内容，提取 AI 的消息
        response_text = self._extract_ai_message(content)
        
        if response_text:
            await self.bus.publish_outbound(OutboundMessage(
                channel="wechat_work",
                chat_id="YuLingZhi",
                content=response_text,
            ))
    
    def _extract_ai_message(self, content: str) -> str:
        """从 iflow 输出中提取 AI 的回复消息"""
        # 这里需要根据 iflow CLI 的输出格式来提取
        # 简单实现：移除控制字符和提示符
        
        # 移除提示符
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            if not line.startswith('>') and line.strip():
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()
    
    async def stop(self):
        """停止会话"""
        self.running = False
        
        if self.iflow_proc:
            self.iflow_proc.terminate()
        
        if self.wechat_channel:
            await self.wechat_channel.stop()
```

### 4. 添加到管理脚本

在 `iflow-bot.sh` 中添加交互模式启动：

```bash
# 交互模式启动
do_interactive() {
    local workspace=""
    local model=""
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --workspace|-w)
                workspace="$2"
                shift 2
                ;;
            --model|-m)
                model="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    
    echo -e "${CYAN}正在启动 iflow CLI 交互模式...${NC}"
    
    # 构建命令
    cmd="python3 -m iflow_bot.cli.commands interactive"
    
    if [ -n "$workspace" ]; then
        cmd="$cmd --workspace $workspace"
        echo -e "工作目录: ${CYAN}$workspace${NC}"
    fi
    
    if [ -n "$model" ]; then
        cmd="$cmd --model $model"
        echo -e "模型: ${CYAN}$model${NC}"
    fi
    
    # 前台运行
    exec python3 -m iflow_bot.cli.commands interactive ${workspace:+--workspace "$workspace"} ${model:+--model "$model"}
}
```

## 使用方法

### 启动交互模式

```bash
# 使用默认配置启动
python3 -m iflow_bot.cli.commands interactive

# 指定工作目录
python3 -m iflow_bot.cli.commands interactive --workspace /opt/MyGitCode/LingQuant

# 指定模型
python3 -m iflow_bot.cli.commands interactive --model GLM-5

# 同时指定工作目录和模型
python3 -m iflow_bot.cli.commands interactive -w /opt/MyGitCode/LingQuant -m GLM-5
```

### 交互方式

1. **终端输入**：直接在命令行输入消息，按 Enter 发送给 iflow
2. **企业微信消息**：通过企业微信发送的消息会自动输入到 iflow CLI
3. **查看回复**：AI 的回复会显示在终端，同时发送到企业微信

### 退出

按 `Ctrl+C` 退出交互模式

## 注意事项

### 1. 输出解析

iflow CLI 的输出格式需要仔细解析，包括：
- 提示符 `>`
- 思考过程
- 工具调用
- 最终回复

需要根据实际的 iflow CLI 输出格式调整解析逻辑。

### 2. 消息同步

需要确保：
- 企业微信消息及时输入到 iflow CLI
- AI 回复准确发送到企业微信
- 避免消息重复或丢失

### 3. 错误处理

需要处理：
- iflow CLI 崩溃或退出
- 企业微信连接断开
- 网络超时
- 输入输出冲突

### 4. 性能优化

- 使用异步 I/O 提高性能
- 避免阻塞主线程
- 合理处理消息队列

## 未来改进

1. **支持更多渠道**：不仅限于企业微信，支持其他即时通讯渠道
2. **消息历史**：保存消息历史，支持回看
3. **富文本支持**：支持 markdown、代码块等格式
4. **多用户支持**：支持多个企业微信用户同时交互
5. **会话管理**：支持多会话切换和管理

## 参考资料

- pexpect 官方文档：https://pexpect.readthedocs.io/
- iflow CLI 文档：https://iflow.ai/docs
- Python 异步编程：https://docs.python.org/3/library/asyncio.html