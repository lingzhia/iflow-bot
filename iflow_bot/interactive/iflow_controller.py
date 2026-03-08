"""iflow CLI 控制器。

通过 tmux send-keys 向 iflow CLI 注入消息。
"""

import subprocess
import shlex
import time
from typing import Optional
from loguru import logger


class IFlowController:
    """iflow CLI 控制器。
    
    通过 tmux send-keys 命令向 iflow CLI 会话注入消息。
    """
    
    def __init__(self, tmux_session: str = "iflow"):
        """初始化 iflow 控制器。
        
        Args:
            tmux_session: tmux 会话名称
        """
        self.tmux_session = tmux_session
        
    def check_tmux_session(self) -> bool:
        """检查 tmux 会话是否存在。
        
        Returns:
            会话是否存在
        """
        try:
            result = subprocess.run(
                ["tmux", "has-session", "-t", self.tmux_session],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"[IFlowController] Error checking tmux session: {e}")
            return False
    
    def check_iflow_running(self) -> bool:
        """检查 iflow CLI 是否在运行。
        
        Returns:
            iflow 是否运行
        """
        if not self.check_tmux_session():
            return False
        
        try:
            # 检查会话中是否有 iflow 进程
            result = subprocess.run(
                ["tmux", "list-panes", "-t", self.tmux_session, "-F", "#{pane_pid}"],
                capture_output=True,
                timeout=5,
                text=True
            )
            
            if result.returncode == 0 and result.stdout.strip():
                pane_pid = result.stdout.strip()
                
                # 检查进程命令是否包含 iflow
                try:
                    with open(f"/proc/{pane_pid}/cmdline", "r") as f:
                        cmdline = f.read()
                        if "iflow" in cmdline.lower():
                            return True
                except:
                    pass
            
            return False
        except Exception as e:
            logger.warning(f"[IFlowController] Error checking iflow status: {e}")
            return False
    
    def send_message(self, message: str) -> bool:
        """发送消息到 iflow CLI。
        
        Args:
            message: 要发送的消息
            
        Returns:
            是否发送成功
        """
        if not self.check_tmux_session():
            logger.error(f"[IFlowController] tmux session '{self.tmux_session}' not found")
            return False
        
        try:
            # 转义单引号（tmux 使用单引号）
            escaped_message = message.replace("'", "'\\''")
            
            # 分两次发送：先发送消息内容，再发送回车键
            subprocess.run(
                ["tmux", "send-keys", "-t", self.tmux_session, escaped_message],
                capture_output=True,
                timeout=5
            )
            
            # 发送回车键
            result = subprocess.run(
                ["tmux", "send-keys", "-t", self.tmux_session, "C-m"],
                capture_output=True,
                timeout=5
            )
            
            if result.returncode != 0:
                logger.error(f"[IFlowController] Failed to send message: {result.stderr.decode()}")
                return False
            
            logger.debug(f"[IFlowController] Message sent to iflow: {message[:50]}...")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("[IFlowController] Timeout sending message")
            return False
        except Exception as e:
            logger.error(f"[IFlowController] Error sending message: {e}")
            return False
    
    def start_iflow(self, model: str = "kimi-k2.5") -> bool:
        """在 tmux 会话中启动 iflow CLI。
        
        Args:
            model: iflow 模型
            
        Returns:
            是否启动成功
        """
        if self.check_tmux_session():
            logger.warning(f"[IFlowController] tmux session '{self.tmux_session}' already exists")
            if self.check_iflow_running():
                logger.info("[IFlowController] iflow already running")
                return True
        
        try:
            # 创建新的 tmux 会话并启动 iflow
            cmd = [
                "tmux",
                "new-session",
                "-d",
                "-s",
                self.tmux_session,
                f"iflow --model {model}"
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"[IFlowController] Failed to start iflow: {result.stderr.decode()}")
                return False
            
            logger.info(f"[IFlowController] iflow started in tmux session '{self.tmux_session}'")
            
            # 等待 iflow 启动
            time.sleep(2)
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("[IFlowController] Timeout starting iflow")
            return False
        except Exception as e:
            logger.error(f"[IFlowController] Error starting iflow: {e}")
            return False
    
    def stop_iflow(self) -> bool:
        """停止 iflow CLI。
        
        Returns:
            是否停止成功
        """
        if not self.check_tmux_session():
            logger.info(f"[IFlowController] tmux session '{self.tmux_session}' not found")
            return True
        
        try:
            # 关闭 tmux 会话
            result = subprocess.run(
                ["tmux", "kill-session", "-t", self.tmux_session],
                capture_output=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.warning(f"[IFlowController] Failed to kill session: {result.stderr.decode()}")
                return False
            
            logger.info(f"[IFlowController] tmux session '{self.tmux_session}' killed")
            return True
            
        except Exception as e:
            logger.error(f"[IFlowController] Error stopping iflow: {e}")
            return False
    
    def get_session_info(self) -> Optional[dict]:
        """获取会话信息。
        
        Returns:
            会话信息字典，如果获取失败则返回 None
        """
        try:
            info = {
                "tmux_session": self.tmux_session,
                "tmux_exists": self.check_tmux_session(),
                "iflow_running": False,
            }
            
            # 只有当 tmux 会话存在时才检查 iflow
            if info["tmux_exists"]:
                info["iflow_running"] = self.check_iflow_running()
            
            return info
        except Exception as e:
            logger.error(f"[IFlowController] Error getting session info: {e}")
            return None