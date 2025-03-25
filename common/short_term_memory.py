# encoding:utf-8
import os
import json
import logging
from typing import List, Dict, Any, Optional
from collections import deque

from channel.chat_message import ChatMessage

logger = logging.getLogger(__name__)

# 配置文件夹路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "memory")
os.makedirs(DATA_DIR, exist_ok=True)

class ShortTermMemory:
    """短期记忆模块，维护最近的对话历史"""
    
    def __init__(self, session_id: str, max_size: int = 50):
        """
        初始化短期记忆
        
        Args:
            session_id: 用户ID
            max_size: 短期记忆最大容量
        """
        self.session_id = session_id
        self.max_size = max_size
        self.messages = deque(maxlen=max_size)
        self.file_path = os.path.join(DATA_DIR, f"short_term_{session_id}.json")
        self._load()
        
    def add(self, message: ChatMessage,from_self:bool=False) -> None:
        """添加消息到短期记忆"""
        self.messages.append(self._message_to_dict(message,from_self))
        self._save()
        
    def get_recent(self, n: Optional[int] = None) -> List[str]:
        """获取最近的n条消息"""
        n = n or len(self.messages)
        return [self._dict_to_str(msg) for msg in list(self.messages)[-n:]]
    
    def clear(self) -> None:
        """清空短期记忆"""
        self.messages.clear()
        self._save()
    
    def _save(self) -> None:
        """保存短期记忆到文件"""
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(list(self.messages), f, ensure_ascii=False)
    
    def _load(self) -> None:
        """从文件加载短期记忆"""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    messages = json.load(f)
                for msg in messages:
                    self.messages.append(msg)
            except Exception as e:
                logger.error(f"加载短期记忆失败: {e}")

    def _message_to_dict(self, message: ChatMessage,from_self:bool=False) -> Dict[str, Any]:
        if from_self:
            return {
                "actual_user_nickname": "bot",
                "content": message.content,
                "create_time": message.create_time,
            }
        else:
            return {
                "actual_user_nickname": message.actual_user_nickname,
                "content": message.content,
                "create_time": message.create_time,
            }
    
    def _dict_to_str(self, message: Dict[str, Any]) -> str:
        return f"(time:{message['create_time']}){message['actual_user_nickname']}: {message['content']}" 