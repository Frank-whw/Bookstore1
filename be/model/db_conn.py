from be.model.store import get_db


class DBConn:
    def __init__(self):
        self.db = get_db()
    # 检查user_id是否存在
    def user_id_exist(self, user_id):
        cursor = self.db["Users"].find_one({"_id": user_id})
        if cursor is None:
            return False
        else:
            return True
    # 检查store_id是否存在
    def store_id_exist(self, store_id):
        cursor = self.db["Stores"].find_one({"_id": store_id})
        if cursor is None:
            return False
        else:
            return True

    # 检查book_id是否存在
    def book_id_exist(self, book_id):
        cursor = self.db["Books"].find_one({"_id": book_id})
        if cursor is None:
            return False
        else:
            return True
    # 检查order_id是否存在
    def order_id_exist(self, order_id):
        cursor = self.db["Orders"].find_one({"_id": order_id})
        if cursor is None:
            return False
        else:
            return True