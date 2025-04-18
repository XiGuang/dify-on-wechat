# encoding:utf-8
import time
import logging
import threading
from typing import List, Dict, Any
from datetime import datetime

from bot import bot_factory
from bridge.bridge import Bridge
from bridge.context import Context, ContextType
from channel.chat_message import ChatMessage
from common.short_term_memory import ShortTermMemory
from common.long_term_memory import LongTermMemory
from config import conf

logger = logging.getLogger(__name__)

# 总结提示词
SUMMARY_PROMPT = "你是一个对话总结助手。请简明扼要地总结以下对话内容，提取关键信息和主题。"

class MemoryManager:
    """记忆管理器，管理用户的长短期记忆"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MemoryManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self, summarize_interval: int = 24 * 3600, clean_interval: int = 7 * 24 * 3600):
        """
        初始化记忆管理器
        
        Args:
            summarize_interval: 总结生成间隔(秒)
            clean_interval: 清理间隔(秒)
        """
        if self._initialized:
            return
            
        self.bot = bot_factory.create_bot(Bridge().btype['chat'])
        self.short_term_memories = {}  # session_id -> ShortTermMemory
        self.long_term_memories = {}  # session_id -> LongTermMemory
        self.summarize_interval = summarize_interval
        self.clean_interval = clean_interval
        self.last_summarize_time = {}  # session_id -> 上次总结时间
        self.last_clean_time = time.time()
        
        # 启动定时任务
        self._start_background_tasks()
        
        self._initialized = True
    
    def get_short_term_memory(self, session_id: str) -> ShortTermMemory:
        """获取用户的短期记忆"""
        if session_id not in self.short_term_memories:
            self.short_term_memories[session_id] = ShortTermMemory(session_id)
        return self.short_term_memories[session_id]
    
    def get_long_term_memory(self, session_id: str) -> LongTermMemory:
        """获取用户的长期记忆"""
        if session_id not in self.long_term_memories:
            self.long_term_memories[session_id] = LongTermMemory(session_id)
        return self.long_term_memories[session_id]
    
    def add_message(self, message: ChatMessage, from_self:bool=False) -> None:
        """添加消息到短期记忆"""
        stm = self.get_short_term_memory(message.from_user_id)
        stm.add(message,from_self)
        
        # 检查是否需要总结
        if len(stm) > conf().get("recent_k_memory",20):
            self._summarize_short_term_memory(message.from_user_id,conf().get("memory_summarize_length",10))
    
    def query_relevant_memories(self, session_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """查询用户相关的记忆"""
        ltm = self.get_long_term_memory(session_id)
        return ltm.query(query, top_k)

    def get_recent_memories(self, session_id: str, top_k: int = 5) -> list[str]:
        """获取用户最近的记忆"""
        stm = self.get_short_term_memory(session_id)
        return stm.get_recent(top_k)

    def get_memories(self, session_id: str, query:str, recent_top_k: int = 10,relevant_top_k:int=5) -> str:
        """获取用户最近的记忆以及相关的长期记忆"""
        recent_memories = self.get_recent_memories(session_id, recent_top_k)
        # relevant_memories = self.query_relevant_memories(session_id, query, relevant_top_k)
        # 合并记忆
        memories = ""
        # memories = "相关长期记忆：\n"
        # for memory in relevant_memories:
        #     memories += f"{memory}\n"
        memories += "[聊天历史(你的回复记录为bot)]\n"
        for memory in recent_memories[:-1]:
            memories += f"{memory}\n"
        memories += f"[当前对话]\n"
        return memories
        

    
    def _summarize_short_term_memory(self, session_id: str,length:int = 20) -> None:
        """总结短期记忆并存入长期记忆"""
        stm = self.get_short_term_memory(session_id)
        ltm = self.get_long_term_memory(session_id)
        
        # 获取最远的消息
        recent_messages = stm.get_back(length)
        if len(recent_messages)<length:
            return
            
        # 提取关键信息
        all_content = "\n".join([msg for msg in recent_messages])
        all_content = f"[聊天记录](你的回复标记为bot)\n{all_content}"
        context=Context(ContextType.FUNCTION, all_content)
        
        # 生成总结
        session_id = f"memory_summary_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        context["session_id"]= session_id
        context["function_name"] = "summarize"
        result = self.bot.reply(all_content,context)
            
        total_tokens, completion_tokens, summary = (
            result['total_tokens'],
            result['completion_tokens'],
            result['content']
        )

        logger.info(f"为用户 {session_id} 生成了总结: {summary}")

        import json
        # 总结输出的格式：{
        #   "summarize":["content 1","content 2", ...]
        # }
        try:
            summary = json.loads(summary)
            summary = summary.get("summarize", summary)
        except json.JSONDecodeError:
            logger.error(f"总结解析错误: {summary}")
            return

        for content in summary:
            # 将生成的总结添加到长期记忆
            ltm.add(content, importance=1.2)
        stm.delete_back(length)
    
    def _clean_outdated_memories(self) -> None:
        """清理过期记忆"""
        for session_id, ltm in self.long_term_memories.items():
            deleted = ltm.clean_outdated()
            if deleted > 0:
                logger.info(f"为用户 {session_id} 清理了 {deleted} 条过期记忆")
    
    def _start_background_tasks(self) -> None:
        """启动后台任务"""
        def run_background_tasks():
            while True:
                try:
                    # 检查是否需要清理
                    now = time.time()
                    if now - self.last_clean_time >= self.clean_interval:
                        self._clean_outdated_memories()
                        self.last_clean_time = now
                except Exception as e:
                    logger.error(f"后台任务出错: {e}")
                finally:
                    # 每小时检查一次
                    time.sleep(3600)
        
        # 启动后台线程
        bg_thread = threading.Thread(target=run_background_tasks, daemon=True)
        bg_thread.start() 