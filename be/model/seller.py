import json
import pymongo
import time

from be.model import db_conn
from be.model import error

class Seller(db_conn.DBConn):
    def __init__(self):
        super().__init__()

    # 需要确定一下 book_json_str 的结构
    def add_book(
        self, user_id: str, store_id: str, book_id: str, book_json_str: str, stock_level: int):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)
            # 如果店铺库存中已存在该书，返回 exist_book_id
            exists = self.db["Stores"].find_one({
                "_id": store_id,
                "inventory": {"$elemMatch": {"book_id": book_id}}
            })
            if exists is not None:
                return error.error_exist_book_id(book_id)
            info = json.loads(book_json_str)
            # 参数类型归一化
            try:
                stock_level = int(stock_level)
            except Exception:
                stock_level = 0
            '''
            {
            "id": "1000134",
            "title": "书名",
            "author": "作者",
            "publisher": "出版社",
            "original_title": "原作名",
            "translator": "译者",
            "pub_year": "2020",
            "pages": 320,
            "price": 3999,
            "currency_unit": "CNY",
            "binding": "精装",
            "isbn": "978-7-XXXX-XXXXX",
            "author_intro": "作者简介文本",
            "book_intro": "书籍简介文本",
            "content": "样章试读文本",
            "tags": ["文学", "小说"],
            "pictures": ["<base64-1>", "<base64-2>"]
            }
            '''
            book = {
                "book_id": book_id,
                "stock_level": stock_level,
                "price": info.get("price"),
            }
            self.db["Stores"].update_one(
                {"_id": store_id},
                {"$push": {"inventory": book}}
            )
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg
        return 200, "ok"
    
    def add_stock_level(
        self, user_id: str, store_id: str, book_id: str, add_stock_level: int
    ):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)
            try:
                add_stock_level = int(add_stock_level)
            except Exception:
                add_stock_level = 0
            # 检查店铺库存中是否存在该书：通过 $elemMatch 查询
            store_doc = self.db["Stores"].find_one({
                "_id": store_id,
                "inventory": {"$elemMatch": {"book_id": book_id}}
            })
            if store_doc is None:
                return error.error_non_exist_book_id(book_id)
            # 使用位置操作符 $ 更新匹配的数组元素
            self.db["Stores"].update_one(
                {"_id": store_id, "inventory.book_id": book_id},
                {"$inc": {"inventory.$.stock_level": add_stock_level}}
            )
            
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg
        return 200, "ok"

    def create_store(self, user_id: str, store_id: str) -> (int, str):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if self.store_id_exist(store_id):
                return error.error_exist_store_id(store_id)
            store = {
                "_id": store_id,
                "user_id": user_id,
                "inventory":[]
            }
            self.db["Stores"].insert_one(store)
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg
        return 200, "ok"

    def ship_order(self, user_id: str, order_id: str) -> (int, str):

        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
                
            if not self.order_id_exist(order_id):
                return error.error_invalid_order_id(order_id)
                
            order_doc = self.db["Orders"].find_one({"_id": order_id})
            
            store_doc = self.db["Stores"].find_one({
                "_id": order_doc["store_id"], 
                "user_id": user_id
            })
            if store_doc is None:
                return error.error_authorization_fail()
            
            if order_doc.get("status") != "paid":
                return error.error_order_status_mismatch(order_id)
            
            result = self.db["Orders"].update_one(
                {"_id": order_id, "status": "paid"},
                {
                    "$set": {
                        "status": "shipped",
                        "ship_time": time.time()
                    }
                }
            )
            
            if result.modified_count == 0:
                return error.error_order_status_mismatch(order_id)
                
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg
        
        return 200, "ok"