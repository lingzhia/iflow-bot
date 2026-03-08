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
        self.session_files: Dict[Path, int] = {}  # 会话文件 -> 读取位置
        self.processed_ids = set()
        self.last_check_time = 0
        self.check_interval = 0.5  # 检查间隔（秒）
        
    def find_session_files(self) -> List[Path]:
        """查找所有会话文件。
        
        Returns:
            所有会话文件路径列表
        """
        projects_dir = self.workspace / "projects"
        if not projects_dir.exists():
            logger.warning(f"[SessionMonitor] Projects directory not found: {projects_dir}")
            return []
            
        # 查找所有会话文件
        session_files = list(projects_dir.glob("*/session-*.jsonl"))
        if not session_files:
            logger.warning("[SessionMonitor] No session files found")
            return []
        
        # 按修改时间排序
        session_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        # 初始化新发现的会话文件
        for session_file in session_files:
            if session_file not in self.session_files:
                self.session_files[session_file] = session_file.stat().st_size
                logger.debug(f"[SessionMonitor] Found session file: {session_file.name}")
        
        # 移除不存在的会话文件
        existing_files = set(session_files)
        self.session_files = {
            f: pos for f, pos in self.session_files.items() 
            if f in existing_files
        }
        
        return session_files
    
    def read_new_assistant_messages(self) -> List[Dict[str, Any]]:
        """读取新增的 AI 回复消息。
        
        Returns:
            新增的 AI 回复消息列表
        """
        # 获取所有会话文件
        session_files = self.find_session_files()
        if not session_files:
            return []
        
        new_messages = []
        
        # 遍历所有会话文件
        for session_file in session_files:
            # 获取该文件的读取位置
            current_size = session_file.stat().st_size
            last_position = self.session_files.get(session_file, 0)
            
            # 检查文件是否有新内容
            if current_size <= last_position:
                continue
            
            try:
                # 从上次读取的位置继续读取
                with open(session_file, 'r', encoding='utf-8') as f:
                    f.seek(last_position)
                    lines = f.readlines()
                    
                    for line in lines:
                        try:
                            msg = json.loads(line)
                            
                            # 只处理 assistant 类型的消息（AI 回复）
                            if msg.get("type") == "assistant":
                                # 提取消息内容
                                message_data = msg.get("message", {})
                                if not message_data:
                                    continue
                                
                                msg_id = message_data.get("id") or msg.get("uuid")
                                
                                # 提取文本内容
                                content_list = message_data.get("content", [])
                                text_content = ""
                                
                                if isinstance(content_list, list):
                                    for item in content_list:
                                        if isinstance(item, dict):
                                            if item.get("type") == "text":
                                                text_content += item.get("text", "")
                                        elif isinstance(item, str):
                                            text_content += item
                                elif isinstance(content_list, str):
                                    text_content = content_list
                                
                                # 只返回非空的回复内容
                                if not text_content.strip():
                                    continue
                                
                                # 过滤已处理的消息
                                if msg_id and msg_id not in self.processed_ids:
                                    new_messages.append({
                                        "id": msg_id,
                                        "content": text_content,
                                        "timestamp": msg.get("timestamp"),
                                        "session_id": msg.get("sessionId"),
                                        "session_file": str(session_file),
                                    })
                                    self.processed_ids.add(msg_id)
                                    
                        except json.JSONDecodeError as e:
                            logger.warning(f"[SessionMonitor] Failed to parse JSON: {e}")
                        except Exception as e:
                            logger.error(f"[SessionMonitor] Error processing message: {e}")
                    
                    # 更新该文件的读取位置
                    self.session_files[session_file] = f.tell()
                    
            except Exception as e:
                logger.error(f"[SessionMonitor] Error reading session file {session_file.name}: {e}")
                # 发生错误时，重置该文件的读取位置
                self.session_files[session_file] = 0
        
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
        self.session_files.clear()
        self.processed_ids.clear()
        self.last_check_time = 0
        logger.info("[SessionMonitor] Monitor reset")
    
    def get_session_info(self) -> Dict[str, Any]:
        """获取会话信息。
        
        Returns:
            会话信息字典
        """
        session_files = self.find_session_files()
        return {
            "total_sessions": len(session_files),
            "session_files": [str(f) for f in session_files],
            "processed_messages": len(self.processed_ids),
        }