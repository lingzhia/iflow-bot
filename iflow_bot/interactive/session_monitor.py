"""iflow 会话文件监控器。

监控 iflow CLI 的会话文件，实时读取 AI 回复。
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from loguru import logger


class SessionMonitor:
    """监控 iflow CLI 会话文件。
    
    通过监控 iflow 的会话文件（session-{id}.jsonl），
    实时读取新增的 AI 回复消息。
    """
    
    def __init__(self, workspace: str = "~/.iflow"):
        """初始化会话监控器。
        
        Args:
            workspace: iflow 工作目录路径
        """
        self.workspace = Path(workspace).expanduser()
        self.session_file: Optional[Path] = None
        self.last_position = 0
        self.processed_ids = set()
        self.last_check_time = 0
        self.check_interval = 0.5  # 检查间隔（秒）
        
    def find_latest_session(self) -> Optional[Path]:
        """查找最新的会话文件。
        
        Returns:
            最新的会话文件路径，如果没有找到则返回 None
        """
        projects_dir = self.workspace / "projects"
        if not projects_dir.exists():
            logger.warning(f"[SessionMonitor] Projects directory not found: {projects_dir}")
            return None
            
        # 查找所有会话文件
        session_files = list(projects_dir.glob("*/session-*.jsonl"))
        if not session_files:
            logger.warning("[SessionMonitor] No session files found")
            return None
            
        # 按修改时间排序，取最新的
        session_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        latest_file = session_files[0]
        
        # 如果切换了文件，重置读取位置
        if self.session_file != latest_file:
            logger.info(f"[SessionMonitor] Found new session file: {latest_file}")
            self.session_file = latest_file
            self.last_position = 0
            self.processed_ids.clear()
        else:
            # 初始化读取位置
            if self.last_position == 0:
                self.last_position = latest_file.stat().st_size
        
        return latest_file
    
    def read_new_assistant_messages(self) -> List[Dict[str, Any]]:
        """读取新增的 AI 回复消息。
        
        Returns:
            新增的 AI 回复消息列表
        """
        # 检查是否需要重新查找会话文件
        if not self.session_file or not self.session_file.exists():
            self.find_latest_session()
            if not self.session_file:
                return []
        
        # 检查文件是否有新内容
        current_size = self.session_file.stat().st_size
        if current_size <= self.last_position:
            return []
        
        new_messages = []
        
        try:
            # 从上次读取的位置继续读取
            with open(self.session_file, 'r', encoding='utf-8') as f:
                f.seek(self.last_position)
                lines = f.readlines()
                
                for line in lines:
                    try:
                        msg = json.loads(line)
                        
                        # 只处理 AI 回复
                        if msg.get("role") == "assistant":
                            msg_id = msg.get("id")
                            
                            # 过滤已处理的消息
                            if msg_id and msg_id not in self.processed_ids:
                                content = msg.get("content", "")
                                if content:
                                    new_messages.append({
                                        "id": msg_id,
                                        "content": content,
                                        "timestamp": msg.get("timestamp"),
                                    })
                                    self.processed_ids.add(msg_id)
                                    
                    except json.JSONDecodeError as e:
                        logger.warning(f"[SessionMonitor] Failed to parse JSON: {e}")
                    except Exception as e:
                        logger.error(f"[SessionMonitor] Error processing message: {e}")
                
                # 更新读取位置
                self.last_position = f.tell()
                
        except Exception as e:
            logger.error(f"[SessionMonitor] Error reading session file: {e}")
            # 发生错误时，重置读取位置
            self.last_position = 0
        
        return new_messages
    
    def should_check(self) -> bool:
        """检查是否应该执行监控检查。
        
        Returns:
            是否应该检查
        """
        current_time = time.time()
        if current_time - self.last_check_time >= self.check_interval:
            self.last_check_time = current_time
            return True
        return False
    
    def reset(self) -> None:
        """重置监控器状态。"""
        self.session_file = None
        self.last_position = 0
        self.processed_ids.clear()
        self.last_check_time = 0
        logger.info("[SessionMonitor] Monitor reset")