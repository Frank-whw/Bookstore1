import pymongo
import uuid
import logging
import time
from pymongo import ReturnDocument
from be.model import db_conn
from be.model import error

class Buyer(db_conn.DBConn):
    def __init__(self):
        super().__init__()
    
    def new_order(
        self, user_id: str, store_id, id_and_count: [(str, int)]
    ) -> (int, str, str):
        order_id = ""
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id) + (order_id,)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id) + (order_id,)
            uid = "{}_{}_{}".format(user_id, store_id, str(uuid.uuid1()))
            db = self.db

            total_amount = 0
            items = []
            for book_id, count in id_and_count:
                # 获取店铺库存并匹配该书，使用 $elemMatch + 投影仅返回匹配的库存项
                store_doc = db["Stores"].find_one(
                    {"_id": store_id, "inventory": {"$elemMatch": {"book_id": book_id}}},
                    {"inventory.$": 1}
                )
                if store_doc is None or "inventory" not in store_doc or not store_doc["inventory"]:
                    return error.error_non_exist_book_id(book_id) + (order_id,)
                inv_item = store_doc["inventory"][0]
                store_level = inv_item.get("stock_level", 0)
                # 归一化价格为 0（防止 None 导致计算异常）
                price = inv_item.get("price", 0) or 0
                # 从 Books 获取快照信息
                book_doc = db["Books"].find_one(
                    {"_id": book_id},
                    {"title": 1, "tags": 1, "content": 1}
                )
                # 生成 tag（取第一个标签）
                tag_val = None
                tags = book_doc.get("tags") if book_doc else None
                if isinstance(tags, list):
                    tag_val = tags[0] if tags else None
                elif isinstance(tags, str):
                    parts = [t.strip() for t in tags.replace("\n", ",").split(",") if t.strip()]
                    tag_val = parts[0] if parts else None
                # 生成 content
                content_val = None
                if book_doc:
                    content_val = book_doc.get("content")
                book_info = {
                    "title": book_doc.get("title") if book_doc else None,
                    "tag": tag_val,
                    "content": content_val,
                }
                if store_level < count:
                    return error.error_stock_level_low(book_id) + (order_id,)
                items.append({
                    "book_id": book_id,
                    "quantity": count,
                    "unit_price": price,
                    "book_snapshot": book_info
                })
                total_amount += count * price
            
            order = {
                "_id": uid,
                "buyer_id": user_id,
                "store_id": store_id,
                "total_amount": total_amount,
                "status": "unpaid",
                "create_time": time.time(),
                "items": items
            }
            order_id = uid
            db["Orders"].insert_one(order)
        except pymongo.errors.PyMongoError as e:
            return error.exception_db_to_tuple3(e)
        except BaseException as e:
            return error.exception_to_tuple3(e)
        
        return 200, "ok", order_id
    def payment(self, user_id: str, password: str, order_id: str) -> (int, str):
        try:
            db = self.db
            # 根据order_id获取订单信息
            if not self.order_id_exist(order_id):
                return error.error_invalid_order_id(order_id)
            order_doc = db["Orders"].find_one({"_id": order_id})
            if order_doc is None:
                return error.error_invalid_order_id(order_id)
            buyer_id = order_doc.get("buyer_id")
            total_amount = order_doc.get("total_amount", 0)

            # 根据buyer_id获取balance,password，并鉴权
            if buyer_id != user_id:
                return error.error_authorization_fail()
            user_doc = db["Users"].find_one({"_id": buyer_id})
            if user_doc is None:
                return error.error_non_exist_user_id(buyer_id)
            balance = user_doc.get("balance", 0)
            if password != user_doc.get("password"):
                return error.error_authorization_fail()

            # 防重复支付：根据订单状态返回更精确的业务错误
            status = order_doc.get("status")
            if status != "unpaid":
                if status == "cancelled":
                    return error.error_order_cancelled(order_id)
                if status in ("paid", "completed"):
                    return error.error_order_completed(order_id)
                return error.error_order_status_mismatch(order_id)

            if balance < total_amount:
                return error.error_not_sufficient_funds(order_id)

            # 买家扣款（一次且带余额条件，防止并发超扣）
            res = db["Users"].update_one(
                {"_id": buyer_id, "balance": {"$gte": total_amount}},
                {"$inc": {"balance": -total_amount}}
            )
            if res.matched_count == 0:
                return error.error_not_sufficient_funds(order_id)
            # 更新订单状态
            updated = db["Orders"].update_one(
                {"_id": order_id, "status": "unpaid"},
                {"$set": {"status": "paid", "pay_time": time.time()}}
            )
            if updated.matched_count == 0:
                # 简单补偿：状态更新失败则回滚扣款
                db["Users"].update_one({
                    "_id": buyer_id
                }, {
                    "$inc": {"balance": total_amount}
                })
                return error.error_invalid_order_id(order_id)
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg

        return 200, "ok"
    
    def add_funds(self, user_id, password, add_value) -> (int, str):
        try:
            db = self.db
            user_doc = db["Users"].find_one({"_id": user_id})
            if user_doc is None:
                # sqlite这边是error.error_authorization_fail()，但我感觉是error_non_exist_user_id
                return error.error_non_exist_user_id(user_id) 
            if password != user_doc.get("password"):
                return error.error_authorization_fail()
            
            # 转换add_value为整数
            try:
                add_value = int(add_value)
            except (ValueError, TypeError):
                return error.error_and_message(400, "充值金额必须是数字")

            # 允许负值作为扣款，但不允许余额变为负数
            if add_value < 0:
                # 原子性扣款：仅当余额 >= 需要扣减的绝对值时才扣款
                result = db["Users"].update_one(
                    {"_id": user_id, "balance": {"$gte": -add_value}},
                    {"$inc": {"balance": add_value}}
                )
                if result.modified_count == 0:
                    return error.error_and_message(400, "余额不足，扣款失败")
            else:
                # 正值或零：直接充值/不变
                db["Users"].update_one(
                    {"_id": user_id},
                    {"$inc": {"balance": add_value}}
                )
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg

        return 200, "ok"

    def receive_order(self, user_id: str, order_id: str) -> (int, str):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
        
            if not self.order_id_exist(order_id):
                return error.error_invalid_order_id(order_id)
            
            order_doc = self.db["Orders"].find_one({
                "_id": order_id,
                "buyer_id": user_id
            })
            if order_doc is None:
                return error.error_authorization_fail()
            
            if order_doc.get("status") != "shipped":
                return error.error_order_status_mismatch(order_id)
            
            # 更新订单状态为已收货，同时给卖家转账
            total_amount = order_doc.get("total_amount", 0)
            store_id = order_doc.get("store_id")
            
            store_doc = self.db["Stores"].find_one({"_id": store_id})
            if store_doc is None:
                return error.error_non_exist_store_id(store_id)
            seller_id = store_doc.get("user_id")

            result = self.db["Orders"].update_one(
                {"_id": order_id, "status": "shipped"},
                {
                    "$set": {
                        "status": "delivered", 
                        "deliver_time": time.time()
                    }
                }
            )
            
            if result.modified_count == 0:
                return error.error_order_status_mismatch(order_id)

            self.db["Users"].update_one(
                {"_id": seller_id},
                {"$inc": {"balance": total_amount}}
            )
                
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg
        
        return 200, "ok"
    
    # 订单查询
    def get_order(self, user_id: str, order_id: str) -> (int, str, dict):
        try:
            db = self.db
            order_doc = db["Orders"].find_one({"_id": order_id})
            if order_doc is None:
                return error.error_invalid_order_id(order_id)
            if order_doc.get("buyer_id") != user_id:
                return error.error_authorization_fail()
            return 200, "ok", order_doc
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg
    def query_orders(self, user_id: str, status: str = None, page: int = 1) -> (int, str, dict):
        try:
            if user_id is None:
                return error.error_and_message(400, "参数不能为空") + ({},)
                
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id) + ({},)

            page_size = 10
            try:
                page = max(1, int(page)) if page else 1
            except (ValueError, TypeError):
                return error.error_and_message(400, "页码参数无效") + ({},)
            skip = (page - 1) * page_size
            
            # 利用复合索引 (buyer_id, status, create_time)
            query = {"buyer_id": user_id}
            if status and status.strip():
                query["status"] = status.strip()
            
            total_count = self.db["Orders"].count_documents(query)
            
            # 查询订单列表，按创建时间倒序
            orders_cursor = self.db["Orders"].find(
                query,
                {
                    "_id": 1, "store_id": 1, "status": 1, "total_amount": 1,
                    "create_time": 1, "pay_time": 1, "ship_time": 1, "deliver_time": 1,
                    "items": 1
                }
            ).sort("create_time", -1).skip(skip).limit(page_size)
            
            orders = []
            for order_doc in orders_cursor:
                order_info = {
                    "order_id": order_doc["_id"],
                    "store_id": order_doc["store_id"],
                    "status": order_doc["status"],
                    "total_amount": order_doc["total_amount"],
                    "create_time": order_doc.get("create_time"),
                    "pay_time": order_doc.get("pay_time"),
                    "ship_time": order_doc.get("ship_time"),
                    "deliver_time": order_doc.get("deliver_time"),
                    "items": order_doc.get("items", [])
                }
                orders.append(order_info)
            
            # 分页
            total_pages = (total_count + page_size - 1) // page_size
            result = {
                "orders": orders,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_count": total_count,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
            
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg, {}
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg, {}
        
        return 200, "ok", result

    def cancel_order(self, user_id: str, order_id: str) -> (int, str):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
                
            if not self.order_id_exist(order_id):
                return error.error_invalid_order_id(order_id)
            
            # 获取订单信息
            order_doc = self.db["Orders"].find_one({"_id": order_id})
            if order_doc is None:
                return error.error_invalid_order_id(order_id)

            if order_doc["buyer_id"] != user_id:
                return error.error_authorization_fail()
            
            status = order_doc.get("status")
            if status not in ["unpaid", "paid"]:
                return error.error_and_message(400, "订单状态不允许取消")

            # 原子性更新订单状态，避免退款与状态变更不一致
            updated_order = self.db["Orders"].find_one_and_update(
                {"_id": order_id, "buyer_id": user_id, "status": status},
                {
                    "$set": {
                        "status": "cancelled",
                        "cancel_time": time.time()
                    }
                },
                return_document=ReturnDocument.BEFORE
            )

            if updated_order is None:
                return error.error_and_message(400, "订单状态已变更，取消失败")

            # 如果是已支付订单，需要退款
            if updated_order.get("status") == "paid":
                total_amount = updated_order.get("total_amount", 0)
                refund_result = self.db["Users"].update_one(
                    {"_id": user_id},
                    {"$inc": {"balance": total_amount}}
                )
                if refund_result.modified_count == 0:
                    # 尝试恢复订单状态，保持资金一致
                    self.db["Orders"].update_one(
                        {"_id": order_id, "status": "cancelled"},
                        {
                            "$set": {"status": "paid"},
                            "$unset": {"cancel_time": ""}
                        }
                    )
                    return error.error_non_exist_user_id(user_id)

        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg
        
        return 200, "ok"

    @staticmethod
    def auto_cancel_timeout_orders() -> (int, str, int):
        # 自动取消超时订单：扫描未支付且超过24小时的订单
        # 使用索引 (status, create_time) 进行高效扫描
        try:
            from be.model.store import get_db
            db = get_db()
            timeout_threshold = time.time() - 24 * 3600

            timeout_orders = db["Orders"].find({
                "status": "unpaid",
                "create_time": {"$lt": timeout_threshold}
            })
            
            cancelled_count = 0
            current_time = time.time()
            
            for order in timeout_orders:
                # 更新订单状态，记录自动取消时间
                result = db["Orders"].update_one(
                    {"_id": order["_id"], "status": "unpaid"},
                    {
                        "$set": {
                            "status": "cancelled",
                            "timeout_at": current_time
                        }
                    }
                )
                if result.modified_count > 0:
                    cancelled_count += 1
                    
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg, 0
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg, 0
        
        return 200, "ok", cancelled_count

    def search_books(self, keyword: str = None, store_id: str = None, page: int = 1) -> (int, str, dict):
        """
        书籍搜索
        全站搜索：在books集合中设置文本索引，满足"题目、标签、目录/内容"的关键字搜索
        店铺内搜索：先取店铺的book_id列表，在Books上$text或前缀/标签过滤，并限制_id in 店铺书目列表
        """
        try:
            if keyword is None or keyword.strip() == "":
                return error.error_and_message(400, "搜索关键字不能为空") + ({},)
            
            keyword = keyword.strip()
            page_size = 10
            
            try:
                page = max(1, int(page)) if page else 1
            except (ValueError, TypeError):
                return error.error_and_message(400, "页码参数无效") + ({},)
            
            skip = (page - 1) * page_size
            
            if store_id and store_id.strip():
                # 店铺内搜索
                if not self.store_id_exist(store_id):
                    return error.error_non_exist_store_id(store_id) + ({},)
                
                store_doc = self.db["Stores"].find_one({"_id": store_id}, {"inventory": 1})
                if not store_doc or "inventory" not in store_doc:
                    return 200, "ok", {
                        "books": [],
                        "pagination": {
                            "page": page,
                            "page_size": page_size,
                            "total_count": 0,
                            "total_pages": 0,
                            "has_next": False,
                            "has_prev": False
                        }
                    }
                
                book_ids = [item["book_id"] for item in store_doc["inventory"]]
                if not book_ids:
                    return 200, "ok", {
                        "books": [],
                        "pagination": {
                            "page": page,
                            "page_size": page_size,
                            "total_count": 0,
                            "total_pages": 0,
                            "has_next": False,
                            "has_prev": False
                        }
                    }
                
                # 在Books集合中搜索
                search_query = {
                    "_id": {"$in": book_ids},
                    "$text": {"$search": keyword}
                }
                
                # 按textScore排序分页
                total_count = self.db["Books"].count_documents(search_query)
                books_cursor = self.db["Books"].find(
                    search_query,
                    {"score": {"$meta": "textScore"}}
                ).sort([("score", {"$meta": "textScore"})]).skip(skip).limit(page_size)
                
            else:
                # 全站搜索
                search_query = {"$text": {"$search": keyword}}
                
                # 按textScore排序分页
                total_count = self.db["Books"].count_documents(search_query)
                books_cursor = self.db["Books"].find(
                    search_query,
                    {"score": {"$meta": "textScore"}}
                ).sort([("score", {"$meta": "textScore"})]).skip(skip).limit(page_size)
            
            books = []
            for book_doc in books_cursor:
                book_info = {
                    "id": book_doc["_id"],
                    "title": book_doc.get("title", ""),
                    "author": book_doc.get("author", ""),
                    "book_intro": book_doc.get("book_intro", ""),
                    "tags": book_doc.get("tags", [])
                }
                if "score" in book_doc:
                    book_info["text_score"] = book_doc["score"]
                books.append(book_info)
            
            total_pages = (total_count + page_size - 1) // page_size
            result = {
                "books": books,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_count": total_count,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
            
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg, {}
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg, {}
        
        return 200, "ok", result

    def search_books_advanced(self, title_prefix: str = None, tags: list = None, store_id: str = None, page: int = 1) -> (int, str, dict):
        """
        参数化搜索：对高频两项设置前缀/精确索引
        search_index.title_lower: 题目前缀/不区分大小写匹配
        search_index.tags_lower: 标签精确或包含匹配
        """
        try:
            if (not title_prefix or title_prefix.strip() == "") and (not tags or len(tags) == 0):
                return error.error_and_message(400, "搜索条件不能为空") + ({},)
            
            page_size = 10
            
            try:
                page = max(1, int(page)) if page else 1
            except (ValueError, TypeError):
                return error.error_and_message(400, "页码参数无效") + ({},)
            
            skip = (page - 1) * page_size
            
            search_conditions = []
            
            if title_prefix and title_prefix.strip():
                title_lower = title_prefix.strip().lower()
                search_conditions.append({
                    "search_index.title_lower": {"$regex": "^" + title_lower}
                })
            
            if tags and len(tags) > 0:
                # 标签精确或包含匹配
                tags_lower = [tag.lower() for tag in tags if tag.strip()]
                if tags_lower:
                    search_conditions.append({
                        "search_index.tags_lower": {"$in": tags_lower}
                    })
            
            if not search_conditions:
                return error.error_and_message(400, "搜索条件不能为空") + ({},)
            
            if len(search_conditions) == 1:
                search_query = search_conditions[0]
            else:
                search_query = {"$and": search_conditions}
            
            if store_id and store_id.strip():
                # 店铺内搜索
                if not self.store_id_exist(store_id):
                    return error.error_non_exist_store_id(store_id) + ({},)
                
                store_doc = self.db["Stores"].find_one({"_id": store_id}, {"inventory": 1})
                if not store_doc or "inventory" not in store_doc:
                    return 200, "ok", {
                        "books": [],
                        "pagination": {
                            "page": page,
                            "page_size": page_size,
                            "total_count": 0,
                            "total_pages": 0,
                            "has_next": False,
                            "has_prev": False
                        }
                    }
                
                book_ids = [item["book_id"] for item in store_doc["inventory"]]
                if not book_ids:
                    return 200, "ok", {
                        "books": [],
                        "pagination": {
                            "page": page,
                            "page_size": page_size,
                            "total_count": 0,
                            "total_pages": 0,
                            "has_next": False,
                            "has_prev": False
                        }
                    }
                
                # 添加店铺限制条件
                search_query = {"$and": [search_query, {"_id": {"$in": book_ids}}]}
            
            total_count = self.db["Books"].count_documents(search_query)
            books_cursor = self.db["Books"].find(search_query).skip(skip).limit(page_size)
            
            books = []
            for book_doc in books_cursor:
                book_info = {
                    "id": book_doc["_id"],
                    "title": book_doc.get("title", ""),
                    "author": book_doc.get("author", ""),
                    "book_intro": book_doc.get("book_intro", ""),
                    "tags": book_doc.get("tags", [])
                }
                books.append(book_info)
            
            total_pages = (total_count + page_size - 1) // page_size
            result = {
                "books": books,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_count": total_count,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
            
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg, {}
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg, {}
        
        return 200, "ok", result

    def get_book_detail(self, book_id: str) -> (int, str, dict):
        #  获取书籍详情信息
        try:
            if book_id is None or book_id.strip() == "":
                return error.error_and_message(400, "书籍ID不能为空") + ({},)
            
            book_id = book_id.strip()
            
            book_doc = self.db["Books"].find_one({"_id": book_id})
            if book_doc is None:
                return error.error_and_message(404, "书籍不存在") + ({},)
            
            book_detail = {
                "id": book_doc["_id"],
                "title": book_doc.get("title", ""),
                "author": book_doc.get("author", ""),
                "publisher": book_doc.get("publisher", ""),
                "original_title": book_doc.get("original_title", ""),
                "translator": book_doc.get("translator", ""),
                "pub_year": book_doc.get("pub_year", ""),
                "pages": book_doc.get("pages", 0),
                "price": book_doc.get("price", 0),
                "currency_unit": book_doc.get("currency_unit", ""),
                "binding": book_doc.get("binding", ""),
                "isbn": book_doc.get("isbn", ""),
                "author_intro": book_doc.get("author_intro", ""),
                "book_intro": book_doc.get("book_intro", ""),
                "content": book_doc.get("content", ""),
                "tags": book_doc.get("tags", []),
                "pictures": book_doc.get("pictures", [])
            }
            
        except pymongo.errors.PyMongoError as e:
            code, msg, _ = error.exception_db_to_tuple3(e)
            return code, msg, {}
        except BaseException as e:
            code, msg, _ = error.exception_to_tuple3(e)
            return code, msg, {}
        
        return 200, "ok", book_detail