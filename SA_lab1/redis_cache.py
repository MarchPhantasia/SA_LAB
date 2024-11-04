import redis
from redisbloom.client import Client as BloomClient
from threading import Lock
from dbutils.pooled_db import PooledDB
import pymysql
import json
import time

# 初始化Redis和布隆过滤器
redis_client = redis.StrictRedis(host="localhost", port=6379, db=0)
# bloom_client = BloomClient(host="localhost", port=6379)
# filter_name = "conversation_filter"
# error_rate = 0.01  # 误判率 1%
# capacity = 1000  # 预期存储容量

# # 创建布隆过滤器
# bloom_client.bfCreate(filter_name, error_rate, capacity)

# 互斥锁字典，用于每个 conversation_id
mutex_locks = {}
dbuser = "root"
dbpassword = "root"

# 初始化 MySQL 连接池
connection_pool = PooledDB(
    creator=pymysql,
    db="sharding_db",
    user="root",
    password="root",
    host="127.0.0.1",
    port=3321,
    mincached=2,  # 最小空闲连接数
    maxcached=5,  # 最大空闲连接数
    maxconnections=None,  # 最大连接数
)


# 插入新对话记录，刷新第一页缓存
def update_cache():
    conn = connection_pool.connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT conversation_id, title, chat_history, timestamp, token_usage
        FROM t_chat_history
        ORDER BY timestamp DESC
        LIMIT 10
    """
    )

    recent_conversations = cursor.fetchall()

    # 更新第一页缓存
    page_data = {}
    for conv in recent_conversations:
        conversation_id, title, chat_history, timestamp, token_usage = conv
        chat_history_json = json.dumps(json.loads(chat_history))

        # 缓存第一页数据
        page_data[conversation_id] = json.dumps(
            {
                "chat_history": chat_history_json,
                "title": title,
                "timestamp": timestamp.isoformat(),
            }
        )

        # 更新每个 conversation 的单独缓存
        redis_client.hset(
            f"conversation:{conversation_id}",
            mapping={
                "chat_history": chat_history_json,
                "title": title,
                "timestamp": timestamp.isoformat(),
            },
        )
        redis_client.expire(f"conversation:{conversation_id}", 3600)

    # 更新第一页缓存并设置过期时间
    redis_client.hset(f"conversations:page:1", mapping=page_data)
    redis_client.expire(f"conversations:page:1", 3600)

    conn.commit()

    return recent_conversations


# 分页查询全部记录
def get_all_conversations(page=1, page_size=10):
    print(page)
    conn = connection_pool.connection()

    cache_key = f"conversations:page:{page}"
    # cached_data = redis_client.hgetall(cache_key)

    # 缓存里有的话就直接返回
    # if cached_data and not cached_data.get(b"empty"):
    #     # 解码缓存数据
    #     for key in cached_data:
    #         cached_data[key] = json.loads(cached_data[key].decode("utf-8"))
 
    #     return cached_data

    # 数据库查询分页数据
    cursor = conn.cursor()
    offset = (page - 1) * page_size
    cursor.execute(
        "SELECT conversation_id, title, chat_history, timestamp, token_usage FROM t_chat_history ORDER BY timestamp DESC LIMIT %s OFFSET %s",
        (page_size, offset),
    )
    conversations = cursor.fetchall()

    if not conversations:
        # 如果该页没有数据，缓存空标记
        # redis_client.hset(cache_key, mapping={"empty": "true"})
        # redis_client.expire(cache_key, 3600)
        return []
    # 将查询的数据写入缓存
    page_data = {}
    for conv in conversations:
        conversation_id, title, chat_history, timestamp, token_usage = conv
        chat_history_json = json.dumps(json.loads(chat_history))

        page_data[conversation_id] = json.dumps(
            {
                "chat_history": chat_history_json,
                "title": title,
                "timestamp": timestamp.isoformat(),
            }
        )

        # 更新每个 conversation 的单独缓存
        redis_client.hset(
            f"conversation:{conversation_id}",
            mapping={
                "chat_history": chat_history_json,
                "title": title,
                "timestamp": timestamp.isoformat(),
            },
        )
        redis_client.expire(f"conversation:{conversation_id}", 3600)

    # 缓存当前页并设置过期时间
    redis_client.hset(cache_key, mapping=page_data)
    redis_client.expire(cache_key, 3600)

    return conversations


# 3. 通过conversation_id查询记录
def get_conversation_by_id(conversation_id):
    # 从 Redis 中获取哈希表数据
    cached_data = redis_client.hgetall(f"conversation:{conversation_id}")

    # 如果缓存中存在数据，将其转换为字典形式并返回
    if cached_data:
        # 解码 Redis 返回的数据（通常为字节，需要解码为字符串）
        return {
            key.decode("utf-8"): value.decode("utf-8")
            for key, value in cached_data.items()
        }

    # 如果缓存中没有数据，返回 None
    return None

if __name__ == "__main__":
    # 测试
    conversations = get_all_conversations()
    print(conversations)
