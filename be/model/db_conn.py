from pyclbr import Class
import pymongo

from fe.access import book

class DBConn:
    def __init__(self):
        self.conn = pymongo.MongoClient("mongodb://localhost:27017/")
    # 检查user_id是否存在
    def user_id_exist(self, user_id):
        cursor = self.conn["bookstore"]["Users"].find_one({"_id": user_id})
        if cursor is None:
            return False
        else:
            return True
    # 检查store_id是否存在
    def store_id_exist(self, store_id):
        cursor = self.conn["bookstore"]["Stores"].find_one({"_id": store_id})
        if cursor is None:
            return False
        else:
            return True

    # 检查book_id是否存在
    def book_id_exist(self, book_id):
        cursor = self.conn["bookstore"]["Books"].find_one({"_id": book_id})
        if cursor is None:
            return False
        else:
            return True
    # 检查order_id是否存在
    def order_id_exist(self, order_id):
        cursor = self.conn["bookstore"]["Orders"].find_one({"_id": order_id})
        if cursor is None:
            return False
        else:
            return True