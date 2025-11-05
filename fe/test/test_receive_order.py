import pytest

from fe import conf
from fe.test.gen_book_data import GenBook
from fe.access.new_buyer import register_new_buyer
from fe.access.seller import Seller
from fe.access.book import Book
from be.model.store import get_db
import uuid


class TestReceiveOrder:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.seller_id = "test_receive_order_seller_id_{}".format(str(uuid.uuid1()))
        self.store_id = "test_receive_order_store_id_{}".format(str(uuid.uuid1()))
        self.buyer_id = "test_receive_order_buyer_id_{}".format(str(uuid.uuid1()))
        self.password = self.seller_id
        
        gen_book = GenBook(self.seller_id, self.store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=5
        )
        self.buy_book_info_list = gen_book.buy_book_info_list
        assert ok
        
        self.buyer = register_new_buyer(self.buyer_id, self.password)
        code, self.order_id = self.buyer.new_order(self.store_id, buy_book_id_list)
        assert code == 200
        
        # 计算总价并支付
        self.total_price = 0
        for item in self.buy_book_info_list:
            book: Book = item[0]
            num = item[1]
            if book.price is not None:
                self.total_price += book.price * num
        
        code = self.buyer.add_funds(self.total_price)
        assert code == 200
        code = self.buyer.payment(self.order_id)
        assert code == 200
        
        # 发货
        self.seller = Seller(conf.URL, self.seller_id, self.password)
        code = self.seller.ship_order(self.order_id)
        assert code == 200
        
        yield

    def test_ok(self):
        code = self.buyer.receive_order(self.order_id)
        assert code == 200

    def test_non_exist_order_id(self):
        code = self.buyer.receive_order(self.order_id + "_x")
        assert code != 200

    def test_order_status_unshipped(self):
        # 创建新的卖家和店铺来避免重复注册
        temp_seller_id = "test_receive_order_temp_seller_{}".format(str(uuid.uuid1()))
        temp_store_id = "test_receive_order_temp_store_{}".format(str(uuid.uuid1()))
        gen_book = GenBook(temp_seller_id, temp_store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=3
        )
        assert ok
        code, order_id = self.buyer.new_order(temp_store_id, buy_book_id_list)
        assert code == 200
        
        # 支付但不发货
        total = 0
        for item in gen_book.buy_book_info_list:
            book: Book = item[0]
            num = item[1]
            if book.price is not None:
                total += book.price * num
        
        code = self.buyer.add_funds(total)
        assert code == 200
        code = self.buyer.payment(order_id)
        assert code == 200
        
        code = self.buyer.receive_order(order_id)
        assert code != 200

    def test_order_status_unpaid(self):
        # 创建新的卖家和店铺来避免重复注册
        temp_seller_id = "test_receive_order_temp_seller2_{}".format(str(uuid.uuid1()))
        temp_store_id = "test_receive_order_temp_store2_{}".format(str(uuid.uuid1()))
        gen_book = GenBook(temp_seller_id, temp_store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=3
        )
        assert ok
        code, unpaid_order_id = self.buyer.new_order(temp_store_id, buy_book_id_list)
        assert code == 200
        
        code = self.buyer.receive_order(unpaid_order_id)
        assert code != 200

    def test_authorization_error(self):
        other_buyer_id = "test_receive_order_other_buyer_{}".format(str(uuid.uuid1()))
        other_buyer = register_new_buyer(other_buyer_id, self.password)
        
        code = other_buyer.receive_order(self.order_id)
        assert code != 200

    def test_repeat_receive(self):
        code = self.buyer.receive_order(self.order_id)
        assert code == 200
        
        code = self.buyer.receive_order(self.order_id)
        assert code != 200

    def test_seller_balance_increase(self):
        # 获取收货前卖家余额
        db = get_db()
        seller_doc = db["Users"].find_one({"_id": self.seller_id}, {"balance": 1})
        initial_balance = seller_doc.get("balance", 0) if seller_doc else 0
        
        # 收货
        code = self.buyer.receive_order(self.order_id)
        assert code == 200
        
        # 验证卖家余额增加
        seller_doc = db["Users"].find_one({"_id": self.seller_id}, {"balance": 1})
        current_balance = seller_doc.get("balance", 0) if seller_doc else 0
        expected_balance = initial_balance + self.total_price
        
        assert current_balance == expected_balance