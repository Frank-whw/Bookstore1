import jwt
import time
import logging
import pymongo
from be.model import error
from be.model import db_conn
from fe.access import book

# encode a json string like:
#   {
#       "user_id": [user name],
#       "terminal": [terminal code],
#       "timestamp": [ts]
#   }to a JWT
def jwt_encode(user_id: str, terminal: str) -> str:
    encoded = jwt.encode(
        {"user_id": user_id, "terminal": terminal, "timestamp": time.time()},
        key=user_id,
        algorithm="HS256",
    )
    # PyJWT v1 returns bytes; PyJWT v2+ returns str
    if isinstance(encoded, bytes):
        return encoded.decode("utf-8")
    return encoded


# decode a JWT to a json string like:
#   {
#       "user_id": [user name],
#       "terminal": [terminal code],
#       "timestamp": [ts]
#   }
def jwt_decode(encoded_token, user_id: str) -> str:
    decoded = jwt.decode(encoded_token, key=user_id, algorithms=["HS256"])
    return decoded

class User(db_conn.DBConn):
    token_lifetime: int = 3600 # 3600 second
    def __init__(self):
        super().__init__()
    def __check_token__(self, user_id: str, db_token: str, token: str) -> bool:
        try:
            if db_token != token:
                return False
            jwt_text = jwt_decode(encoded_token=token, user_id=user_id)
            ts = jwt_text["timestamp"]
            if ts is not None:
                now = time.time()
                if self.token_lifetime > now - ts >= 0:
                    return True
        except jwt.exceptions.InvalidSignatureError as e:
            logging.error(str(e))
            return False
    
    def register(self, user_id: str, password: str) -> (int, str):
        try:
            terminal = "terminal_{}".format(str(time.time()))
            token = jwt_encode(user_id, terminal)
            user = {
                "_id": user_id,
                "password": password,
                "balance": 0,
                "token": token,
                "terminal": terminal
            }
            self.conn[bookstore][Users].insert_one(user)
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        return 200, "ok"
    
    def check_token(self, user_id: str, token: str) -> (int, str):
        user_doc = self.conn[bookstore][Users].find_one({"_id": user_id})
        if user_doc is None:
            return error.error_non_exist_user_id(user_id)
        db_token = user_doc.get("token")
        if not self.__check_token__(user_id, db_token, token):
            return error.error_authorization_fail()
        return 200, "ok"
    
    def check_password(self, user_id: str, password: str) -> (int, str):
        user_doc = self.conn[bookstore][Users].find_one({"_id": user_id})
        if user_doc is None:
            return error.error_non_exist_user_id(user_id)
        db_password = user_doc.get("password")
        if db_password != password:
            return error.error_authorization_fail()
        return 200, "ok"

    def login(self, user_id: str, password: str, terminal: str) -> (int, str, str):
        token = ""
        try:
            code, message = self.check_password(user_id, password)
            if code != 200:
                return code, message, ""

            token = jwt_encode(user_id, terminal)
            self.conn[bookstore][Users].update_one({
                "_id": user_id
            },{
                "$set":{"token": token}
            })
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e)), ""
        except BaseException as e:
            return 530, "{}".format(str(e)), ""
        return 200, "ok", token

    def logout(self, user_id: str, token: str) -> bool:
        try:
            code, message = self.check_token(user_id, token)
            if code != 200:
                return code, message

            terminal = "terminal_{}".format(str(time.time()))
            dummy_token = jwt_encode(user_id, terminal)

            self.conn[bookstore][Users].update_one({
                "_id": user_id
            },{
                "$set":{
                    "token": dummy_token,
                    "terminal": terminal
                }
            })
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        except BaseException as e:
            return 530, "{}".format(str(e))
        return 200, "ok"

    def unregister(self, user_id: str, password: str) -> (int, str):
        try:
            code, message = self.check_password(user_id, password)
            if code != 200:
                return code, message

            self.conn[bookstore][Users].delete_one({
                "_id": user_id
            })
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        except BaseException as e:
            return 530, "{}".format(str(e))
        return 200, "ok"

    def change_password(
        self, user_id: str, old_password: str, new_password: str
    ) -> bool:
        try:
            code, message = self.check_password(user_id, old_password)
            if code != 200:
                return code, message

            terminal = "terminal_{}".format(str(time.time()))
            token = jwt_encode(user_id, terminal)
            self.conn[bookstore][Users].update_one({
                "_id": user_id
            },{
                "$set":{
                    "password": new_password,
                    "token": token,
                    "terminal": terminal
                }
            })
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        except BaseException as e:
            return 530, "{}".format(str(e))
        return 200, "ok"