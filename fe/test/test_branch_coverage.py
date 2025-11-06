import uuid
import pytest

from fe import conf
from fe.access import book
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer
from fe.access.seller import Seller
from be.model.store import get_db


class TestAddBookTypeConversion:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.seller_id = f"branch_add_book_seller_{uuid.uuid1()}"
        self.store_id = f"branch_add_book_store_{uuid.uuid1()}"
        self.password = self.seller_id
        self.seller = register_new_seller(self.seller_id, self.password)
        assert self.seller.create_store(self.store_id) == 200
        self.book_db = book.BookDB(conf.Use_Large_DB)
        self.books = self.book_db.get_book_info(0, 2)
        yield

    def test_stock_level_string_numeric(self):
        bk = self.books[0]
        # 传入字符串数字，验证模型层转换为 int
        code = self.seller.add_book(self.store_id, "7", bk)
        assert code == 200

        db = get_db()
        store_doc = db["Stores"].find_one(
            {"_id": self.store_id, "inventory": {"$elemMatch": {"book_id": bk.id}}},
            {"inventory.$": 1},
        )
        assert store_doc and store_doc.get("inventory")
        assert store_doc["inventory"][0].get("stock_level") == 7

    def test_stock_level_string_invalid(self):
        bk = self.books[1]
        # 传入不可解析字符串，模型层应回落为 0
        code = self.seller.add_book(self.store_id, "bad_value", bk)
        assert code == 200

        db = get_db()
        store_doc = db["Stores"].find_one(
            {"_id": self.store_id, "inventory": {"$elemMatch": {"book_id": bk.id}}},
            {"inventory.$": 1},
        )
        assert store_doc and store_doc.get("inventory")
        assert store_doc["inventory"][0].get("stock_level") == 0


class TestAddStockLevelTypeConversion:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.seller_id = f"branch_add_stock_seller_{uuid.uuid1()}"
        self.store_id = f"branch_add_stock_store_{uuid.uuid1()}"
        self.password = self.seller_id
        self.seller = register_new_seller(self.seller_id, self.password)
        assert self.seller.create_store(self.store_id) == 200
        self.book_db = book.BookDB(conf.Use_Large_DB)
        self.bk = self.book_db.get_book_info(0, 1)[0]
        # 初始库存 0
        assert self.seller.add_book(self.store_id, 0, self.bk) == 200
        yield

    def test_add_stock_level_string_numeric(self):
        code = self.seller.add_stock_level(self.seller_id, self.store_id, self.bk.id, "10")
        assert code == 200

        db = get_db()
        store_doc = db["Stores"].find_one(
            {"_id": self.store_id, "inventory": {"$elemMatch": {"book_id": self.bk.id}}},
            {"inventory.$": 1},
        )
        assert store_doc and store_doc.get("inventory")
        assert store_doc["inventory"][0].get("stock_level") == 10

    def test_add_stock_level_string_invalid(self):
        # 不可解析字符串，增量应视为 0
        code = self.seller.add_stock_level(self.seller_id, self.store_id, self.bk.id, "abc")
        assert code == 200

        db = get_db()
        store_doc = db["Stores"].find_one(
            {"_id": self.store_id, "inventory": {"$elemMatch": {"book_id": self.bk.id}}},
            {"inventory.$": 1},
        )
        assert store_doc and store_doc.get("inventory")
        # 初始库存为 0，增量不可解析按 0 处理，库存仍为 0
        assert store_doc["inventory"][0].get("stock_level") == 0


class TestShipOrderNegativeBranches:
    def _prepare_paid_order(self, max_book_count=3):
        seller_id = f"branch_ship_seller_{uuid.uuid1()}"
        store_id = f"branch_ship_store_{uuid.uuid1()}"
        buyer_id = f"branch_ship_buyer_{uuid.uuid1()}"
        password = seller_id

        gen = None
        # 生成店铺与书目
        gen = __import__("fe.test.gen_book_data", fromlist=["GenBook"]).GenBook(seller_id, store_id)
        ok, id_and_count = gen.gen(non_exist_book_id=False, low_stock_level=False, max_book_count=max_book_count)
        assert ok

        buyer = register_new_buyer(buyer_id, password)
        code, order_id = buyer.new_order(store_id, id_and_count)
        assert code == 200

        # 充值并支付
        total_price = 0
        for bk, num in gen.buy_book_info_list:
            if bk.price is not None:
                total_price += bk.price * num
        assert buyer.add_funds(total_price) == 200
        assert buyer.payment(order_id) == 200

        return seller_id, store_id, buyer, order_id

    def test_ship_order_missing_book(self):
        seller_id, store_id, buyer, order_id = self._prepare_paid_order(max_book_count=2)

        db = get_db()
        order_doc = db["Orders"].find_one({"_id": order_id})
        assert order_doc and order_doc.get("items")
        removed_book_id = order_doc["items"][0]["book_id"]

        # 从库存中移除该书，触发发货时的缺书分支
        db["Stores"].update_one({"_id": store_id}, {"$pull": {"inventory": {"book_id": removed_book_id}}})

        seller = Seller(conf.URL, seller_id, seller_id)
        code = seller.ship_order(order_id)
        assert code != 200

    def test_ship_order_low_stock(self):
        seller_id, store_id, buyer, order_id = self._prepare_paid_order(max_book_count=2)

        db = get_db()
        order_doc = db["Orders"].find_one({"_id": order_id})
        assert order_doc and order_doc.get("items")
        # 将其中一本库存改为小于购买数量，触发库存不足分支
        book_id = order_doc["items"][0]["book_id"]
        quantity = order_doc["items"][0]["quantity"]
        new_stock = max(0, quantity - 1)
        db["Stores"].update_one(
            {"_id": store_id, "inventory.book_id": book_id},
            {"$set": {"inventory.$.stock_level": new_stock}},
        )

        seller = Seller(conf.URL, seller_id, seller_id)
        code = seller.ship_order(order_id)
        assert code != 200


class TestAddFundsInsufficient:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.user_id = f"branch_add_funds_user_{uuid.uuid1()}"
        self.password = self.user_id
        self.buyer = register_new_buyer(self.user_id, self.password)
        yield

    def test_withdraw_exceed_balance(self):
        # 初始余额为 0，直接扣款应失败
        code = self.buyer.add_funds(-200)
        assert code != 200

        # 充值后再尝试过量扣款也应失败
        assert self.buyer.add_funds(100) == 200
        code = self.buyer.add_funds(-200)
        assert code != 200