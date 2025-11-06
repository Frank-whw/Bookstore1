import uuid
import pytest

from fe import conf
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer
from fe.access.seller import Seller
from be.model.store import get_db


class TestShipOrderExtended:
    def _prepare_paid_order(self, max_book_count=3):
        seller_id = f"ship_ext_seller_{uuid.uuid1()}"
        store_id = f"ship_ext_store_{uuid.uuid1()}"
        buyer_id = f"ship_ext_buyer_{uuid.uuid1()}"
        password = seller_id

        # 生成店铺与书目
        gen = __import__("fe.test.gen_book_data", fromlist=["GenBook"]).GenBook(
            seller_id, store_id
        )
        ok, id_and_count = gen.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=max_book_count
        )
        assert ok

        # 下单并支付
        buyer = register_new_buyer(buyer_id, password)
        code, order_id = buyer.new_order(store_id, id_and_count)
        assert code == 200

        # 计算总价并支付
        total_price = 0
        for bk, num in gen.buy_book_info_list:
            if bk.price is not None:
                total_price += bk.price * num
        assert buyer.add_funds(total_price) == 200
        assert buyer.payment(order_id) == 200

        return seller_id, store_id, order_id

    def _prepare_unpaid_order(self, max_book_count=2):
        seller_id = f"ship_ext_unpaid_seller_{uuid.uuid1()}"
        store_id = f"ship_ext_unpaid_store_{uuid.uuid1()}"
        buyer_id = f"ship_ext_unpaid_buyer_{uuid.uuid1()}"
        password = seller_id

        gen = __import__("fe.test.gen_book_data", fromlist=["GenBook"]).GenBook(
            seller_id, store_id
        )
        ok, id_and_count = gen.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=max_book_count
        )
        assert ok

        buyer = register_new_buyer(buyer_id, password)
        code, order_id = buyer.new_order(store_id, id_and_count)
        assert code == 200
        return seller_id, store_id, order_id

    def test_ship_order_ok(self):
        seller_id, store_id, order_id = self._prepare_paid_order(max_book_count=2)

        # 记录发货前库存
        db = get_db()
        order_doc = db["Orders"].find_one({"_id": order_id})
        assert order_doc and order_doc.get("items")
        before_stock = {}
        for item in order_doc["items"]:
            book_id = item["book_id"]
            doc = db["Stores"].find_one(
                {"_id": store_id, "inventory": {"$elemMatch": {"book_id": book_id}}},
                {"inventory.$": 1},
            )
            assert doc and doc.get("inventory")
            before_stock[book_id] = doc["inventory"][0].get("stock_level", 0)

        seller = Seller(conf.URL, seller_id, seller_id)
        code = seller.ship_order(order_id)
        assert code == 200

        # 校验订单状态与库存变更
        order_after = db["Orders"].find_one({"_id": order_id})
        assert order_after.get("status") == "shipped"
        assert order_after.get("ship_time") is not None

        for item in order_doc["items"]:
            book_id = item["book_id"]
            quantity = item["quantity"]
            doc = db["Stores"].find_one(
                {"_id": store_id, "inventory": {"$elemMatch": {"book_id": book_id}}},
                {"inventory.$": 1},
            )
            assert doc and doc.get("inventory")
            assert doc["inventory"][0].get("stock_level", 0) == before_stock[book_id] - quantity

    def test_ship_order_invalid_user(self):
        seller_id, store_id, order_id = self._prepare_paid_order(max_book_count=2)
        seller = Seller(conf.URL, seller_id, seller_id)
        # 修改为不存在的用户ID以触发 511
        seller.seller_id = seller.seller_id + "_x"
        code = seller.ship_order(order_id)
        assert code != 200

    def test_ship_order_invalid_order_id(self):
        seller_id, store_id, order_id = self._prepare_paid_order(max_book_count=2)
        seller = Seller(conf.URL, seller_id, seller_id)
        code = seller.ship_order(order_id + "_x")
        assert code != 200

    def test_ship_order_authorization_fail(self):
        seller_id, store_id, order_id = self._prepare_paid_order(max_book_count=2)
        # 使用另一个卖家发货，触发 401 权限失败
        other_seller_id = f"ship_ext_other_seller_{uuid.uuid1()}"
        other_password = other_seller_id
        other_seller = register_new_seller(other_seller_id, other_password)
        code = other_seller.ship_order(order_id)
        assert code == 401 or code != 200

    def test_ship_order_status_mismatch(self):
        seller_id, store_id, order_id = self._prepare_unpaid_order(max_book_count=2)
        seller = Seller(conf.URL, seller_id, seller_id)
        code = seller.ship_order(order_id)
        assert code != 200