# encoding:utf-8
from common.chat_message import ChatMessage
from common.memory_manager import MemoryManager

def test_memory_system():
    # 创建几个测试消息
    messages = [
        ChatMessage(sender_id="user1", receiver_id="bot", content="你好，我叫张三"),
        ChatMessage(sender_id="bot", receiver_id="user1", content="你好张三，很高兴认识你"),
        ChatMessage(sender_id="user1", receiver_id="bot", content="我想了解一下深度学习技术"),
        ChatMessage(sender_id="bot", receiver_id="user1", content="深度学习是机器学习的一个分支，它使用多层神经网络来学习数据表示"),
        ChatMessage(sender_id="user1", receiver_id="bot", content="我的邮箱是zhangsan@example.com，有资料可以发给我"),
    ]
    
    # 初始化记忆管理器
    memory_manager = MemoryManager(summarize_interval=5)  # 设置较短的摘要间隔以便测试
    
    # 添加消息到短期记忆
    for msg in messages:
        memory_manager.add_message(msg)
    
    # 查询短期记忆
    short_term = memory_manager.get_short_term_memory("user1")
    recent_messages = short_term.get_recent(3)  # 获取最近3条消息
    print("最近的消息:")
    for msg in recent_messages:
        print(f"- {msg.sender_id}: {msg.content}")
    
    # 手动添加一些长期记忆
    long_term = memory_manager.get_long_term_memory("user1")
    long_term.add("张三是一位对深度学习感兴趣的用户", importance=1.2)
    long_term.add("张三的邮箱是zhangsan@example.com", importance=1.5)
    
    # 查询相关记忆
    query = "张三的联系方式是什么？"
    memories = memory_manager.query_relevant_memories("user1", query)
    print("\n查询结果:")
    for memory in memories:
        print(f"- [{memory['score']:.2f}] {memory['content']}")

if __name__ == "__main__":
    test_memory_system() 