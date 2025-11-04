import pytest

from fe import conf
from fe.test.gen_book_data import GenBook
from fe.access.new_buyer import register_new_buyer
from fe.access.new_seller import register_new_seller
from fe.access.seller import Seller
from fe.access.book import Book
import uuid


class TestShipOrder:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.seller_id = "test_ship_order_seller_id_{}".format(str(uuid.uuid1()))
        self.store_id = "test_ship_order_store_id_{}".format(str(uuid.uuid1()))
        self.buyer_id = "test_ship_order_buyer_id_{}".format(str(uuid.uuid1()))
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
        
        self.seller = Seller(conf.URL, self.seller_id, self.password)
        yield

    def test_ok(self):
        code = self.seller.ship_order(self.order_id)
        assert code == 200

    def test_non_exist_order_id(self):
        code = self.seller.ship_order(self.order_id + "_x")
        assert code != 200

    def test_order_status_unpaid(self):
        gen_book = GenBook(self.seller_id, self.store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=3
        )
        assert ok
        code, unpaid_order_id = self.buyer.new_order(self.store_id, buy_book_id_list)
        assert code == 200
        
        code = self.seller.ship_order(unpaid_order_id)
        assert code != 200

    def test_authorization_error(self):
        other_seller_id = "test_ship_order_other_seller_{}".format(str(uuid.uuid1()))
        other_seller = register_new_seller(other_seller_id, self.password)
        
        code = other_seller.ship_order(self.order_id)
        assert code != 200

    def test_repeat_ship(self):
        code = self.seller.ship_order(self.order_id)
        assert code == 200
        
        code = self.seller.ship_order(self.order_id)
        assert code != 200

    def test_stock_level_decrease(self):
        # 记录发货前的库存信息
        initial_stocks = {}
        for item in self.buy_book_info_list:
            book: Book = item[0]
            initial_stocks[book.id] = item[1]
        
        # 发货
        code = self.seller.ship_order(self.order_id)
        assert code == 200
        
        # 验证订单状态变为已发货
        code, order_info = self.buyer.query_order_status(self.order_id)
        assert code == 200
        assert order_info.get("status") == "shipped"