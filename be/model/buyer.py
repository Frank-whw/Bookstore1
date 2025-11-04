import pymongo
import uuid
import logging
import time
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
                # 获取店铺库存并匹配该书
                # 使用 $elemMatch + 投影仅返回匹配的库存项
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
                # sqlite代码逻辑是这边直接更新库存，但是后面要涉及发货
                # 所以更新库存的逻辑放在发货函数中

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
            '''
            sqlite这边的逻辑是：买家的balance直接 - total_amount,卖家的balance直接 + total_amount
            如果涉及发货收货，逻辑应该要改一下：
            1. 下单的时候扣款，收货的时候收款
            2. 收货的时候扣款+收款

            选择1
            统一一下业务流程：
            下单 买家扣款，发货 book的stock_level减少，收货 卖家收款
            '''
            # 删除重复扣款（已在上方完成一次扣款）
            # 更新订单状态
            # sqlite的逻辑是直接删除订单，这里使用status记录订单状态
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
            db["Users"].update_one({
                "_id": user_id
            },{
                "$inc":{"balance": add_value}
            })
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
    
    # 取消订单
    def cancel_order(self, user_id: str, order_id: str) -> (int, str):
        try:
            db = self.db
            order_doc = db["Orders"].find_one({"_id": order_id})
            if order_doc is None:
                return error.error_invalid_order_id(order_id)
            if order_doc.get("buyer_id") != user_id:
                return error.error_authorization_fail()
            status = order_doc.get("status")
            if status != "unpaid":
                if status == "cancelled":
                    return error.error_order_cancelled(order_id)
                if status in ("paid", "completed"):
                    return error.error_order_completed(order_id)
                return error.error_order_status_mismatch(order_id)
            updated = db["Orders"].update_one(
                {"_id": order_id, "status": "unpaid"},
                {"$set": {"status": "cancelled", "cancel_time": time.time()}}
            )
            if updated.matched_count == 0:
                return error.error_invalid_order_id(order_id)
            # 买家退款
            # 直接退款（不需要余额条件），若后续需要事务可加入 session
            db["Users"].update_one(
                {"_id": user_id},
                {"$inc": {"balance": order_doc.get("total_amount", 0)}}
            )
            return 200, "ok"
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