#!/usr/bin/env python3
"""
增强的工作负载测试，包含新功能的性能测试
"""

import sys
import os
import logging
import uuid
import random
import threading
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

from fe.access import book
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer
from fe.access.buyer import Buyer
from fe.access.seller import Seller
from fe import conf

class NewOrder:
    """创建订单"""
    def __init__(self, buyer: Buyer, store_id: str, book_id_and_count: list):
        self.buyer = buyer
        self.store_id = store_id
        self.book_id_and_count = book_id_and_count

    def run(self) -> (bool, str):
        try:
            code, order_id = self.buyer.new_order(self.store_id, self.book_id_and_count)
            return code == 200, order_id
        except Exception as e:
            logging.error(f"New order failed: {e}")
            return False, ""


class Payment:
    """支付"""
    def __init__(self, buyer: Buyer, order_id: str = None):
        self.buyer = buyer
        self.order_id = order_id

    def run(self) -> bool:
        try:
            if not self.order_id:
                return False
            code = self.buyer.payment(self.order_id)
            return code == 200
        except Exception as e:
            logging.error(f"Payment failed: {e}")
            return False


class SearchBooks:
    """书籍搜索"""
    def __init__(self, buyer: Buyer, search_type: str = "basic", **kwargs):
        self.buyer = buyer
        self.search_type = search_type
        self.kwargs = kwargs

    def run(self) -> bool:
        try:
            from be.model.store import get_db
            db = get_db()
            
            if self.search_type == "basic":
                # 文本索引搜索 - 直接数据库查询，避免API开销
                keyword = self.kwargs.get("keyword", "小说")
                search_query = {"$text": {"$search": keyword}}
                cursor = db["Books"].find(search_query).limit(10)
                books = list(cursor)
                return len(books) >= 0
                
            elif self.search_type == "advanced":
                # 参数化索引搜索 - 直接数据库查询
                title_prefix = self.kwargs.get("title_prefix", None)
                tags = self.kwargs.get("tags", None)
                
                search_conditions = []
                if title_prefix:
                    title_prefix_lower = title_prefix.lower()
                    search_conditions.append({"search_index.title_lower": {"$regex": f"^{title_prefix_lower}"}})
                if tags:
                    tags_lower = [tag.lower() for tag in tags]
                    search_conditions.append({"search_index.tags_lower": {"$in": tags_lower}})
                
                if search_conditions:
                    query = {"$and": search_conditions} if len(search_conditions) > 1 else search_conditions[0]
                    cursor = db["Books"].find(query).limit(10)
                    books = list(cursor)
                    return len(books) >= 0
                return False
            else:
                return False
        except Exception as e:
            logging.error(f"Search failed: {e}")
            return False


class QueryOrders:
    """订单查询"""
    def __init__(self, buyer: Buyer, status: str = None):
        self.buyer = buyer
        self.status = status

    def run(self) -> bool:
        try:
            code, result = self.buyer.query_orders(status=self.status)
            return code == 200
        except Exception as e:
            logging.error(f"Query orders failed: {e}")
            return False

class GetBookDetail:
    """获取书籍详情"""
    def __init__(self, buyer: Buyer, book_id: str):
        self.buyer = buyer
        self.book_id = book_id

    def run(self) -> bool:
        try:
            code, detail = self.buyer.get_book_detail(self.book_id)
            return code == 200
        except Exception as e:
            logging.error(f"Get book detail failed: {e}")
            return False


class CancelOrder:
    """取消订单"""
    def __init__(self, buyer: Buyer, order_id: str = None):
        self.buyer = buyer
        self.order_id = order_id

    def run(self) -> bool:
        try:
            if not self.order_id:
                return False
            code = self.buyer.cancel_order(self.order_id)
            return code == 200
        except Exception as e:
            logging.error(f"Cancel order failed: {e}")
            return False


class ShipOrder:
    """发货"""
    def __init__(self, seller, order_id: str = None):
        self.seller = seller
        self.order_id = order_id

    def run(self) -> bool:
        try:
            if not self.order_id:
                return False
            code = self.seller.ship_order(self.order_id)
            return code == 200
        except Exception as e:
            logging.error(f"Ship order failed: {e}")
            return False


class ReceiveOrder:
    """收货确认"""
    def __init__(self, buyer: Buyer, order_id: str = None):
        self.buyer = buyer
        self.order_id = order_id

    def run(self) -> bool:
        try:
            if not self.order_id:
                return False
            code = self.buyer.receive_order(self.order_id)
            return code == 200
        except Exception as e:
            logging.error(f"Receive order failed: {e}")
            return False


class AddFunds:
    """充值"""
    def __init__(self, buyer: Buyer, add_value: int):
        self.buyer = buyer
        self.add_value = add_value

    def run(self) -> bool:
        try:
            code = self.buyer.add_funds(str(self.add_value))
            if code != 200:
                logging.warning(f"Add funds 返回错误码: {code}, 充值金额: {self.add_value}")
            return code == 200
        except Exception as e:
            logging.error(f"Add funds 异常: {e}, 充值金额: {self.add_value}")
            return False


class NoIndexSearchBooks:
    """无索引搜索(正则表达式模拟)"""
    def __init__(self, buyer: Buyer, keyword: str):
        self.buyer = buyer
        self.keyword = keyword

    def run(self) -> bool:
        try:
            from be.model.store import get_db
            db = get_db()
            
            # 强制不使用索引，使用hint禁用所有索引
            regex_pattern = {"$regex": self.keyword, "$options": "i"}
            cursor = db["Books"].find({
                "$or": [
                    {"title": regex_pattern},
                    {"author": regex_pattern},
                    {"book_intro": regex_pattern}
                ]
            }).hint({"$natural": 1}).limit(10)  # hint强制不使用索引
            
            books = list(cursor)
            return len(books) >= 0
        except Exception as e:
            logging.error(f"No index search failed: {e}")
            return False


class OrderQueryTest:
    """订单查询测试(受益于索引)"""
    def __init__(self, buyer: Buyer):
        self.buyer = buyer

    def run(self) -> bool:
        try:
            # 复合索引 (buyer_id, status, create_time)
            code, result = self.buyer.query_orders()
            return code == 200
        except Exception as e:
            logging.error(f"Order query test failed: {e}")
            return False


class OrderUpdateTest:
    """订单更新测试 (索引维护开销)"""
    def __init__(self, buyer: Buyer):
        self.buyer = buyer

    def run(self) -> bool:
        try:
            from be.model.store import get_db
            db = get_db()
            order = db["Orders"].find_one({"status": "unpaid"})
            if order:

                result = db["Orders"].update_one(
                    {"_id": order["_id"]},
                    {"$set": {"status": "paid", "pay_time": time.time()}}
                )
                return result.modified_count > 0
            return True
        except Exception as e:
            logging.error(f"Order update test failed: {e}")
            return False


class InventoryQueryTest:
    """库存查询测试(多键索引受益)"""
    def __init__(self, seller):
        self.seller = seller

    def run(self) -> bool:
        try:
            # 库存查询，多键索引 inventory.book_id
            from be.model.store import get_db
            db = get_db()
            
            cursor = db["Stores"].find({
                "inventory.book_id": {"$exists": True}
            }).limit(5)
            
            stores = list(cursor)
            return len(stores) >= 0
        except Exception as e:
            logging.error(f"Inventory query test failed: {e}")
            return False


class InventoryUpdateTest:
    """库存更新测试(多键索引维护开销)"""
    def __init__(self, seller):
        self.seller = seller

    def run(self) -> bool:
        try:
            # 模拟库存更新，触发多键索引更新
            from be.model.store import get_db
            db = get_db()
            
            # 查找一个有库存的店铺
            store = db["Stores"].find_one({"inventory": {"$exists": True, "$ne": []}})
            if store and store.get("inventory"):
                # 更新库存数量，触发多键索引维护
                book_id = store["inventory"][0]["book_id"]
                result = db["Stores"].update_one(
                    {"_id": store["_id"], "inventory.book_id": book_id},
                    {"$inc": {"inventory.$.stock_level": 1}}
                )
                return result.modified_count > 0
            return True
        except Exception as e:
            logging.error(f"Inventory update test failed: {e}")
            return False


class OrderSnapshotQueryTest:
    """订单快照查询测试(冗余数据查询优势)"""
    def __init__(self):
        pass

    def run(self) -> bool:
        try:
            # 测试从订单快照中直接查询商品信息，无需关联Books集合
            from be.model.store import get_db
            db = get_db()
            
            # 查询包含商品快照的订单，直接从冗余数据获取信息
            orders_cursor = db["Orders"].find(
                {"items.book_snapshot": {"$exists": True}},
                {"items.book_snapshot.title": 1, "items.book_snapshot.tag": 1}
            ).limit(10)
            
            orders = list(orders_cursor)
            return len(orders) >= 0
        except Exception as e:
            logging.error(f"Order snapshot query test failed: {e}")
            return False


class OrderSnapshotInsertTest:
    """订单快照插入测试(冗余数据插入开销)"""
    def __init__(self):
        pass

    def run(self) -> bool:
        try:
            # 模拟创建订单时需要复制商品信息到快照，增加插入开销
            from be.model.store import get_db
            db = get_db()
            import uuid
            
            # 获取一个随机书籍信息用于快照
            book = db["Books"].find_one({}, {"title": 1, "tags": 1, "content": 1})
            if not book:
                return False
            
            # 创建包含冗余快照数据的订单
            order_doc = {
                "_id": f"test_order_{uuid.uuid1()}",
                "buyer_id": f"test_buyer_{uuid.uuid1()}",
                "store_id": f"test_store_{uuid.uuid1()}",
                "total_amount": 8500,
                "status": "unpaid",
                "create_time": time.time(),
                "items": [{
                    "book_id": book["_id"],
                    "quantity": 1,
                    "unit_price": 8500,
                    # 冗余数据：商品信息快照
                    "book_snapshot": {
                        "title": book.get("title", ""),
                        "tag": book.get("tags", ""),
                        "content": book.get("content", "")[:200]
                    }
                }]
            }
            
            result = db["Orders"].insert_one(order_doc)
            
            # 清理测试数据
            db["Orders"].delete_one({"_id": order_doc["_id"]})
            
            return result.inserted_id is not None
        except Exception as e:
            logging.error(f"Order snapshot insert test failed: {e}")
            return False


class EnhancedWorkload:

    def __init__(self):
        self.uuid = str(uuid.uuid1())
        self.book_ids = {}
        self.buyer_ids = []
        self.seller_ids = []
        self.store_ids = []
        self.order_ids = []  # 存储已创建的订单ID
        self.order_ids_lock = threading.Lock()
        self.book_db = book.BookDB(conf.Use_Large_DB)
        self.row_count = self.book_db.get_book_count()

        self.book_num_per_store = min(conf.Book_Num_Per_Store, self.row_count)
        self.store_num_per_user = conf.Store_Num_Per_User
        self.seller_num = conf.Seller_Num
        self.buyer_num = conf.Buyer_Num
        self.session = conf.Session
        self.stock_level = conf.Default_Stock_Level
        self.user_funds = conf.Default_User_Funds
        self.batch_size = conf.Data_Batch_Size
        self.procedure_per_session = conf.Request_Per_Session

        self.stats = {
            'search_basic': {'count': 0, 'success': 0, 'time': 0},
            'search_advanced': {'count': 0, 'success': 0, 'time': 0},
            'query_orders': {'count': 0, 'success': 0, 'time': 0},
            'new_order': {'count': 0, 'success': 0, 'time': 0},
            'payment': {'count': 0, 'success': 0, 'time': 0},
            'cancel_order': {'count': 0, 'success': 0, 'time': 0},
            'ship_order': {'count': 0, 'success': 0, 'time': 0},
            'receive_order': {'count': 0, 'success': 0, 'time': 0},
            'add_funds': {'count': 0, 'success': 0, 'time': 0},
        }
        self.lock = threading.Lock()

    def gen_database(self):
        """生成测试数据"""
        
        for i in range(1, self.seller_num + 1):
            user_id, password = self.to_seller_id_and_password(i)
            seller = register_new_seller(user_id, password)
            self.seller_ids.append(user_id)
            
            for j in range(1, self.store_num_per_user + 1):
                store_id = self.to_store_id(i, j)
                code = seller.create_store(store_id)
                assert code == 200
                self.store_ids.append(store_id)
                self.book_ids[store_id] = []
                
                row_no = 0
                while row_no < self.book_num_per_store:
                    books = self.book_db.get_book_info(row_no, self.batch_size)
                    if len(books) == 0:
                        break
                    for bk in books:
                        code = seller.add_book(store_id, self.stock_level, bk)
                        assert code == 200
                        self.book_ids[store_id].append(bk.id)
                    row_no += len(books)
        
        for k in range(1, self.buyer_num + 1):
            user_id, password = self.to_buyer_id_and_password(k)
            buyer = register_new_buyer(user_id, password)
            buyer.add_funds(self.user_funds)
            self.buyer_ids.append(user_id)
        
        logging.info("数据加载完成")

    def to_seller_id_and_password(self, no: int) -> (str, str):
        return f"seller_{no}_{self.uuid}", f"password_seller_{no}_{self.uuid}"

    def to_buyer_id_and_password(self, no: int) -> (str, str):
        return f"buyer_{no}_{self.uuid}", f"buyer_seller_{no}_{self.uuid}"

    def to_store_id(self, seller_no: int, i):
        return f"store_s_{seller_no}_{i}_{self.uuid}"

    def get_random_operation(self):
        """随机获取一个操作"""
        operations = ['search_basic', 'search_advanced', 'query_orders', 'new_order', 'payment', 
                     'cancel_order', 'ship_order', 'receive_order', 'add_funds']
        weights = [25, 20, 15, 20, 5, 5, 5, 3, 2]  # 总计100%
        operation = random.choices(operations, weights=weights)[0]
        return self.create_operation(operation)

    def create_operation(self, operation_type: str):
        """创建具体的操作对象"""
        buyer_id, buyer_password = random.choice([
            self.to_buyer_id_and_password(i) for i in range(1, self.buyer_num + 1)
        ])
        buyer = Buyer(url_prefix=conf.URL, user_id=buyer_id, password=buyer_password)
        
        if operation_type == 'search_basic':
            keywords = ['小说', '文学', '历史', '科学', '技术']
            keyword = random.choice(keywords)
            store_id = random.choice(self.store_ids) if random.random() < 0.3 else None
            return SearchBooks(buyer, "basic", keyword=keyword, store_id=store_id)
            
        elif operation_type == 'search_advanced':
            if random.random() < 0.5:
                prefixes = ['中国', '世界', '现代', '新']
                title_prefix = random.choice(prefixes)
                return SearchBooks(buyer, "advanced", title_prefix=title_prefix)
            else:
                tags = [['小说'], ['文学'], ['历史']]
                tag_list = random.choice(tags)
                return SearchBooks(buyer, "advanced", tags=tag_list)
                
        elif operation_type == 'query_orders':
            status = random.choice([None, 'unpaid', 'paid', 'shipped'])
            return QueryOrders(buyer, status)
            
        elif operation_type == 'new_order':
            store_id = random.choice(self.store_ids)
            books = random.randint(1, 2)
            book_id_and_count = []
            for _ in range(books):
                if self.book_ids[store_id]:
                    book_id = random.choice(self.book_ids[store_id])
                    count = random.randint(1, 2)
                    book_id_and_count.append((book_id, count))
            return NewOrder(buyer, store_id, book_id_and_count)
            
        elif operation_type == 'payment':
            order_id = self.get_random_order_id()
            if order_id:
                # 尝试使用正确的买家身份，如果失败则使用随机买家
                buyer_id_from_order = self.extract_buyer_id_from_order(order_id)
                if buyer_id_from_order and buyer_id_from_order in self.buyer_ids:
                    buyer_password = self.get_buyer_password_by_id(buyer_id_from_order)
                    try:
                        correct_buyer = Buyer(url_prefix=conf.URL, user_id=buyer_id_from_order, password=buyer_password)
                        return Payment(correct_buyer, order_id)
                    except:
                        pass
            return Payment(buyer, order_id)
                
        elif operation_type == 'cancel_order':
            order_id = self.get_random_order_id()
            if order_id:
                # 尝试使用正确的买家身份
                buyer_id_from_order = self.extract_buyer_id_from_order(order_id)
                if buyer_id_from_order and buyer_id_from_order in self.buyer_ids:
                    buyer_password = self.get_buyer_password_by_id(buyer_id_from_order)
                    try:
                        correct_buyer = Buyer(url_prefix=conf.URL, user_id=buyer_id_from_order, password=buyer_password)
                        return CancelOrder(correct_buyer, order_id)
                    except:
                        pass
            return CancelOrder(buyer, order_id)
                
        elif operation_type == 'ship_order':
            order_id = self.get_random_order_id()
            if order_id:
                # 尝试使用正确的卖家身份
                seller_id_from_order = self.extract_seller_id_from_order(order_id)
                if seller_id_from_order and seller_id_from_order in self.seller_ids:
                    seller_password = self.get_seller_password_by_id(seller_id_from_order)
                    try:
                        correct_seller = Seller(url_prefix=conf.URL, seller_id=seller_id_from_order, password=seller_password)
                        return ShipOrder(correct_seller, order_id)
                    except:
                        pass
            # 使用随机卖家
            seller_id, seller_password = random.choice([
                self.to_seller_id_and_password(i) for i in range(1, self.seller_num + 1)
            ])
            seller = Seller(url_prefix=conf.URL, seller_id=seller_id, password=seller_password)
            return ShipOrder(seller, order_id)
                
        elif operation_type == 'receive_order':
            order_id = self.get_random_order_id()
            if order_id:
                # 尝试使用正确的买家身份
                buyer_id_from_order = self.extract_buyer_id_from_order(order_id)
                if buyer_id_from_order and buyer_id_from_order in self.buyer_ids:
                    buyer_password = self.get_buyer_password_by_id(buyer_id_from_order)
                    try:
                        correct_buyer = Buyer(url_prefix=conf.URL, user_id=buyer_id_from_order, password=buyer_password)
                        return ReceiveOrder(correct_buyer, order_id)
                    except:
                        pass
            return ReceiveOrder(buyer, order_id)
                
        elif operation_type == 'add_funds':
            add_value = random.randint(100, 1000)
            return AddFunds(buyer, add_value)
        
        return None

    def update_stats(self, operation_type: str, success: bool, elapsed_time: float):
        """更新统计信息"""
        with self.lock:
            if operation_type not in self.stats:
                logging.warning(f"未知操作类型: {operation_type}")
                return
            self.stats[operation_type]['count'] += 1
            if success:
                self.stats[operation_type]['success'] += 1
            self.stats[operation_type]['time'] += elapsed_time

    def add_order_id(self, order_id: str):
        """线程安全地添加订单ID"""
        with self.order_ids_lock:
            self.order_ids.append(order_id)
    
    def get_random_order_id(self):
        """线程安全地获取随机订单ID"""
        with self.order_ids_lock:
            if self.order_ids:
                return random.choice(self.order_ids)
            return None

    def extract_buyer_id_from_order(self, order_id: str) -> str:
        """从订单ID中提取买家ID"""
        # 订单ID格式: buyer_X_uuid_store_Y_Z_uuid_uuid
        # 例如: buyer_1_7849fcac-ba46-11f0-8e19-743af4c616b8_store_s_1_1_7849fcac-ba46-11f0-8e19-743af4c616b8_uuid
        try:
            parts = order_id.split('_')
            if len(parts) >= 3 and parts[0] == 'buyer':
                # buyer_X_uuid 格式
                buyer_num = parts[1]
                uuid_part = parts[2]
                return f"buyer_{buyer_num}_{uuid_part}"
        except:
            pass
        return None

    def get_buyer_password_by_id(self, buyer_id: str) -> str:
        """根据买家ID获取密码"""
        try:
            # 从buyer_X_uuid中提取X
            parts = buyer_id.split('_')
            if len(parts) >= 3 and parts[0] == 'buyer':
                buyer_num = int(parts[1])
                uuid_part = parts[2]
                return f"buyer_seller_{buyer_num}_{uuid_part}"
        except:
            pass
        return ""

    def extract_seller_id_from_order(self, order_id: str) -> str:
        """从订单ID中提取卖家ID"""
        # 订单ID格式: buyer_X_uuid_store_s_Y_Z_uuid_uuid
        # 店铺ID格式: store_s_Y_Z_uuid，对应卖家ID: seller_Y_uuid
        try:
            parts = order_id.split('_')
            # 找到store_s部分
            for i in range(len(parts) - 2):
                if parts[i] == 'store' and parts[i+1] == 's':
                    seller_num = parts[i+2]  # Y
                    # UUID应该是整个订单ID中的UUID部分，不是最后一个
                    # 从buyer部分提取UUID: buyer_X_uuid_...
                    if len(parts) >= 3:
                        uuid_part = parts[2]  # buyer_X_uuid中的uuid部分
                        return f"seller_{seller_num}_{uuid_part}"
        except Exception as e:
            logging.debug(f"提取卖家ID失败: {order_id}, 错误: {e}")
        return None

    def get_seller_password_by_id(self, seller_id: str) -> str:
        """根据卖家ID获取密码"""
        try:
            # 从seller_X_uuid中提取X
            parts = seller_id.split('_')
            if len(parts) >= 3 and parts[0] == 'seller':
                seller_num = int(parts[1])
                uuid_part = parts[2]
                return f"password_seller_{seller_num}_{uuid_part}"
        except:
            pass
        return ""

    def print_stats(self):
        """打印统计信息"""
        with self.lock:
            logging.info("性能统计")
            for op_type, stat in self.stats.items():
                if stat['count'] > 0:
                    success_rate = (stat['success'] / stat['count']) * 100
                    avg_latency = stat['time'] / stat['count']
                    tps = stat['success'] / stat['time'] if stat['time'] > 0 else 0
                    logging.info(f"{op_type}: 成功率={success_rate:.1f}% 延迟={avg_latency:.3f}s TPS={tps:.1f}")
