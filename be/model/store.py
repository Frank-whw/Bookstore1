import logging
import threading
from typing import Optional

import pymongo
from pymongo import ASCENDING
from pymongo.errors import PyMongoError



class StoreMongoDB:
    """
    MongoDB 版本的 Store：负责初始化需要的集合与索引，并提供连接句柄。

    - 集合：Users, Stores, Orders, Books
    - 索引：
        * Users.token (sparse)
        * Stores.user_id, Stores.inventory.book_id
        * Orders (buyer_id, status, create_time) 复合索引；(status, timeout_at)
        * Books 文本索引 + 前缀索引（title_lower、tags_lower）
    """

    def __init__(self, mongo_uri: str = "mongodb://localhost:27017/", db_name: str = "bookstore"):
        try:
            self.client = pymongo.MongoClient(mongo_uri)
            self.db = self.client[db_name]
            self.init_collections_and_indexes()
        except pymongo.errors.PyMongoError as e:
            logging.error(f"初始化 MongoDB 连接失败: {e}")
            raise

    def init_collections_and_indexes(self) -> None:
        """创建集合（如不存在）并建立常用索引。"""
        try:
            # 显式创建集合以确保存在
            for name in ["Users", "Stores", "Orders", "Books"]:
                if name not in self.db.list_collection_names():
                    try:
                        self.db.create_collection(name)
                    except Exception:
                        # 并发或已存在时忽略
                        pass

            # Users 索引
            try:
                self.db.Users.create_index([("token", ASCENDING)], sparse=True)
            except PyMongoError as e:
                logging.warning(f"Users.create_index(token) 失败: {e}")

            # Stores 索引
            try:
                self.db.Stores.create_index([("user_id", ASCENDING)])
                # 为按商品过滤库存添加多键索引
                self.db.Stores.create_index([("inventory.book_id", ASCENDING)])
            except PyMongoError as e:
                logging.warning(f"Stores.create_index(user_id) 失败: {e}")

            # Orders 索引
            try:
                # 复合索引：buyer_id + status + create_time（按时间倒序）
                self.db.Orders.create_index([("buyer_id", ASCENDING), ("status", ASCENDING), ("create_time", -1)], name="orders_by_buyer_status_time")
                # 可选索引：状态超时扫描
                self.db.Orders.create_index([("status", ASCENDING), ("timeout_at", ASCENDING)], name="orders_timeout_scan")
            except PyMongoError as e:
                logging.warning(f"Orders.create_index 失败: {e}")

            # Books 索引（用于搜索优化）
            try:
                # 单一文本索引，覆盖多个字段并设置权重
                try:
                    self.db.Books.create_index([
                        ("title", "text"),
                        ("author", "text"),
                        ("book_intro", "text"),
                        ("content", "text"),
                        ("tags", "text"),
                    ], name="books_text", default_language="none", weights={
                        "title": 10,
                        "author": 7,
                        "tags": 5,
                        "book_intro": 2,
                        "content": 2,
                    })
                except Exception:
                    # 如果已有文本索引则忽略
                    pass
                # 前缀索引（题目与标签）
                self.db.Books.create_index([("search_index.title_lower", ASCENDING)])
                self.db.Books.create_index([("search_index.tags_lower", ASCENDING)])
            except PyMongoError as e:
                logging.warning(f"Books.create_index(search_index.*) 失败: {e}")

            logging.info("MongoDB 集合与索引初始化完成")
        except PyMongoError as e:
            logging.error(f"初始化集合/索引失败: {e}")

    def get_db_conn(self):
        """返回 MongoClient（连接句柄）。"""
        return self.client

    def get_db(self):
        """返回 Database（bookstore）。"""
        return self.db


# 与 sqlite 版本保持相似的全局接口
database_instance: Optional[StoreMongoDB] = None
init_completed_event = threading.Event()


def init_database(mongo_uri: str = "mongodb://localhost:27017/", db_name: str = "bookstore") -> None:
    """初始化全局 MongoDB 实例。"""
    global database_instance
    database_instance = StoreMongoDB(mongo_uri=mongo_uri, db_name=db_name)
    init_completed_event.set()


def get_db_conn():
    """获取全局 MongoClient。"""
    global database_instance
    if database_instance is None:
        # 惰性初始化以提升可用性
        init_database()
    return database_instance.get_db_conn()


def get_db():
    """获取全局 Database（bookstore）。"""
    global database_instance
    if database_instance is None:
        init_database()
    return database_instance.get_db()