import requests
import simplejson
from urllib.parse import urljoin
from fe.access.auth import Auth


class Buyer:
    def __init__(self, url_prefix, user_id, password):
        self.url_prefix = urljoin(url_prefix, "buyer/")
        self.user_id = user_id
        self.password = password
        self.token = ""
        self.terminal = "my terminal"
        self.auth = Auth(url_prefix)
        code, self.token = self.auth.login(self.user_id, self.password, self.terminal)
        assert code == 200

    def new_order(self, store_id: str, book_id_and_count: [(str, int)]) -> (int, str):
        books = []
        for id_count_pair in book_id_and_count:
            books.append({"id": id_count_pair[0], "count": id_count_pair[1]})
        json = {"user_id": self.user_id, "store_id": store_id, "books": books}
        # print(simplejson.dumps(json))
        url = urljoin(self.url_prefix, "new_order")
        headers = {"token": self.token}
        r = requests.post(url, headers=headers, json=json)
        response_json = r.json()
        return r.status_code, response_json.get("order_id")

    def payment(self, order_id: str):
        json = {
            "user_id": self.user_id,
            "password": self.password,
            "order_id": order_id,
        }
        url = urljoin(self.url_prefix, "payment")
        headers = {"token": self.token}
        r = requests.post(url, headers=headers, json=json)
        return r.status_code

    def add_funds(self, add_value: str) -> int:
        json = {
            "user_id": self.user_id,
            "password": self.password,
            "add_value": add_value,
        }
        url = urljoin(self.url_prefix, "add_funds")
        headers = {"token": self.token}
        r = requests.post(url, headers=headers, json=json)
        return r.status_code

    def receive_order(self, order_id: str) -> int:
        json = {
            "user_id": self.user_id,
            "order_id": order_id,
        }
        url = urljoin(self.url_prefix, "receive")
        headers = {"token": self.token}
        r = requests.post(url, headers=headers, json=json)
        return r.status_code


    def query_orders(self, status: str = None, page: int = 1) -> (int, dict):
        json = {
            "user_id": self.user_id,
            "status": status,
            "page": page,
        }
        url = urljoin(self.url_prefix, "orders")
        headers = {"token": self.token}
        r = requests.post(url, headers=headers, json=json)
        response_json = r.json()
        return r.status_code, response_json.get("result", {})

    def cancel_order(self, order_id: str) -> int:
        json = {
            "user_id": self.user_id,
            "order_id": order_id,
        }
        url = urljoin(self.url_prefix, "cancel_order")
        headers = {"token": self.token}
        r = requests.post(url, headers=headers, json=json)
        return r.status_code

    @staticmethod
    def auto_cancel_timeout_orders(url_prefix: str) -> (int, int):
        json = {}
        url = urljoin(urljoin(url_prefix, "buyer/"), "auto_cancel_timeout")
        r = requests.post(url, json=json)
        response_json = r.json()
        return r.status_code, response_json.get("cancelled_count", 0)

    def search_books(self, keyword: str, store_id: str = None, page: int = 1) -> (int, dict):
        json = {
            "keyword": keyword,
            "store_id": store_id,
            "page": page,
        }
        url = urljoin(self.url_prefix, "search_books")
        headers = {"token": self.token}
        r = requests.post(url, headers=headers, json=json)
        response_json = r.json()
        return r.status_code, response_json.get("result", {})

    def search_books_advanced(self, title_prefix: str = None, tags: list = None, store_id: str = None, page: int = 1) -> (int, dict):
        json = {
            "title_prefix": title_prefix,
            "tags": tags,
            "store_id": store_id,
            "page": page,
        }
        url = urljoin(self.url_prefix, "search_books_advanced")
        headers = {"token": self.token}
        r = requests.post(url, headers=headers, json=json)
        response_json = r.json()
        return r.status_code, response_json.get("result", {})

    def get_book_detail(self, book_id: str) -> (int, dict):
        json = {
            "book_id": book_id,
        }
        url = urljoin(self.url_prefix, "book_detail")
        headers = {"token": self.token}
        r = requests.post(url, headers=headers, json=json)
        response_json = r.json()
        return r.status_code, response_json.get("result", {})