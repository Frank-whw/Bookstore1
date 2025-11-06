import uuid
from fe.access.new_seller import register_new_seller
from fe import conf
from fe.access.seller import Seller


class TestCreateStoreNegative:
    def test_user_not_exist(self):
        seller_id = f"create_store_neg_{uuid.uuid1()}"
        password = seller_id
        s = register_new_seller(seller_id, password)
        # 登录成功后再篡改 seller_id，避免构造函数断言失败
        s.seller_id = s.seller_id + "_x"
        code = s.create_store(f"store_neg_{uuid.uuid1()}")
        assert code != 200