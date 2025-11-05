import pytest
import time

from fe import conf
from fe.test.gen_book_data import GenBook
from fe.access.new_buyer import register_new_buyer
from fe.access.seller import Seller
from fe.access.book import Book
from fe.access.buyer import Buyer
from be.model.store import get_db
import uuid


class TestCancelOrder:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.seller_id = "test_cancel_order_seller_id_{}".format(str(uuid.uuid1()))
        self.store_id = "test_cancel_order_store_id_{}".format(str(uuid.uuid1()))
        self.buyer_id = "test_cancel_order_buyer_id_{}".format(str(uuid.uuid1()))
        self.password = self.seller_id
        
        gen_book = GenBook(self.seller_id, self.store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=5
        )
        self.buy_book_info_list = gen_book.buy_book_info_list
        assert ok
        
        self.buyer = register_new_buyer(self.buyer_id, self.password)
        self.seller = Seller(conf.URL, self.seller_id, self.password)
        
        code, self.order_id = self.buyer.new_order(self.store_id, buy_book_id_list)
        assert code == 200
        
        self.total_price = 0
        for item in self.buy_book_info_list:
            book: Book = item[0]
            num = item[1]
            if book.price is not None:
                self.total_price += book.price * num
        
        yield

    def test_cancel_unpaid_order(self):
        code = self.buyer.cancel_order(self.order_id)
        assert code == 200
        
        db = get_db()
        order_doc = db["Orders"].find_one({"_id": self.order_id})
        assert order_doc["status"] == "cancelled"
        assert "cancel_time" in order_doc

    def test_cancel_paid_order(self):
        code = self.buyer.add_funds(self.total_price)
        assert code == 200
        code = self.buyer.payment(self.order_id)
        assert code == 200
        
        db = get_db()
        user_doc = db["Users"].find_one({"_id": self.buyer_id})
        balance_before_cancel = user_doc.get("balance", 0)
        
        code = self.buyer.cancel_order(self.order_id)
        assert code == 200
        
        # 验证订单状态已变为取消
        order_doc = db["Orders"].find_one({"_id": self.order_id})
        assert order_doc["status"] == "cancelled"
        assert "cancel_time" in order_doc
        
        # 验证已退款
        user_doc = db["Users"].find_one({"_id": self.buyer_id})
        balance_after_cancel = user_doc.get("balance", 0)
        assert balance_after_cancel == balance_before_cancel + self.total_price

    def test_cancel_shipped_order(self):
        code = self.buyer.add_funds(self.total_price)
        assert code == 200
        code = self.buyer.payment(self.order_id)
        assert code == 200
        
        code = self.seller.ship_order(self.order_id)
        assert code == 200
        
        # 尝试取消订单
        code = self.buyer.cancel_order(self.order_id)
        assert code != 200

    def test_cancel_non_exist_order(self):
        code = self.buyer.cancel_order(self.order_id + "_x")
        assert code != 200

    def test_cancel_other_user_order(self):
        other_buyer_id = "test_cancel_other_buyer_{}".format(str(uuid.uuid1()))
        other_buyer = register_new_buyer(other_buyer_id, self.password)
        
        code = other_buyer.cancel_order(self.order_id)
        assert code != 200

    def test_repeat_cancel(self):
        code = self.buyer.cancel_order(self.order_id)
        assert code == 200
        
        # 再次取消
        code = self.buyer.cancel_order(self.order_id)
        assert code != 200

    def test_auto_cancel_timeout_orders(self):
        # 修改创建时间来创建一个超时的订单
        timeout_seller_id = "test_timeout_seller_{}".format(str(uuid.uuid1()))
        timeout_store_id = "test_timeout_store_{}".format(str(uuid.uuid1()))
        timeout_buyer_id = "test_timeout_buyer_{}".format(str(uuid.uuid1()))
        
        gen_book = GenBook(timeout_seller_id, timeout_store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=1
        )
        assert ok
        
        timeout_buyer = register_new_buyer(timeout_buyer_id, timeout_seller_id)
        code, timeout_order_id = timeout_buyer.new_order(timeout_store_id, buy_book_id_list)
        assert code == 200

        # 25小时前的订单
        db = get_db()
        timeout_time = time.time() - 25 * 3600
        db["Orders"].update_one(
            {"_id": timeout_order_id},
            {"$set": {"create_time": timeout_time}}
        )
        
        code, cancelled_count = Buyer.auto_cancel_timeout_orders(conf.URL)
        assert code == 200
        assert cancelled_count >= 1
        
        # 验证订单已被取消
        order_doc = db["Orders"].find_one({"_id": timeout_order_id})
        assert order_doc["status"] == "cancelled"
        assert "timeout_at" in order_doc

    def test_auto_cancel_no_timeout_orders(self):
        # 未超时订单
        recent_seller_id = "test_recent_seller_{}".format(str(uuid.uuid1()))
        recent_store_id = "test_recent_store_{}".format(str(uuid.uuid1()))
        recent_buyer_id = "test_recent_buyer_{}".format(str(uuid.uuid1()))
        
        gen_book = GenBook(recent_seller_id, recent_store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=1
        )
        assert ok
        
        recent_buyer = register_new_buyer(recent_buyer_id, recent_seller_id)
        code, recent_order_id = recent_buyer.new_order(recent_store_id, buy_book_id_list)
        assert code == 200

        code, cancelled_count = Buyer.auto_cancel_timeout_orders(conf.URL)
        assert code == 200
        
        # 验证订单状态未变
        db = get_db()
        order_doc = db["Orders"].find_one({"_id": recent_order_id})
        assert order_doc["status"] == "unpaid"
        assert "timeout_at" not in order_doc
