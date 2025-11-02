import pymongo

from be.model import db_conn

class Seller(db_conn.DBConn):
    def __init__(self):
        super().__init__()

    # 需要确定一下 book_json_str 的结构
    def add_book(
        self, user_id: str, store_id: str, book_id: str, book_json_str: str, stock_level: int):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)
            if self.book_id_exist(store_id, book_id):
                return error.error_exist_book_id(book_id)
            info = json.loads(book_json_str)
            '''
            {
            "id": "1000134",
            "title": "书名",
            "author": "作者",
            "publisher": "出版社",
            "original_title": "原作名",
            "translator": "译者",
            "pub_year": "2020",
            "pages": 320,
            "price": 3999,
            "currency_unit": "CNY",
            "binding": "精装",
            "isbn": "978-7-XXXX-XXXXX",
            "author_intro": "作者简介文本",
            "book_intro": "书籍简介文本",
            "content": "样章试读文本",
            "tags": ["文学", "小说"],
            "pictures": ["<base64-1>", "<base64-2>"]
            }
            '''
            book = {
                "book_id": book_id,
                "stock_level": stock_level,
                "price": info.get("price"),
                "book_info": {
                    "title": info.get("title"),
                    "tag": info.get("tags"),
                    "content": info.get("content")
                }
            }
            self.conn["bookstore"]["Stores"].update_one({
                "_id": store_id
            },{
                "$push":{
                    "inventory": {book}
                }
            })
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        except BaseException as e:
            return 530, "{}".format(str(e))
        return 200, "ok"
    
    def add_stock_level(
        self, user_id: str, store_id: str, book_id: str, add_stock_level: int
    ):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)
            if not self.book_id_exist(store_id, book_id):
                return error.error_non_exist_book_id(book_id)

            self.conn["bookstore"]["Stores"].update_one({
                "_id": store_id,
                "inventory.book_id": book_id
            },{
                "$inc":{"inventory.stock_level": add_stock_level}
            })
            
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        except BaseException as e:
            return 530, "{}".format(str(e))
        return 200, "ok"

    def create_store(self, user_id: str, store_id: str) -> (int, str):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if self.store_id_exist(store_id):
                return error.error_exist_store_id(store_id)
            store = {
                "_id": store_id,
                "user_id": user_id,
                "inventory":[]
            }
            self.conn["bookstore"]["Stores"].insert_one(store)
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        except BaseException as e:
            return 530, "{}".format(str(e))
        return 200, "ok"