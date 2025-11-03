# API 错误码说明

本项目后端错误码采用分模块的 5xx 系列规范（授权相关保留 401），并提供标准化异常处理返回格式与日志记录要求。

## 返回格式

- 成功返回：
  - 根据接口约定，可能返回 `(code, message)` 或 `(code, message, extra)`；`extra` 为附加数据（如 `order_id`）。
- 失败/异常返回（统一要求）：
  - 采用 `except BaseException as e` 捕获，并记录完整日志（`logging.exception`）。
  - 返回格式统一为三元组：`(状态码, 错误信息字符串, 空字符串)`。

说明：视图层会从返回值中提取 `message` 并透传到响应体；三元组的第三项在错误场景固定为空字符串以保持一致性。

## 错误码列表

### 授权相关（4xx）
- `401` authorization fail.

### 用户 / 店铺 / 图书（5xx）
- `511` non exist user id {user_id}
- `512` exist user id {user_id}
- `513` non exist store id {store_id}
- `514` exist store id {store_id}
- `515` non exist book id {book_id}
- `516` exist book id {book_id}
- `517` stock level low, book id {book_id}

### 订单相关（5xx）
- `518` invalid order id {order_id}
- `520` order cancelled, order id {order_id}
- `521` order completed, order id {order_id}
- `522` order status mismatch, order id {order_id}

### 支付相关（5xx）
- `519` not sufficient funds, order id {order_id}
- `524` payment timeout, order id {order_id}
- `525` payment closed, order id {order_id}

### 权限 / 会话相关（5xx）
- `526` no operation permission, user id {user_id}
- `527` not logged in

### 系统 / 数据库（5xx）
- `528` database error {detail}
- `530` internal error {detail}

## 使用建议

- 模型层（be/model/*）在业务校验失败时返回上述 `error_*` 方法的二元组；当接口约定需要三元组（例如返回 `order_id` 等），请在失败时追加空字符串形成三元组：`error.error_xxx(args) + ("",)`。
- 在异常捕获中统一使用：
  - `except BaseException as e:`
  - 使用 `logging.exception("..", e)` 记录完整堆栈
  - 返回三元组：`error.exception_to_tuple3(e)` 或 `error.exception_db_to_tuple3(e)`（数据库异常）

## 变更记录

- 新增订单状态校验相关错误：`520`（已取消）、`521`（已完成）、`522`（状态不匹配）
- 新增支付相关错误：`524`（支付超时）、`525`（支付关闭）
- 新增用户权限校验错误：`526`（无操作权限）、`527`（未登录）
- 标准化异常返回：增加 `exception_to_tuple3` 与 `exception_db_to_tuple3`，统一日志记录与返回格式。