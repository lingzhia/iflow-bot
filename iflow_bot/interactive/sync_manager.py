"""同步管理器。

协调会话监控、iflow 控制和企业微信渠道，实现双向同步。
"""

import asyncio
import time
from typing import Optional, Dict, Any
from loguru import logger

from iflow_bot.interactive.session_monitor import SessionMonitor
from iflow_bot.interactive.iflow_controller import IFlowController
from iflow_bot.bus.queue import MessageBus
from iflow_bot.bus.events import OutboundMessage


class SyncManager:
    """同步管理器。
    
    协调各个组件，实现 iflow CLI 和企业微信的双向同步。
    """
    
    def __init__(
        self,
        workspace: str = "~/.iflow",
        tmux_session: str = "iflow",
        bus: Optional[MessageBus] = None,
        wechat_channel: Optional[str] = "wechat_work",
    ):
        """初始化同步管理器。
        
        Args:
            workspace: iflow 工作目录
            tmux_session: tmux 会话名称
            bus: 消息总线
            wechat_channel: 企业微信渠道名称
        """
        self.workspace = workspace
        self.tmux_session = tmux_session
        self.bus = bus
        self.wechat_channel = wechat_channel
        
        self.monitor = SessionMonitor(workspace)
        self.controller = IFlowController(tmux_session)
        
        self.running = False
        self._tasks = []
        
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
                        await self._send_to_wechat(msg)
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
        if not self.bus:
            logger.warning("[SyncManager] No message bus, skipping wechat loop")
            return
        
        while self.running:
            try:
                # 从消息总线获取企业微信消息
                msg = await self.bus.consume_inbound(timeout=1.0)
                
                if msg and msg.channel == self.wechat_channel:
                    await self._send_to_iflow(msg)
                    self.stats["messages_sent_to_iflow"] += 1
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SyncManager] Error in wechat loop: {e}")
                self.stats["errors"] += 1
                await asyncio.sleep(1)
    
    async def _send_to_wechat(self, message: Dict[str, Any]) -> None:
        """发送消息到企业微信。
        
        Args:
            message: iflow 回复消息
        """
        if not self.bus:
            return
        
        try:
            # 发送消息到企业微信
            await self.bus.publish_outbound(OutboundMessage(
                channel=self.wechat_channel,
                chat_id="",  # 从元数据中获取
                content=message["content"],
                metadata={
                    "source": "iflow_cli",
                    "message_id": message["id"],
                    "timestamp": message.get("timestamp"),
                },
            ))
            
            logger.debug(f"[SyncManager] Sent to wechat: {message['content'][:50]}...")
            
        except Exception as e:
            logger.error(f"[SyncManager] Failed to send to wechat: {e}")
            self.stats["errors"] += 1
    
    async def _send_to_iflow(self, msg) -> None:
        """发送消息到 iflow CLI。
        
        Args:
            msg: 企业微信消息
        """
        try:
            # 聚合多行消息
            content = msg.content.strip()
            
            # 发送确认消息
            if self.bus:
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=f"✅ 已同步到 iflow CLI\n\n消息内容: {content[:100]}{'...' if len(content) > 100 else ''}",
                    metadata={"is_confirmation": True},
                ))
            
            # 注入到 iflow
            success = self.controller.send_message(content)
            
            if not success:
                logger.error(f"[SyncManager] Failed to inject message to iflow")
                
                # 发送失败通知
                if self.bus:
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="❌ 注入到 iflow 失败，请检查 iflow 是否正常运行",
                        metadata={"is_error": True},
                    ))
                
                self.stats["errors"] += 1
            
            logger.debug(f"[SyncManager] Sent to iflow: {content[:50]}...")
            
        except Exception as e:
            logger.error(f"[SyncManager] Failed to send to iflow: {e}")
            self.stats["errors"] += 1
    
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
            "running": self.running,
        }