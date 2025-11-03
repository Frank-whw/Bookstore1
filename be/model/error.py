import json
import logging

error_code = {
    200: "ok",
    401: "authorization fail.",
    511: "non exist user id {}",
    512: "exist user id {}",
    513: "non exist store id {}",
    514: "exist store id {}",
    515: "non exist book id {}",
    516: "exist book id {}",
    517: "stock level low, book id {}",
    518: "invalid order id {}",
    519: "not sufficient funds, order id {}",
    520: "bad request",
    521: "conflict",
    522: "unprocessable",
    523: "timeout",
    524: "rate limit",
    525: "not implemented",
    526: "dependency failure",
    527: "unknown error",
    528: "database error: {}",
    529: "external service error: {}",
    530: "internal server error: {}",
}

# 简单错误级别（可用于统一日志/消息前缀）
error_level_default = {
    200: "info",
    401: "error",
    511: "error",
    512: "error",
    513: "error",
    514: "error",
    515: "error",
    516: "error",
    517: "warning",
    518: "error",
    519: "error",
    528: "error",
    529: "error",
    530: "critical",
}


def _format(code: int, text: str, context: dict | None = None):
    level = error_level_default.get(code, "error")
    ctx = f" | ctx={json.dumps(context, ensure_ascii=False)}" if context else ""
    message = f"[{level}] {text}{ctx}"
    try:
        logging.log(
            logging.ERROR if level in ("error", "critical") else logging.INFO,
            f"code={code} level={level} msg={message}"
        )
    except Exception:
        pass
    return code, message


def error_non_exist_user_id(user_id):
    return _format(511, error_code[511].format(user_id))


def error_exist_user_id(user_id):
    return _format(512, error_code[512].format(user_id))


def error_non_exist_store_id(store_id):
    return _format(513, error_code[513].format(store_id))


def error_exist_store_id(store_id):
    return _format(514, error_code[514].format(store_id))


def error_non_exist_book_id(book_id):
    return _format(515, error_code[515].format(book_id))


def error_exist_book_id(book_id):
    return _format(516, error_code[516].format(book_id))


def error_stock_level_low(book_id):
    return _format(517, error_code[517].format(book_id))


def error_invalid_order_id(order_id):
    return _format(518, error_code[518].format(order_id))


def error_not_sufficient_funds(order_id):
    return _format(519, error_code[519].format(order_id))


def error_invalid_order_status(order_id, status):
    # 为不合法的订单状态操作提供更明确的错误信息
    return _format(518, f"invalid order status {order_id}, status={status}", {"order_id": order_id, "status": status})


def error_authorization_fail(context: dict | None = None):
    return _format(401, error_code[401], context)


def error_db_exception(exc: Exception, context: dict | None = None):
    return _format(528, error_code[528].format(str(exc)), context)


def error_internal_exception(exc: Exception, context: dict | None = None):
    return _format(530, error_code[530].format(str(exc)), context)


def error_and_message(code, message):
    return _format(code, message)
