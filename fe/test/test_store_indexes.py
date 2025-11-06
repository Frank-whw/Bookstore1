import pytest
from be.model.store import get_db


class TestStoreIndexes:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.db = get_db()
        yield

    def test_users_token_sparse_index(self):
        indexes = list(self.db["Users"].list_indexes())
        names = {i.get("name") for i in indexes}
        # 文本索引与默认 _id 索引必然存在；我们关注 token 索引存在即可
        assert any("token" in idx.get("key", {}) for idx in indexes) or "token_1" in names

    def test_stores_user_and_inventory_index(self):
        indexes = list(self.db["Stores"].list_indexes())
        keys = [list(i.get("key", {}).keys()) for i in indexes]
        flat_keys = {k for sub in keys for k in sub}
        # user_id 单列索引；inventory.book_id 多键索引
        assert "user_id" in flat_keys
        assert "inventory.book_id" in flat_keys

    def test_orders_compound_indexes(self):
        indexes = list(self.db["Orders"].list_indexes())
        names = {i.get("name") for i in indexes}
        assert "orders_by_buyer_status_time" in names
        assert "orders_status_create_time" in names
        assert "orders_timeout_scan" in names

    def test_books_text_and_prefix_indexes(self):
        indexes = list(self.db["Books"].list_indexes())
        names = {i.get("name") for i in indexes}
        # 文本索引名称：books_text；前缀索引键：search_index.title_lower/tags_lower
        assert "books_text" in names or any(i.get("weights") for i in indexes if i.get("name") == "text")
        keys = [list(i.get("key", {}).keys()) for i in indexes]
        flat_keys = {k for sub in keys for k in sub}
        assert "search_index.title_lower" in flat_keys
        assert "search_index.tags_lower" in flat_keys