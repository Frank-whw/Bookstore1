import json
import copy
import time
from contextlib import contextmanager

import pytest
from pymongo import ReturnDocument
from pymongo import errors as pymongo_errors

from be.model import error
from be.model.seller import Seller
from be.model.buyer import Buyer
from be.model import store as store_module


class FakeUpdateResult:
    def __init__(self, matched_count: int, modified_count: int):
        self.matched_count = matched_count
        self.modified_count = modified_count


class FakeCursor:
    def __init__(self, documents):
        # 使用深拷贝，避免测试过程对原始数据造成污染
        self._documents = [copy.deepcopy(doc) for doc in documents]

    def sort(self, key, direction=None):
        if isinstance(key, list):
            # pymongo 支持按多个字段排序；这里倒序应用，模拟链式排序
            for field, order in reversed(key):
                if isinstance(order, dict):
                    # 文本搜索的 score 排序，这里不做特殊处理
                    continue
                reverse = order == -1
                self._documents.sort(key=lambda d: d.get(field), reverse=reverse)
        else:
            reverse = direction == -1
            self._documents.sort(key=lambda d: d.get(key), reverse=reverse)
        return self

    def skip(self, count: int):
        self._documents = self._documents[count:]
        return self

    def limit(self, count: int):
        if count:
            self._documents = self._documents[:count]
        return self

    def __iter__(self):
        for doc in self._documents:
            yield copy.deepcopy(doc)


class UsersCollection:
    def __init__(self, documents):
        self.documents = {doc["_id"]: copy.deepcopy(doc) for doc in documents}

    def find_one(self, query):
        user_id = query.get("_id")
        doc = self.documents.get(user_id)
        return copy.deepcopy(doc) if doc is not None else None

    def update_one(self, query, update):
        user_id = query.get("_id")
        doc = self.documents.get(user_id)
        if doc is None:
            return FakeUpdateResult(0, 0)

        balance_cond = query.get("balance")
        if isinstance(balance_cond, dict) and "$gte" in balance_cond:
            if doc.get("balance", 0) < balance_cond["$gte"]:
                return FakeUpdateResult(0, 0)

        modified = False
        if "$inc" in update:
            for field, delta in update["$inc"].items():
                doc[field] = doc.get(field, 0) + delta
                modified = True

        if "$set" in update:
            for field, value in update["$set"].items():
                doc[field] = value
                modified = True

        if "$unset" in update:
            for field in update["$unset"].keys():
                doc.pop(field, None)
                modified = True

        return FakeUpdateResult(1, 1 if modified else 0)


class StoresCollection:
    def __init__(self, documents):
        self.documents = {doc["_id"]: copy.deepcopy(doc) for doc in documents}

    def find_one(self, query, projection=None):
        store_id = query.get("_id")
        store = self.documents.get(store_id)
        if store is None:
            return None

        user_id = query.get("user_id")
        if user_id is not None and store.get("user_id") != user_id:
            return None

        inventory_query = query.get("inventory")
        matched_item = None
        if isinstance(inventory_query, dict) and "$elemMatch" in inventory_query:
            target = inventory_query["$elemMatch"]
            for item in store.get("inventory", []):
                matches = all(item.get(k) == v for k, v in target.items())
                if matches:
                    matched_item = copy.deepcopy(item)
                    break
            if matched_item is None:
                return None

        if projection and "inventory.$" in projection and matched_item is not None:
            return {"_id": store_id, "inventory": [matched_item]}

        return copy.deepcopy(store)

    def insert_one(self, document):
        self.documents[document["_id"]] = copy.deepcopy(document)

    def update_one(self, query, update):
        store_id = query.get("_id")
        store = self.documents.get(store_id)
        if store is None:
            return FakeUpdateResult(0, 0)

        inventory_item = None
        book_id_filter = query.get("inventory.book_id")
        if book_id_filter is not None:
            for item in store.get("inventory", []):
                if item.get("book_id") == book_id_filter:
                    inventory_item = item
                    break
            if inventory_item is None:
                return FakeUpdateResult(0, 0)

        stock_filter = query.get("inventory.stock_level")
        if isinstance(stock_filter, dict) and inventory_item is not None:
            if inventory_item.get("stock_level", 0) < stock_filter.get("$gte", 0):
                return FakeUpdateResult(0, 0)

        modified = False
        if "$push" in update:
            for field, value in update["$push"].items():
                store.setdefault(field, []).append(copy.deepcopy(value))
                modified = True

        if "$inc" in update:
            for field, delta in update["$inc"].items():
                if field == "inventory.$.stock_level" and inventory_item is not None:
                    inventory_item["stock_level"] = inventory_item.get("stock_level", 0) + delta
                    modified = True
                else:
                    store[field] = store.get(field, 0) + delta
                    modified = True

        if "$set" in update:
            for field, value in update["$set"].items():
                store[field] = value
                modified = True

        if "$unset" in update:
            for field in update["$unset"].keys():
                store.pop(field, None)
                modified = True

        return FakeUpdateResult(1, 1 if modified else 0)


class OrdersCollection:
    def __init__(self, documents):
        self.documents = {doc["_id"]: copy.deepcopy(doc) for doc in documents}

    def find_one(self, query):
        for order in self.documents.values():
            if all(order.get(k) == v for k, v in query.items()):
                return copy.deepcopy(order)
        return None

    def insert_one(self, document):
        self.documents[document["_id"]] = copy.deepcopy(document)

    def update_one(self, query, update):
        for order in self.documents.values():
            if all(order.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                modified = False
                if "$set" in update:
                    for field, value in update["$set"].items():
                        order[field] = value
                        modified = True
                if "$unset" in update:
                    for field in update["$unset"].keys():
                        order.pop(field, None)
                        modified = True
                return FakeUpdateResult(1, 1 if modified else 0)
        return FakeUpdateResult(0, 0)

    def find_one_and_update(self, query, update, return_document=None):
        for order_id, order in self.documents.items():
            if all(order.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                before = copy.deepcopy(order)
                if "$set" in update:
                    for field, value in update["$set"].items():
                        order[field] = value
                if "$unset" in update:
                    for field in update["$unset"].keys():
                        order.pop(field, None)
                if return_document == ReturnDocument.BEFORE:
                    return before
                return copy.deepcopy(order)
        return None

    def count_documents(self, query):
        return len(list(self._filter(query)))

    def find(self, query, projection=None):
        return FakeCursor(list(self._filter(query)))

    def _filter(self, query):
        for order in self.documents.values():
            match = True
            for key, value in query.items():
                if isinstance(value, dict) and "$lt" in value:
                    if not order.get(key, 0) < value["$lt"]:
                        match = False
                        break
                elif order.get(key) != value:
                    match = False
                    break
            if match:
                yield copy.deepcopy(order)


class BooksCollection:
    def __init__(self, documents):
        self.documents = {doc["_id"]: copy.deepcopy(doc) for doc in documents}

    def find_one(self, query, projection=None):
        doc = self.documents.get(query.get("_id"))
        return copy.deepcopy(doc) if doc else None

    def count_documents(self, query):
        return len(list(self._filter(query)))

    def find(self, query, projection=None):
        docs = list(self._filter(query))
        # 当查询请求 textScore 时，附上示例分数
        if projection and isinstance(projection, dict) and "score" in projection:
            for doc in docs:
                doc["score"] = 1.0
        return FakeCursor(docs)

    def _filter(self, query):
        if not query:
            yield from []
            return

        for book in self.documents.values():
            if self._matches(book, query):
                yield copy.deepcopy(book)

    def _matches(self, book, query):
        for key, value in query.items():
            if key == "$text":
                continue
            if key == "$and":
                return all(self._matches(book, cond) for cond in value)
            if key == "_id" and isinstance(value, dict) and "$in" in value:
                if book.get("_id") not in value["$in"]:
                    return False
                continue
            if key.startswith("search_index."):
                _, field = key.split(".", 1)
                field_value = book.get("search_index", {}).get(field)
                if isinstance(value, dict) and "$regex" in value:
                    pattern = value["$regex"].lstrip("^")
                    if not (isinstance(field_value, str) and field_value.startswith(pattern)):
                        return False
                elif isinstance(value, dict) and "$in" in value:
                    if isinstance(field_value, list):
                        if not any(item in value["$in"] for item in field_value):
                            return False
                    else:
                        if field_value not in value["$in"]:
                            return False
                continue
            if book.get(key) != value:
                return False
        return True


class FakeDB:
    def __init__(self, *, users, stores, orders, books):
        self.collections = {
            "Users": UsersCollection(users),
            "Stores": StoresCollection(stores),
            "Orders": OrdersCollection(orders),
            "Books": BooksCollection(books),
        }

    def __getitem__(self, name):
        return self.collections[name]


class MockCollection:
    def __init__(self):
        self.created_indexes = []

    def create_index(self, keys, **kwargs):
        self.created_indexes.append((tuple(keys), kwargs))


class MockDatabase:
    def __init__(self):
        self.collections = {}

    def list_collection_names(self):
        return list(self.collections.keys())

    def create_collection(self, name):
        self.collections[name] = MockCollection()

    def __getattr__(self, name):
        if name not in self.collections:
            self.collections[name] = MockCollection()
        return self.collections[name]

    __getitem__ = __getattr__


class MockMongoClient:
    def __init__(self, *args, **kwargs):
        self.databases = {}

    def __getitem__(self, name):
        if name not in self.databases:
            self.databases[name] = MockDatabase()
        return self.databases[name]

def create_fake_db():
    users = [
        {"_id": "seller_1", "password": "seller_pass", "balance": 0},
        {"_id": "buyer_1", "password": "buyer_pass", "balance": 10_000},
    ]
    stores = [
        {
            "_id": "store_1",
            "user_id": "seller_1",
            "inventory": [
                {"book_id": "book_existing", "stock_level": 5, "price": 100},
            ],
        }
    ]
    books = [
        {
            "_id": "book_existing",
            "title": "Existing Book",
            "tags": ["fiction"],
            "content": "Sample content",
            "search_index": {"title_lower": "existing", "tags_lower": ["fiction"]},
        },
        {
            "_id": "book_new",
            "title": "New Arrival",
            "tags": ["novel"],
            "content": "Preview",
            "search_index": {"title_lower": "new arrival", "tags_lower": ["novel"]},
        },
    ]
    orders = []
    return FakeDB(users=users, stores=stores, orders=orders, books=books)


@contextmanager
def patched_db(fake_db):
    from unittest.mock import patch

    with patch("be.model.db_conn.get_db", return_value=fake_db), \
            patch("be.model.store.get_db", return_value=fake_db):
        yield


def instantiate_seller_and_buyer(fake_db):
    with patched_db(fake_db):
        return Seller(), Buyer()


def test_add_book_success():
    fake_db = create_fake_db()
    seller, _ = instantiate_seller_and_buyer(fake_db)

    book_info = {
        "id": "book_new",
        "title": "New Arrival",
        "price": 199,
    }
    code, msg = seller.add_book(
        "seller_1",
        "store_1",
        "book_new",
        json.dumps(book_info),
        3,
    )

    assert (code, msg) == (200, "ok")
    inventory = fake_db["Stores"].documents["store_1"]["inventory"]
    assert any(item["book_id"] == "book_new" and item["stock_level"] == 3 for item in inventory)


def test_add_book_rejects_duplicate():
    fake_db = create_fake_db()
    seller, _ = instantiate_seller_and_buyer(fake_db)

    code, msg = seller.add_book(
        "seller_1",
        "store_1",
        "book_existing",
        json.dumps({"price": 100}),
        1,
    )

    assert (code, msg) == error.error_exist_book_id("book_existing")


def test_add_book_requires_existing_user_and_store():
    fake_db = create_fake_db()
    fake_db["Users"].documents.pop("seller_1")
    seller, _ = instantiate_seller_and_buyer(fake_db)

    code, msg = seller.add_book(
        "seller_1", "store_1", "book_new", json.dumps({}), 1
    )
    assert (code, msg) == error.error_non_exist_user_id("seller_1")

    fake_db = create_fake_db()
    fake_db["Stores"].documents.pop("store_1")
    seller, _ = instantiate_seller_and_buyer(fake_db)
    code, msg = seller.add_book(
        "seller_1", "store_1", "book_new", json.dumps({}), 1
    )
    assert (code, msg) == error.error_non_exist_store_id("store_1")


def test_add_stock_level_updates_inventory():
    fake_db = create_fake_db()
    seller, _ = instantiate_seller_and_buyer(fake_db)

    code, msg = seller.add_stock_level("seller_1", "store_1", "book_existing", 4)

    assert (code, msg) == (200, "ok")
    assert fake_db["Stores"].documents["store_1"]["inventory"][0]["stock_level"] == 9


def test_add_stock_level_validates_user_and_store():
    fake_db = create_fake_db()
    fake_db["Users"].documents.pop("seller_1")
    seller, _ = instantiate_seller_and_buyer(fake_db)
    assert seller.add_stock_level("seller_1", "store_1", "book_existing", 1) == error.error_non_exist_user_id("seller_1")

    fake_db = create_fake_db()
    fake_db["Stores"].documents.pop("store_1")
    seller, _ = instantiate_seller_and_buyer(fake_db)
    assert seller.add_stock_level("seller_1", "store_1", "book_existing", 1) == error.error_non_exist_store_id("store_1")


def test_add_stock_level_missing_book():
    fake_db = create_fake_db()
    seller, _ = instantiate_seller_and_buyer(fake_db)

    code, msg = seller.add_stock_level("seller_1", "store_1", "unknown", 2)

    assert (code, msg) == error.error_non_exist_book_id("unknown")


def test_add_operations_handle_invalid_numbers_and_db_errors():
    fake_db = create_fake_db()
    seller, _ = instantiate_seller_and_buyer(fake_db)

    code, msg = seller.add_book(
        "seller_1", "store_1", "book_numeric", json.dumps({"price": 10}), "invalid"
    )
    assert (code, msg) == (200, "ok")
    added = [item for item in fake_db["Stores"].documents["store_1"]["inventory"] if item["book_id"] == "book_numeric"]
    assert added and added[0]["stock_level"] == 0

    code, msg = seller.add_stock_level("seller_1", "store_1", "book_existing", "bad")
    assert (code, msg) == (200, "ok")
    assert fake_db["Stores"].documents["store_1"]["inventory"][0]["stock_level"] == 5

    seller, _ = instantiate_seller_and_buyer(fake_db)
    original_update = fake_db["Stores"].update_one

    def raise_error(*args, **kwargs):
        raise pymongo_errors.PyMongoError("boom")

    fake_db["Stores"].update_one = raise_error
    code, msg = seller.add_stock_level("seller_1", "store_1", "book_existing", 1)
    assert code == 528
    fake_db["Stores"].update_one = original_update


def test_create_store_requires_unique_id():
    fake_db = create_fake_db()
    seller, _ = instantiate_seller_and_buyer(fake_db)

    code, msg = seller.create_store("seller_1", "store_1")
    assert (code, msg) == error.error_exist_store_id("store_1")

    code, msg = seller.create_store("seller_1", "store_new")
    assert (code, msg) == (200, "ok")
    assert "store_new" in fake_db["Stores"].documents


def test_ship_order_success_and_inventory_deduction():
    fake_db = create_fake_db()
    seller, buyer = instantiate_seller_and_buyer(fake_db)

    # 创建订单并标记为已支付
    order = {
        "_id": "order_1",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "paid",
        "items": [{"book_id": "book_existing", "quantity": 2}],
    }
    fake_db["Orders"].insert_one(order)

    code, msg = seller.ship_order("seller_1", "order_1")
    assert (code, msg) == (200, "ok")

    updated_order = fake_db["Orders"].find_one({"_id": "order_1"})
    assert updated_order["status"] == "shipped"
    assert fake_db["Stores"].documents["store_1"]["inventory"][0]["stock_level"] == 3


def test_ship_order_rolls_back_on_insufficient_stock():
    fake_db = create_fake_db()
    seller, _ = instantiate_seller_and_buyer(fake_db)

    order = {
        "_id": "order_2",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "paid",
        "items": [{"book_id": "book_existing", "quantity": 6}],
    }
    fake_db["Orders"].insert_one(order)

    code, msg = seller.ship_order("seller_1", "order_2")

    assert (code, msg) == error.error_stock_level_low("book_existing")
    # 库存与订单状态保持不变
    assert fake_db["Stores"].documents["store_1"]["inventory"][0]["stock_level"] == 5
    assert fake_db["Orders"].find_one({"_id": "order_2"})["status"] == "paid"


def test_ship_order_error_paths():
    fake_db = create_fake_db()
    seller, _ = instantiate_seller_and_buyer(fake_db)

    assert seller.ship_order("seller_1", "missing") == error.error_invalid_order_id("missing")

    unpaid_order = {
        "_id": "order_unpaid",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "unpaid",
        "items": [],
    }
    fake_db["Orders"].insert_one(unpaid_order)
    assert seller.ship_order("seller_1", "order_unpaid") == error.error_order_status_mismatch("order_unpaid")

    owner_mismatch = {
        "_id": "order_mismatch",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "paid",
        "items": [],
    }
    fake_db["Orders"].insert_one(owner_mismatch)
    fake_db["Users"].documents["seller_2"] = {"_id": "seller_2", "password": "x", "balance": 0}
    assert seller.ship_order("seller_2", "order_mismatch") == error.error_authorization_fail()

    missing_book_order = {
        "_id": "order_missing_book",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "paid",
        "items": [{"book_id": "ghost", "quantity": 1}],
    }
    fake_db["Orders"].insert_one(missing_book_order)
    assert seller.ship_order("seller_1", "order_missing_book") == error.error_non_exist_book_id("ghost")


def test_ship_order_checks_authorization():
    fake_db = create_fake_db()
    seller, _ = instantiate_seller_and_buyer(fake_db)

    order = {
        "_id": "order_unauth",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "paid",
        "items": [],
    }
    fake_db["Orders"].insert_one(order)

    code, msg = seller.ship_order("seller_other", "order_unauth")
    assert (code, msg) == error.error_non_exist_user_id("seller_other")


def test_ship_order_handles_update_failures_and_exceptions():
    fake_db = create_fake_db()
    seller, _ = instantiate_seller_and_buyer(fake_db)

    fake_db["Stores"].documents["store_1"]["inventory"].append({
        "book_id": "book_second",
        "stock_level": 1,
        "price": 50,
    })
    fake_db["Books"].documents["book_second"] = {
        "_id": "book_second",
        "title": "Second",
        "tags": ["extra"],
        "content": "",
        "search_index": {"title_lower": "second", "tags_lower": ["extra"]},
    }

    order = {
        "_id": "order_multi",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "paid",
        "items": [
            {"book_id": "book_existing", "quantity": 1},
            {"book_id": "book_second", "quantity": 1},
        ],
    }
    fake_db["Orders"].insert_one(order)

    original_store_update = fake_db["Stores"].update_one
    call_count = {"value": 0}

    def update_with_failure(filter, update):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return original_store_update(filter, update)
        if call_count["value"] == 2:
            return FakeUpdateResult(0, 0)
        return original_store_update(filter, update)

    fake_db["Stores"].update_one = update_with_failure
    code, msg = seller.ship_order("seller_1", "order_multi")
    assert (code, msg) == error.error_stock_level_low("book_second")
    assert fake_db["Stores"].documents["store_1"]["inventory"][0]["stock_level"] == 5
    fake_db["Stores"].update_one = original_store_update

    order_fail = {
        "_id": "order_status_fail",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "paid",
        "items": [],
    }
    fake_db["Orders"].insert_one(order_fail)
    original_order_update = fake_db["Orders"].update_one
    fake_db["Orders"].update_one = lambda *args, **kwargs: FakeUpdateResult(1, 0)
    assert seller.ship_order("seller_1", "order_status_fail") == error.error_order_status_mismatch("order_status_fail")
    fake_db["Orders"].update_one = original_order_update

    order_exception = {
        "_id": "order_exception",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "paid",
        "items": [
            {"book_id": "book_existing", "quantity": 1},
            {"book_id": "book_second", "quantity": 1},
        ],
    }
    fake_db["Orders"].insert_one(order_exception)
    call_count["value"] = 0

    def update_then_raise(filter, update):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return original_store_update(filter, update)
        if call_count["value"] == 2:
            raise pymongo_errors.PyMongoError("boom")
        return original_store_update(filter, update)

    fake_db["Stores"].update_one = update_then_raise
    assert seller.ship_order("seller_1", "order_exception")[0] == 528
    fake_db["Stores"].update_one = original_store_update


def test_db_conn_helpers():
    fake_db = create_fake_db()
    with patched_db(fake_db):
        from be.model.db_conn import DBConn

        conn = DBConn()
        assert conn.user_id_exist("seller_1")
        assert not conn.user_id_exist("ghost")
        assert conn.store_id_exist("store_1")
        assert not conn.book_id_exist("missing")


def test_new_order_success_snapshot_and_total():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    code, msg, order_id = buyer.new_order(
        "buyer_1",
        "store_1",
        [("book_existing", 2)],
    )

    assert (code, msg) == (200, "ok")
    order_doc = fake_db["Orders"].find_one({"_id": order_id})
    assert order_doc["total_amount"] == 200
    assert order_doc["items"][0]["book_snapshot"]["title"] == "Existing Book"


def test_new_order_requires_existing_user_and_store():
    fake_db = create_fake_db()
    fake_db["Users"].documents.pop("buyer_1")
    _, buyer = instantiate_seller_and_buyer(fake_db)
    assert buyer.new_order("buyer_1", "store_1", [("book_existing", 1)]) == error.error_non_exist_user_id("buyer_1") + ("",)

    fake_db = create_fake_db()
    fake_db["Stores"].documents.pop("store_1")
    _, buyer = instantiate_seller_and_buyer(fake_db)
    assert buyer.new_order("buyer_1", "store_1", [("book_existing", 1)]) == error.error_non_exist_store_id("store_1") + ("",)


def test_new_order_validates_stock_and_book():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    result = buyer.new_order("buyer_1", "store_1", [("missing", 1)])
    assert result == error.error_non_exist_book_id("missing") + ("",)

    result = buyer.new_order("buyer_1", "store_1", [("book_existing", 10)])
    assert result == error.error_stock_level_low("book_existing") + ("",)


def test_new_order_handles_string_tags_and_db_error():
    fake_db = create_fake_db()
    fake_db["Books"].documents["book_existing"]["tags"] = "fiction, drama"
    _, buyer = instantiate_seller_and_buyer(fake_db)
    code, msg, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    assert (code, msg) == (200, "ok")
    assert order_id

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    original_insert = fake_db["Orders"].insert_one

    def raise_error(*args, **kwargs):
        raise pymongo_errors.PyMongoError("boom")

    fake_db["Orders"].insert_one = raise_error
    result = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    assert result[0] == 528
    fake_db["Orders"].insert_one = original_insert


def test_new_order_handles_unexpected_exception():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    original_find = fake_db["Stores"].find_one

    def raise_runtime(*args, **kwargs):
        raise RuntimeError("boom")

    fake_db["Stores"].find_one = raise_runtime
    result = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    assert result[0] == 530
    fake_db["Stores"].find_one = original_find


def test_payment_success_and_balance_change():
    fake_db = create_fake_db()
    seller, buyer = instantiate_seller_and_buyer(fake_db)

    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    code, msg = buyer.payment("buyer_1", "buyer_pass", order_id)
    assert (code, msg) == (200, "ok")

    updated_order = fake_db["Orders"].find_one({"_id": order_id})
    assert updated_order["status"] == "paid"
    assert fake_db["Users"].documents["buyer_1"]["balance"] == 9900


def test_payment_handles_insufficient_funds_and_status():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    fake_db["Users"].documents["buyer_1"]["balance"] = 50
    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    code, msg = buyer.payment("buyer_1", "buyer_pass", order_id)
    assert (code, msg) == error.error_not_sufficient_funds(order_id)

    # 再次支付，手动标记订单状态为已取消
    fake_db["Orders"].documents[order_id]["status"] = "cancelled"
    code, msg = buyer.payment("buyer_1", "buyer_pass", order_id)
    assert (code, msg) == error.error_order_cancelled(order_id)

    fake_db["Orders"].documents[order_id]["status"] = "paid"
    code, msg = buyer.payment("buyer_1", "buyer_pass", order_id)
    assert (code, msg) == error.error_order_completed(order_id)

    fake_db["Orders"].documents[order_id]["status"] = "shipped"
    code, msg = buyer.payment("buyer_1", "buyer_pass", order_id)
    assert (code, msg) == error.error_order_status_mismatch(order_id)


def test_payment_validates_inputs():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    assert buyer.payment("buyer_1", "buyer_pass", "missing") == error.error_invalid_order_id("missing")

    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])

    fake_db["Orders"].documents[order_id]["buyer_id"] = "someone_else"
    assert buyer.payment("buyer_1", "buyer_pass", order_id) == error.error_authorization_fail()

    fake_db["Orders"].documents[order_id]["buyer_id"] = "buyer_1"
    fake_db["Users"].documents["buyer_1"]["password"] = "new_pass"
    assert buyer.payment("buyer_1", "buyer_pass", order_id) == error.error_authorization_fail()

    fake_db["Users"].documents.pop("buyer_1")
    assert buyer.payment("buyer_1", "buyer_pass", order_id) == error.error_non_exist_user_id("buyer_1")


def test_payment_handles_database_errors():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    original_update = fake_db["Users"].update_one

    def raise_error(*args, **kwargs):
        raise pymongo_errors.PyMongoError("boom")

    fake_db["Users"].update_one = raise_error
    code, msg = buyer.payment("buyer_1", "buyer_pass", order_id)
    assert code == 528
    fake_db["Users"].update_one = original_update


def test_payment_covers_edge_cases():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    buyer.order_id_exist = lambda _order_id: True
    fake_db["Orders"].find_one = lambda query: None
    assert buyer.payment("buyer_1", "buyer_pass", "ghost") == error.error_invalid_order_id("ghost")

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    fake_db["Users"].update_one = lambda *args, **kwargs: FakeUpdateResult(0, 0)
    assert buyer.payment("buyer_1", "buyer_pass", order_id) == error.error_not_sufficient_funds(order_id)

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    original_user_update = fake_db["Users"].update_one
    def deduct_then_restore(filter, update):
        if update["$inc"]["balance"] < 0:
            return FakeUpdateResult(1, 1)
        return FakeUpdateResult(1, 1)
    fake_db["Users"].update_one = deduct_then_restore
    original_order_update = fake_db["Orders"].update_one
    fake_db["Orders"].update_one = lambda *args, **kwargs: FakeUpdateResult(0, 0)
    assert buyer.payment("buyer_1", "buyer_pass", order_id) == error.error_invalid_order_id(order_id)
    fake_db["Users"].update_one = original_user_update
    fake_db["Orders"].update_one = original_order_update

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    fake_db["Users"].update_one = lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom"))
    assert buyer.payment("buyer_1", "buyer_pass", order_id)[0] == 530


def test_add_funds_validation():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    code, msg = buyer.add_funds("buyer_1", "buyer_pass", "abc")
    assert (code, msg) == (400, "充值金额必须是数字")


    code, msg = buyer.add_funds("buyer_1", "buyer_pass", 100)
    assert (code, msg) == (200, "ok")
    assert fake_db["Users"].documents["buyer_1"]["balance"] == 10_100


def test_add_funds_requires_valid_user():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    fake_db["Users"].documents.pop("buyer_1")
    assert buyer.add_funds("buyer_1", "buyer_pass", 10) == error.error_non_exist_user_id("buyer_1")

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    assert buyer.add_funds("buyer_1", "wrong", 10) == error.error_authorization_fail()

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    original_update = fake_db["Users"].update_one
    fake_db["Users"].update_one = lambda *args, **kwargs: (_ for _ in ()).throw(pymongo_errors.PyMongoError("boom"))
    assert buyer.add_funds("buyer_1", "buyer_pass", 10)[0] == 528
    fake_db["Users"].update_one = lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom"))
    assert buyer.add_funds("buyer_1", "buyer_pass", 10)[0] == 530
    fake_db["Users"].update_one = original_update


def test_receive_order_transfers_funds():
    fake_db = create_fake_db()
    seller, buyer = instantiate_seller_and_buyer(fake_db)

    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    buyer.payment("buyer_1", "buyer_pass", order_id)
    fake_db["Orders"].documents[order_id]["status"] = "shipped"

    code, msg = buyer.receive_order("buyer_1", order_id)
    assert (code, msg) == (200, "ok")
    assert fake_db["Orders"].find_one({"_id": order_id})["status"] == "delivered"
    assert fake_db["Users"].documents["seller_1"]["balance"] == 100


def test_receive_order_validations():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    assert buyer.receive_order("ghost", "order") == error.error_non_exist_user_id("ghost")

    assert buyer.receive_order("buyer_1", "missing") == error.error_invalid_order_id("missing")

    fake_db["Orders"].insert_one({
        "_id": "order_wrong_user",
        "buyer_id": "other",
        "store_id": "store_1",
        "status": "shipped",
        "total_amount": 50,
        "items": [],
    })
    assert buyer.receive_order("buyer_1", "order_wrong_user") == error.error_authorization_fail()

    fake_db["Orders"].insert_one({
        "_id": "order_wrong_status",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "paid",
        "total_amount": 50,
        "items": [],
    })
    assert buyer.receive_order("buyer_1", "order_wrong_status") == error.error_order_status_mismatch("order_wrong_status")

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    fake_db["Orders"].insert_one({
        "_id": "order_db_error",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "shipped",
        "total_amount": 20,
        "items": [],
    })
    fake_db["Orders"].update_one = lambda *args, **kwargs: (_ for _ in ()).throw(pymongo_errors.PyMongoError("boom"))
    assert buyer.receive_order("buyer_1", "order_db_error")[0] == 528

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    fake_db["Orders"].insert_one({
        "_id": "order_base_error",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "shipped",
        "total_amount": 20,
        "items": [],
    })
    fake_db["Orders"].update_one = lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom"))
    assert buyer.receive_order("buyer_1", "order_base_error")[0] == 530

    fake_db["Orders"].insert_one({
        "_id": "order_missing_store",
        "buyer_id": "buyer_1",
        "store_id": "ghost_store",
        "status": "shipped",
        "total_amount": 10,
        "items": [],
    })
    assert buyer.receive_order("buyer_1", "order_missing_store") == error.error_non_exist_store_id("ghost_store")

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    fake_db["Orders"].insert_one({
        "_id": "order_update_fail",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "shipped",
        "total_amount": 20,
        "items": [],
    })
    original_update = fake_db["Orders"].update_one

    def no_change(*args, **kwargs):
        return FakeUpdateResult(1, 0)

    fake_db["Orders"].update_one = no_change
    assert buyer.receive_order("buyer_1", "order_update_fail") == error.error_order_status_mismatch("order_update_fail")
    fake_db["Orders"].update_one = original_update


def test_get_and_query_orders_with_pagination():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    order_ids = []
    for _ in range(12):
        _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
        order_ids.append(order_id)

    first_order = order_ids[0]
    code, msg, doc = buyer.get_order("buyer_1", first_order)
    assert (code, msg) == (200, "ok")
    assert doc["_id"] == first_order

    fake_db_error = create_fake_db()
    _, buyer_error = instantiate_seller_and_buyer(fake_db_error)
    fake_db_error["Orders"].find_one = lambda *args, **kwargs: (_ for _ in ()).throw(pymongo_errors.PyMongoError("boom"))
    assert buyer_error.get_order("buyer_1", "order")[0] == 528

    code, msg, result = buyer.query_orders("buyer_1", page=2)
    assert (code, msg) == (200, "ok")
    assert result["pagination"]["page"] == 2
    assert len(result["orders"]) == 2  # 12 条数据，page_size=10


def test_query_orders_validations():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    assert buyer.query_orders(None)[0:2] == error.error_and_message(400, "参数不能为空")
    fake_db["Users"].documents.pop("buyer_1")
    assert buyer.query_orders("buyer_1")[0:2] == error.error_non_exist_user_id("buyer_1")

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    assert buyer.query_orders("buyer_1", page="abc")[0:2] == error.error_and_message(400, "页码参数无效")

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    fake_db["Orders"].find = lambda *args, **kwargs: (_ for _ in ()).throw(pymongo_errors.PyMongoError("boom"))
    assert buyer.query_orders("buyer_1")[0] == 528


def test_cancel_order_refunds_paid_order():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    buyer.payment("buyer_1", "buyer_pass", order_id)

    code, msg = buyer.cancel_order("buyer_1", order_id)
    assert (code, msg) == (200, "ok")
    order_doc = fake_db["Orders"].find_one({"_id": order_id})
    assert order_doc["status"] == "cancelled"
    assert fake_db["Users"].documents["buyer_1"]["balance"] == 10_000


def test_cancel_order_validations():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    assert buyer.cancel_order("ghost", "order")[0:2] == error.error_non_exist_user_id("ghost")
    assert buyer.cancel_order("buyer_1", "order")[0:2] == error.error_invalid_order_id("order")

    fake_db["Orders"].insert_one({
        "_id": "order_other",
        "buyer_id": "other",
        "store_id": "store_1",
        "status": "paid",
        "total_amount": 10,
        "items": [],
    })
    assert buyer.cancel_order("buyer_1", "order_other")[0:2] == error.error_authorization_fail()

    fake_db["Orders"].insert_one({
        "_id": "order_completed",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "delivered",
        "total_amount": 10,
        "items": [],
    })
    assert buyer.cancel_order("buyer_1", "order_completed") == (400, "订单状态不允许取消")

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    fake_db["Orders"].documents[order_id]["status"] = "unpaid"
    fake_db["Orders"].find_one_and_update = lambda *args, **kwargs: None
    assert buyer.cancel_order("buyer_1", order_id) == (400, "订单状态已变更，取消失败")

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    buyer.payment("buyer_1", "buyer_pass", order_id)
    original_update = fake_db["Users"].update_one

    def no_refund(*args, **kwargs):
        return FakeUpdateResult(1, 0)

    fake_db["Users"].update_one = no_refund
    code, msg = buyer.cancel_order("buyer_1", order_id)
    assert (code, msg) == error.error_non_exist_user_id("buyer_1")
    fake_db["Users"].update_one = original_update

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    fake_db["Orders"].find_one = lambda *args, **kwargs: (_ for _ in ()).throw(pymongo_errors.PyMongoError("boom"))
    assert buyer.cancel_order("buyer_1", order_id)[0] == 528

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    _, _, order_id = buyer.new_order("buyer_1", "store_1", [("book_existing", 1)])
    fake_db["Orders"].find_one_and_update = lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom"))
    assert buyer.cancel_order("buyer_1", order_id)[0] == 530


def test_auto_cancel_timeout_orders():
    fake_db = create_fake_db()
    seller, buyer = instantiate_seller_and_buyer(fake_db)

    old_time = time.time() - 25 * 3600
    fake_db["Orders"].insert_one({
        "_id": "stale_order",
        "buyer_id": "buyer_1",
        "store_id": "store_1",
        "status": "unpaid",
        "create_time": old_time,
        "items": [],
    })

    with patched_db(fake_db):
        code, msg, count = Buyer.auto_cancel_timeout_orders()
    assert (code, msg, count) == (200, "ok", 1)
    assert fake_db["Orders"].find_one({"_id": "stale_order"})["status"] == "cancelled"

    from unittest.mock import patch

    with patch("be.model.store.get_db", side_effect=pymongo_errors.PyMongoError("boom")):
        assert Buyer.auto_cancel_timeout_orders()[0] == 528

    with patch("be.model.store.get_db", return_value=fake_db):
        fake_db["Orders"].find = lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom"))
        assert Buyer.auto_cancel_timeout_orders()[0] == 530


def test_store_mongodb_initialization():
    from unittest.mock import patch

    mock_client = MockMongoClient()
    with patch("pymongo.MongoClient", return_value=mock_client):
        store_db = store_module.StoreMongoDB(mongo_uri="mongodb://fake", db_name="testdb")

    test_db = mock_client.databases["testdb"]
    assert test_db.Users.created_indexes
    assert test_db.Stores.created_indexes
    assert test_db.Orders.created_indexes
    assert test_db.Books.created_indexes
    assert store_db.get_db() is test_db
    assert store_db.get_db_conn() is mock_client


def test_store_global_helpers():
    from unittest.mock import patch

    store_module.database_instance = None
    store_module.init_completed_event.clear()

    first_client = MockMongoClient()
    with patch("pymongo.MongoClient", return_value=first_client):
        store_module.init_database("mongodb://fake", "globaldb")

    assert isinstance(store_module.database_instance, store_module.StoreMongoDB)
    assert store_module.init_completed_event.is_set()
    assert store_module.get_db() is store_module.database_instance.get_db()
    assert store_module.get_db_conn() is store_module.database_instance.get_db_conn()

    store_module.database_instance = None
    store_module.init_completed_event.clear()
    second_client = MockMongoClient()
    with patch("pymongo.MongoClient", return_value=second_client):
        db = store_module.get_db()
        conn = store_module.get_db_conn()

    assert isinstance(store_module.database_instance, store_module.StoreMongoDB)
    assert db is store_module.database_instance.get_db()
    assert conn is store_module.database_instance.get_db_conn()

    store_module.database_instance = None
    store_module.init_completed_event.clear()


def test_store_handles_connection_and_init_errors():
    from unittest.mock import patch

    with patch("pymongo.MongoClient", side_effect=pymongo_errors.PyMongoError("boom")):
        with pytest.raises(pymongo_errors.PyMongoError):
            store_module.StoreMongoDB()

    class ErrorDatabase(MockDatabase):
        def list_collection_names(self):
            raise pymongo_errors.PyMongoError("fail")

    class ErrorClient(MockMongoClient):
        def __getitem__(self, name):
            return ErrorDatabase()

    with patch("pymongo.MongoClient", return_value=ErrorClient()):
        store = store_module.StoreMongoDB(mongo_uri="mongodb://fake", db_name="errordb")
        assert isinstance(store.get_db(), MockDatabase)


def test_search_books_in_store_scope():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    code, msg, result = buyer.search_books("Existing", store_id="store_1")
    assert (code, msg) == (200, "ok")
    assert result["pagination"]["total_count"] == 1
    assert result["books"][0]["id"] == "book_existing"

    code, msg, result = buyer.search_books("Existing")
    assert (code, msg) == (200, "ok")
    assert result["pagination"]["total_count"] == 2


def test_search_books_validations():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    assert buyer.search_books("   ")[0:2] == error.error_and_message(400, "搜索关键字不能为空")
    assert buyer.search_books("keyword", store_id="ghost")[0:2] == error.error_non_exist_store_id("ghost")

    fake_db["Stores"].documents["store_1"]["inventory"] = []
    code, msg, result = buyer.search_books("keyword", store_id="store_1")
    assert (code, msg) == (200, "ok")
    assert result["pagination"]["total_count"] == 0

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    fake_db["Books"].find = lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom"))
    assert buyer.search_books("keyword")[0] == 530


def test_search_books_advanced_with_store_filter():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    code, msg, result = buyer.search_books_advanced(
        title_prefix="new",
        tags=["novel"],
        store_id="store_1",
    )
    # 店铺中没有该书，应该返回空列表
    assert (code, msg) == (200, "ok")
    assert result["pagination"]["total_count"] == 0


def test_get_book_detail_success():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    code, msg, detail = buyer.get_book_detail("book_existing")
    assert (code, msg) == (200, "ok")
    assert detail["title"] == "Existing Book"


def test_search_books_advanced_validations():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    assert buyer.search_books_advanced()[0:2] == error.error_and_message(400, "搜索条件不能为空")

    assert buyer.search_books_advanced(title_prefix="new", store_id="ghost")[0:2] == error.error_non_exist_store_id("ghost")

    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)
    fake_db["Books"].find = lambda *args, **kwargs: (_ for _ in ()).throw(pymongo_errors.PyMongoError("boom"))
    assert buyer.search_books_advanced(title_prefix="new")[0] == 528


def test_get_book_detail_errors():
    fake_db = create_fake_db()
    _, buyer = instantiate_seller_and_buyer(fake_db)

    assert buyer.get_book_detail("   ")[0:2] == error.error_and_message(400, "书籍ID不能为空")
    assert buyer.get_book_detail("missing")[0:2] == error.error_and_message(404, "书籍不存在")

    fake_db["Books"].find_one = lambda *args, **kwargs: (_ for _ in ()).throw(pymongo_errors.PyMongoError("boom"))
    assert buyer.get_book_detail("book_existing")[0] == 528

