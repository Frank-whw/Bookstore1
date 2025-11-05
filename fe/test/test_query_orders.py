import pytest

from fe import conf
from fe.test.gen_book_data import GenBook
from fe.access.new_buyer import register_new_buyer
from fe.access.seller import Seller
from fe.access.book import Book
import uuid


class TestQueryOrders:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.seller_id = "test_query_orders_seller_id_{}".format(str(uuid.uuid1()))
        self.store_id = "test_query_orders_store_id_{}".format(str(uuid.uuid1()))
        self.buyer_id = "test_query_orders_buyer_id_{}".format(str(uuid.uuid1()))
        self.password = self.seller_id
        
        gen_book = GenBook(self.seller_id, self.store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=5
        )
        self.buy_book_info_list = gen_book.buy_book_info_list
        assert ok
        
        self.buyer = register_new_buyer(self.buyer_id, self.password)
        self.seller = Seller(conf.URL, self.seller_id, self.password)

        self.order_ids = []
        for i in range(12): # 创建12个订单，能测试分页
            code, order_id = self.buyer.new_order(self.store_id, buy_book_id_list[:2])
            assert code == 200
            self.order_ids.append(order_id)
        
        self.total_price = 0
        for item in self.buy_book_info_list[:2]:
            book: Book = item[0]
            num = item[1]
            if book.price is not None:
                self.total_price += book.price * num
        
        code = self.buyer.add_funds(self.total_price * 12)
        assert code == 200
        # 支付前3个订单
        for i in range(3):
            code = self.buyer.payment(self.order_ids[i])
            assert code == 200
        
        yield

    def test_buyer_query_all_orders(self):
        code, result = self.buyer.query_orders()
        assert code == 200
        assert "orders" in result
        assert "pagination" in result
        assert len(result["orders"]) == 10  # 第一页规定10条
        assert result["pagination"]["total_count"] == 12

    def test_buyer_query_orders_by_status(self):
        # 查询未支付订单
        code, result = self.buyer.query_orders(status="unpaid")
        assert code == 200
        assert len(result["orders"]) == 9
        for order in result["orders"]:
            assert order["status"] == "unpaid"
        
        # 查询已支付订单
        code, result = self.buyer.query_orders(status="paid")
        assert code == 200
        assert len(result["orders"]) == 3
        for order in result["orders"]:
            assert order["status"] == "paid"

    def test_buyer_query_orders_pagination(self):
        code, result = self.buyer.query_orders(page=1)
        assert code == 200
        assert len(result["orders"]) <= 10
        assert result["pagination"]["page"] == 1
        assert result["pagination"]["page_size"] == 10
        
        if result["pagination"]["total_count"] > 10:
            code, result2 = self.buyer.query_orders(page=2)
            assert code == 200
            page1_ids = [order["order_id"] for order in result["orders"]]
            page2_ids = [order["order_id"] for order in result2["orders"]]
            assert len(set(page1_ids) & set(page2_ids)) == 0
    def test_query_orders_invalid_user(self):
        self.buyer.user_id = self.buyer.user_id + "_x"
        code, result = self.buyer.query_orders()
        assert code == 511

    def test_query_orders_empty_status(self):
        code, result = self.buyer.query_orders(status="")
        assert code == 200
        # 空状态应该返回所有订单
        assert len(result["orders"]) == 10
        assert result["pagination"]["total_count"] == 12

    def test_query_orders_nonexistent_status(self):
        code, result = self.buyer.query_orders(status="nonexistent")
        assert code == 200
        assert len(result["orders"]) == 0
        assert result["pagination"]["total_count"] == 0