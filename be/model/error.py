import logging

error_code = {
    # 授权相关（保持 4xx 与现有风格一致）
    401: "authorization fail.",

    # 用户 / 店铺 / 图书 基础错误（5xx）
    511: "non exist user id {}",
    512: "exist user id {}",
    513: "non exist store id {}",
    514: "exist store id {}",
    515: "non exist book id {}",
    516: "exist book id {}",
    517: "stock level low, book id {}",

    # 订单相关（状态、有效性）
    518: "invalid order id {}",
    520: "order cancelled, order id {}",
    521: "order completed, order id {}",
    522: "order status mismatch, order id {}",

    # 支付相关
    519: "not sufficient funds, order id {}",
    524: "payment timeout, order id {}",
    525: "payment closed, order id {}",

    # 权限/会话相关
    526: "no operation permission, user id {}",
    527: "not logged in",

    # 系统/数据库错误与兜底
    528: "database error {}",
    530: "internal error {}",
}


"""
模块化业务错误：
- User/Store/Book: 511~517
- Order: 518, 520~522
- Payment: 519, 524~525
- Permission/Session: 526~527
- System/DB: 528, 530

为保持与现有代码风格一致，以下函数均返回 (code, message)。
异常处理统一使用辅助函数在 try/except 中记录日志并返回标准三元组。
"""


# 用户/店铺/图书相关
def error_non_exist_user_id(user_id):
    return 511, error_code[511].format(user_id)


def error_exist_user_id(user_id):
    return 512, error_code[512].format(user_id)


def error_non_exist_store_id(store_id):
    return 513, error_code[513].format(store_id)


def error_exist_store_id(store_id):
    return 514, error_code[514].format(store_id)


def error_non_exist_book_id(book_id):
    return 515, error_code[515].format(book_id)


def error_exist_book_id(book_id):
    return 516, error_code[516].format(book_id)


def error_stock_level_low(book_id):
    return 517, error_code[517].format(book_id)


def error_invalid_order_id(order_id):
    return 518, error_code[518].format(order_id)


# 订单状态相关
def error_order_cancelled(order_id):
    return 520, error_code[520].format(order_id)


def error_order_completed(order_id):
    return 521, error_code[521].format(order_id)


def error_order_status_mismatch(order_id):
    return 522, error_code[522].format(order_id)


def error_not_sufficient_funds(order_id):
    return 519, error_code[519].format(order_id)


def error_payment_timeout(order_id):
    return 524, error_code[524].format(order_id)


def error_payment_closed(order_id):
    return 525, error_code[525].format(order_id)


def error_authorization_fail():
    return 401, error_code[401]


def error_no_operation_permission(user_id):
    return 526, error_code[526].format(user_id)


def error_not_logged_in():
    return 527, error_code[527]


def error_and_message(code, message):
    return code, message


# 系统/数据库错误与异常处理辅助
def error_database_error(message: str):
    """数据库错误统一消息（code: 528）。返回 (code, message)。"""
    return 528, error_code[528].format(message)


def exception_to_tuple3(e: BaseException, code: int = 530):
    """
    标准化异常处理：
    - 统一 except BaseException as e 捕获
    - 记录详细错误日志（traceback）
    - 返回 (状态码, 错误信息字符串, 空字符串)
    """
    logging.exception("Unhandled exception: %s", e)
    return code, error_code.get(code, "internal error {}").format(str(e)), ""


def exception_db_to_tuple3(e: BaseException):
    """数据库异常专用助手：记录日志并返回 528 统一格式三元组。"""
    logging.exception("Database exception: %s", e)
    return 528, error_code[528].format(str(e)), ""
