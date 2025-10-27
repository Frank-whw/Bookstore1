import pymongo
import uuid
import logging
import time
from be.model import db_conn
from be.model import error

class Buyer(db_conn.DBConn):
    def __init__(self):
        db_conn.DBConn.__init__()
    
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
            db = self.conn["bookstore"]

            total_amount = 0
            items = []
            for book_id, count in id_and_count:
                # 获取店铺库存并匹配该书
                store_doc = db["Stores"].find_one({"_id": store_id})
                if store_doc is None or "inventory" not in store_doc:
                    return error.error_non_exist_store_id(store_id) + (order_id,)
                inv_item = None
                for it in store_doc.get("inventory", []):
                    if it.get("book_id") == book_id:
                        inv_item = it
                        break
                if inv_item is None:
                    return error.error_non_exist_book_id(book_id) + (order_id,)
                store_level = inv_item.get("stock_level", 0)
                price = inv_item.get("price", 0)
                book_info = inv_item.get("book_info")
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
            logging.info("528, {}".format(str(e)))
            return 528, "{}".format(str(e)), ""
        except BaseException as e:
            logging.info("530, {}".format(str(e)))
            return 530, "{}".format(str(e)), ""
        
        return 200, "ok", order_id
    def payment(self, user_id: str, password: str, order_id: str) -> (int, str):
        try:
            db = self.conn["bookstore"]
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

            # 防重复支付
            if order_doc.get("status") != "unpaid":
                return error.error_invalid_order_id(order_id)

            if balance < total_amount:
                return error.error_not_sufficient_funds(order_id)

            # 买家扣款
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
            # 买家扣款
            self.conn["bookstore"][Users].update_one({
                "_id": buyer_id
            }, {
                "$inc": {
                    "balance": -total_amount
                }
            })
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
            return 528, "{}".format(str(e))

        except BaseException as e:
            return 530, "{}".format(str(e))

        return 200, "ok"
    
    def add_funds(self, user_id, password, add_value) -> (int, str):
        try:
            db = self.conn["bookstore"]
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
            return 528, "{}".format(str(e))
        except BaseException as e:
            return 530, "{}".format(str(e))

        return 200, "ok"
    
    # 订单查询
    def get_order(self, user_id: str, order_id: str) -> (int, str, dict):
        try:
            db = self.conn["bookstore"]
            order_doc = db["Orders"].find_one({"_id": order_id})
            if order_doc is None:
                return error.error_invalid_order_id(order_id)
            if order_doc.get("buyer_id") != user_id:
                return error.error_authorization_fail()
            return 200, "ok", order_doc
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        except BaseException as e:
            return 530, "{}".format(str(e))
    
    # 取消订单
    def cancel_order(self, user_id: str, order_id: str) -> (int, str):
        try:
            db = self.conn["bookstore"]
            order_doc = db["Orders"].find_one({"_id": order_id})
            if order_doc is None:
                return error.error_invalid_order_id(order_id)
            if order_doc.get("buyer_id") != user_id:
                return error.error_authorization_fail()
            if order_doc.get("status") != "unpaid":
                return error.error_invalid_order_id(order_id)
            db["Orders"].update_one({
                "_id": order_id
            },{
                "$set":{"status":"canceled"}
            })
            # 买家退款
            res = db["Users"].update_one(
                {
                    "_id": user_id, 
                    "balance": {"$gte": order_doc.get("total_amount", 0)}
                },{
                    "$inc": {"balance": order_doc.get("total_amount", 0)}
                })
            if res.matched_count == 0:
                # 状态更新失败则回滚取消订单
                db["Orders"].update_one({
                    "_id": order_id
                },{
                    "$set":{"status":"unpaid"}
                })
                return error.error_not_sufficient_funds(order_id)
            return 200, "ok"
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        except BaseException as e:
            return 530, "{}".format(str(e))