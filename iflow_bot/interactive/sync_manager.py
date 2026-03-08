"""同步管理器。

协调会话监控、iflow 控制和企业微信渠道，实现双向同步。
"""

import asyncio
import time
from typing import Optional, Dict, Any
from loguru import logger

from iflow_bot.interactive.session_monitor import SessionMonitor
from iflow_bot.interactive.iflow_controller import IFlowController
from iflow_bot.config.schema import WechatWorkConfig
from iflow_bot.channels.wechat_work import WechatWorkChannel


class SyncManager:
    """同步管理器。
    
    协调各个组件，实现 iflow CLI 和企业微信的双向同步。
    注意：此管理器独立运行，不依赖 Gateway 的 MessageBus。
    """
    
    def __init__(
        self,
        workspace: str = "~/.iflow",
        tmux_session: str = "iflow",
        wechat_config: Optional[WechatWorkConfig] = None,
    ):
        """初始化同步管理器。
        
        Args:
            workspace: iflow 工作目录
            tmux_session: tmux 会话名称
            wechat_config: 企业微信配置（独立于 Gateway）
        """
        self.workspace = workspace
        self.tmux_session = tmux_session
        self.wechat_config = wechat_config
        
        self.monitor = SessionMonitor(workspace)
        self.controller = IFlowController(tmux_session)
        self.wechat_channel = None
        
        self.running = False
        self._tasks = []
        self._wechat_queue = asyncio.Queue()
        
        # 统计信息
        self.stats = {
            "messages_sent_to_iflow": 0,
            "messages_synced_to_wechat": 0,
            "errors": 0,
        }
    
    async def start(self, auto_start_iflow: bool = True) -> bool:
        """启动同步服务。
        
        Args:
            auto_start_iflow: 是否自动启动 iflow
            
        Returns:
            是否启动成功
        """
        if self.running:
            logger.warning("[SyncManager] Already running")
            return True
        
        logger.info("[SyncManager] Starting sync service...")
        
        # 检查 iflow 是否运行
        if not self.controller.check_iflow_running():
            if auto_start_iflow:
                logger.info("[SyncManager] iflow not running, starting...")
                if not self.controller.start_iflow():
                    logger.error("[SyncManager] Failed to start iflow")
                    return False
            else:
                logger.error("[SyncManager] iflow not running and auto_start disabled")
                return False
        
        # 初始化企业微信渠道
        if self.wechat_config and self.wechat_config.enabled:
            logger.info("[SyncManager] Initializing WeChat Work channel...")
            self.wechat_channel = WechatWorkChannel(
                config=self.wechat_config,
                bus=None,  # 独立运行，不使用 MessageBus
            )
            
            # 设置消息处理器
            self.wechat_channel.set_message_handler(
                lambda content, sender_id, chat_id, is_group, metadata:
                    self.receive_wechat_message(content, sender_id, chat_id, metadata)
            )
            
            # 启动企业微信渠道
            try:
                await self.wechat_channel.start()
                logger.info("[SyncManager] WeChat Work channel started")
            except Exception as e:
                logger.error(f"[SyncManager] Failed to start WeChat Work channel: {e}")
                self.wechat_channel = None
        else:
            logger.warning("[SyncManager] WeChat Work not configured or disabled, running without WeChat sync")
        
        # 查找会话文件
        if not self.monitor.find_latest_session():
            logger.warning("[SyncManager] No session file found, waiting...")
        
        self.running = True
        
        # 启动同步任务
        self._tasks = [
            asyncio.create_task(self._monitor_loop()),
            asyncio.create_task(self._wechat_loop()),
        ]
        
        logger.info("[SyncManager] Sync service started")
        return True
    
    async def stop(self) -> None:
        """停止同步服务。"""
        if not self.running:
            return
        
        logger.info("[SyncManager] Stopping sync service...")
        self.running = False
        
        # 取消所有任务
        for task in self._tasks:
            task.cancel()
        
        # 等待任务结束
        await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        
        # 停止企业微信渠道
        if self.wechat_channel:
            try:
                await self.wechat_channel.stop()
                logger.info("[SyncManager] WeChat Work channel stopped")
            except Exception as e:
                logger.error(f"[SyncManager] Error stopping WeChat Work channel: {e}")
        
        logger.info("[SyncManager] Sync service stopped")
        
        # 打印统计信息
        logger.info(f"[SyncManager] Stats: {self.stats}")
    
    async def _monitor_loop(self) -> None:
        """监控 iflow 输出循环。"""
        while self.running:
            try:
                # 检查是否应该读取新消息
                if self.monitor.should_check():
                    new_messages = self.monitor.read_new_assistant_messages()
                    
                    for msg in new_messages:
                        await self.send_to_wechat(msg["content"])
                        self.stats["messages_synced_to_wechat"] += 1
                
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SyncManager] Error in monitor loop: {e}")
                self.stats["errors"] += 1
                await asyncio.sleep(1)
    
    async def _wechat_loop(self) -> None:
        """企业微信消息处理循环。"""
        while self.running:
            try:
                # 从队列获取企业微信消息
                msg = await self._wechat_queue.get()
                
                if msg:
                    await self._send_to_iflow(msg)
                    self.stats["messages_sent_to_iflow"] += 1
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SyncManager] Error in wechat loop: {e}")
                self.stats["errors"] += 1
                await asyncio.sleep(1)
    
    async def send_to_wechat(self, content: str) -> None:
        """发送消息到企业微信。
        
        Args:
            content: 消息内容
        """
        if not self.wechat_channel:
            logger.debug("[SyncManager] WeChat Work channel not available, skipping send")
            return
        
        try:
            # 直接调用企业微信渠道的 send 方法
            await self.wechat_channel.send(content)
            logger.debug(f"[SyncManager] Sent to wechat: {content[:50]}...")
            
        except Exception as e:
            logger.error(f"[SyncManager] Failed to send to wechat: {e}")
            self.stats["errors"] += 1
    
    async def _send_to_iflow(self, msg: Dict[str, Any]) -> None:
        """发送消息到 iflow CLI。
        
        Args:
            msg: 企业微信消息（包含 content, chat_id 等字段）
        """
        try:
            content = msg.get("content", "").strip()
            chat_id = msg.get("chat_id", "")
            
            # 发送确认消息
            if self.wechat_channel:
                await self.wechat_channel.send(
                    f"✅ 已同步到 iflow CLI\n\n消息内容: {content[:100]}{'...' if len(content) > 100 else ''}"
                )
            
            # 注入到 iflow
            success = self.controller.send_message(content)
            
            if not success:
                logger.error(f"[SyncManager] Failed to inject message to iflow")
                
                # 发送失败通知
                if self.wechat_channel:
                    await self.wechat_channel.send(
                        "❌ 注入到 iflow 失败，请检查 iflow 是否正常运行"
                    )
                
                self.stats["errors"] += 1
            
            logger.debug(f"[SyncManager] Sent to iflow: {content[:50]}...")
            
        except Exception as e:
            logger.error(f"[SyncManager] Failed to send to iflow: {e}")
            self.stats["errors"] += 1
    
    def receive_wechat_message(self, content: str, sender_id: str, chat_id: str, metadata: Optional[dict] = None) -> None:
        """接收企业微信消息。
        
        由企业微信渠道调用此方法，将消息放入队列。
        
        Args:
            content: 消息内容
            sender_id: 发送者 ID
            chat_id: 聊天 ID
            metadata: 元数据
        """
        try:
            msg = {
                "content": content,
                "sender_id": sender_id,
                "chat_id": chat_id,
                "metadata": metadata or {},
            }
            self._wechat_queue.put_nowait(msg)
            logger.debug(f"[SyncManager] Received wechat message: {content[:50]}...")
        except Exception as e:
            logger.error(f"[SyncManager] Failed to queue wechat message: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息。
        
        Returns:
            统计信息字典
        """
        session_info = self.controller.get_session_info()
        
        return {
            **self.stats,
            "session_info": session_info,
            "session_file": str(self.monitor.session_file) if self.monitor.session_file else None,
            "wechat_enabled": self.wechat_channel is not None,
            "running": self.running,
        }