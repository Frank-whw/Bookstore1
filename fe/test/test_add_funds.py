import pytest
import uuid
from fe.access.new_buyer import register_new_buyer


class TestAddFunds:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.user_id = "test_add_funds_{}".format(str(uuid.uuid1()))
        self.password = self.user_id
        self.buyer = register_new_buyer(self.user_id, self.password)
        yield

    def test_ok(self):
        code = self.buyer.add_funds(1000)
        assert code == 200

        code = self.buyer.add_funds(-1000)
        assert code == 200

    def test_error_user_id(self):
        self.buyer.user_id = self.buyer.user_id + "_x"
        code = self.buyer.add_funds(10)
        assert code != 200

    def test_error_password(self):
        self.buyer.password = self.buyer.password + "_x"
        code = self.buyer.add_funds(10)
        assert code != 200

    def test_non_numeric_input(self):
        # 非数字字符串
        code = self.buyer.add_funds("abc")
        assert code != 200
        # None 值
        code = self.buyer.add_funds(None)
        assert code != 200
        # 可解析的数字字符串
        code = self.buyer.add_funds("50")
        assert code == 200
