# encoding:utf-8
import os
import time
import sqlite3
import logging
import numpy as np
from typing import List, Dict, Any, Optional

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning("SentenceTransformers 未安装，长期记忆将不可用。安装: pip install sentence-transformers")

logger = logging.getLogger(__name__)

# 配置文件夹路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "memory")
os.makedirs(DATA_DIR, exist_ok=True)

class LongTermMemory:
    """长期记忆模块，使用向量数据库存储记忆"""
    
    def __init__(self, session_id: str, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        """
        初始化长期记忆
        
        Args:
            session_id: 会话ID
            model_name: SentenceTransformer模型名称
        """
        self.session_id = session_id
        self.db_path = os.path.join(DATA_DIR, f"long_term_{session_id}.db")
        
        # 初始化向量模型
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            self.model = SentenceTransformer(model_name)
        else:
            self.model = None
            
        # 初始化数据库
        self._init_db()
        
    def _init_db(self) -> None:
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            vector BLOB,
            timestamp REAL,
            importance REAL,
            last_accessed REAL,
            access_count INTEGER DEFAULT 0
        )
        ''')
        conn.commit()
        conn.close()
        
    def add(self, content: str, importance: float = 1.0) -> Optional[int]:
        """
        添加记忆到长期记忆
        
        Args:
            content: 记忆内容
            importance: 记忆重要性
            
        Returns:
            记忆ID
        """
        if not content.strip():
            return -1
            
        if self.model is None:
            logger.warning("SentenceTransformers未安装，无法添加长期记忆")
            return -1
        
        logger.debug(f"添加记忆到长期记忆: {content}")

        # 向量化内容
        vector = self.model.encode(content)
        vector_bytes = vector.numpy().tobytes()
        
        # 存储到数据库
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = time.time()
        cursor.execute(
            "INSERT INTO memories (content, vector, timestamp, importance, last_accessed) VALUES (?, ?, ?, ?, ?)",
            (content, vector_bytes, now, importance, now)
        )
        memory_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return memory_id
        
    def query(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        查询最相关的记忆
        
        Args:
            query: 查询内容
            top_k: 返回结果数量
            
        Returns:
            相关记忆列表
        """
        if self.model is None:
            logger.warning("SentenceTransformers未安装，无法查询长期记忆")
            return []
            
        # 向量化查询
        query_vector = self.model.encode(query)
        
        # 从数据库获取所有记忆
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, content, vector, importance, timestamp, last_accessed, access_count FROM memories")
        results = cursor.fetchall()
        
        if not results:
            conn.close()
            return []
        
        # 计算相似度并排序
        memories = []
        now = time.time()
        for row in results:
            memory_id, content, vector_bytes, importance, created_time, last_accessed, access_count = row
            vector = np.frombuffer(vector_bytes, dtype=np.float32)
            
            # 计算向量相似度
            similarity = np.dot(query_vector, vector) / (np.linalg.norm(query_vector) * np.linalg.norm(vector))
            
            # 时间衰减（一周减半）
            time_factor = 0.5 ** ((now - created_time) / (7 * 24 * 3600))
            
            # 访问频率增益
            recency_factor = 0.5 ** ((now - last_accessed) / (24 * 3600))
            frequency_factor = min(1.0, access_count / 10)
            
            # 最终分数
            score = similarity * (0.6 + 0.2 * importance + 0.1 * time_factor + 0.1 * (recency_factor + frequency_factor))
            
            memories.append({
                "id": memory_id,
                "content": content,
                "similarity": similarity,
                "score": score,
                "created_time": created_time,
                "importance": importance
            })
        
        # 按得分排序并返回top_k个结果
        memories.sort(key=lambda x: x["score"], reverse=True)
        top_memories = memories[:top_k]
        
        # 更新访问统计
        for memory in top_memories:
            cursor.execute(
                "UPDATE memories SET last_accessed = ?, access_count = access_count + 1 WHERE id = ?",
                (now, memory["id"])
            )
        
        conn.commit()
        conn.close()
        
        return [self._dict_to_str(memory) for memory in top_memories]

    def _dict_to_str(self, memory: Dict[str, Any]) -> str:
        """将记忆字典转换为字符串"""
        return f"(time: {memory['created_time']}):{memory['content']}"
    
    def delete(self, memory_id: int) -> bool:
        """删除指定ID的记忆"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
    
    def update_importance(self, memory_id: int, importance: float) -> bool:
        """更新记忆的重要性"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE memories SET importance = ? WHERE id = ?", (importance, memory_id))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
    
    def clean_outdated(self, threshold_days: int = 90, min_importance: float = 0.3) -> int:
        """清理过时且不重要的记忆"""
        now = time.time()
        threshold_time = now - threshold_days * 24 * 3600
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM memories WHERE timestamp < ? AND importance < ?",
            (threshold_time, min_importance)
        )
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted_count 