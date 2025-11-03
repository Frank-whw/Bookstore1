## Todo
- [x] 设计[Schema](##Schema) 10.21
- [x] 迁移数据库
  - [x] 创建MongoDB连接配置
  - [x] 编写数据迁移脚本
  - [x] 从SQLite导入book.db数据到MongoDB
- [x] 修改[buyer.py](be/model/buyer.py) - 买家相关业务逻辑 10.27
  - [x] 适配MongoDB的订单创建逻辑
  - [x] 实现订单状态管理（发货/收货）
  - [x] 添加订单查询和取消功能
- [x] 修改[db_conn.py](be/model/db_conn.py) - 数据库连接层 10.27
  - [x] 替换SQLite连接为MongoDB连接
  - [x] 实现MongoDB基础操作封装
- [x] 修改[error.py](be/model/error.py) - 错误处理
  - [x] 添加MongoDB相关错误处理
  - [x] 添加订单状态相关错误码
- [x] 修改[seller.py](be/model/seller.py) - 卖家相关业务逻辑
  - [x] 适配新的Stores集合结构
  - [ ] 实现发货功能
  - [ ] 添加订单管理功能
- [x] 修改[user.py](be/model/user.py) - 用户认证逻辑
  - [x] 适配MongoDB的用户数据操作
- [x] 修改[store.py](be/model/store.py) - 数据库初始化
  - [x] 替换SQLite表创建为MongoDB集合初始化
  - [x] 创建必要的索引
- [ ] 实现新功能
  - [ ] 图书搜索功能（全文索引）
  - [ ] 订单超时自动取消
  - [ ] 分页查询优化
- [ ] 测试验证
  - [ ] 单元测试适配
  - [ ] 功能测试验证
  - [ ] 性能测试

## Schema
Users
```json
{
  "_id": String,// 唯一用户ID
  "password": String, // 加密密码
  "balance": Number, // 账户余额
  "token": String, // 登录token
  "terminal": String // 登录终端
}
```

Books
```json
{
  "_id": String, // 唯一图书ID，对应原SQLite的id
  "title": String,
  "author": String,
  "publisher": String,
  "original_title": String,
  "translator": String,
  "pub_year": String,
  "pages": Number,
  "price": Number, // 原价
  "currency_unit": String,
  "binding": String,
  "isbn": String,
  "author_intro": String,
  "book_intro": String,
  "content": String,
  "tags": String, 
  "picture": BinData // 图片二进制数据
}
```

Stores
```json
{
  "_id": String, // 唯一店铺ID
  "user_id": String, // 关联用户ID
  // 库存信息数组
  "inventory": [
    {
      "book_id": String,
      "stock_level": Number,
      "price": Number, // 该店铺的销售价格
    }
  ]
  

}
```

Orders
```json
{
  "_id": String, // 唯一订单ID
  "buyer_id": String, // 买家ID
  "store_id": String, // 店铺ID
  "total_amount": Number, // 订单总金额
  "status": String, // "unpaid", "paid", "shipped", "delivered", "cancelled", "timeout"
  "create_time": Date,
  "pay_time": Date,
  "ship_time": Date,
  "deliver_time": Date,
  "cancel_time": Date,
  "timeout_at": Date, // 超时取消时间
  
  // 订单项数组
  "items": [
    {
      "book_id": String,
      "quantity": Number,
      "unit_price": Number, //购买时的单价
      // 商品信息快照（避免书籍信息变更影响历史订单）
      "book_snapshot": {
        "title": String,
        "tag":String,
		"content": String
      }
    }
  ],
}
```

## 索引
### 索引与选择原因


Users（无需额外索引）
- 依赖 `_id` 默认主键即可；当前接口按用户ID读写。

Books（全站关键字/参数化搜索）
- 文本索引（集合仅允许一个 text 索引）：覆盖 `title/author/book_intro/content/tags` 并设权重。
  - 原因：满足“题目、标签、目录/内容”的关键字搜索；权重让标题/作者更靠前。
  - 示例：`db.Books.create_index([("title", "text"), ("author", "text"), ("book_intro", "text"), ("content", "text"), ("tags", "text")], name="books_text", default_language="none", weights={"title":10, "author":7, "tags":5, "book_intro":2, "content":2})`
- 前缀/精确索引（高频两项）：
  - `search_index.title_lower`：题目前缀/不区分大小写匹配（使用 `^` 前缀锚定）。
  - `search_index.tags_lower`：标签精确或包含匹配。

Stores（店铺范围搜索与库存操作）
- `inventory.book_id`（多键索引）：
  - 原因：店内库存按书目筛选与 `$elemMatch` 查询的高频场景；用于店铺范围限制（`_id in 店铺书目列表`）。

Orders（订单查询与状态管理）
- 复合索引：`(buyer_id, status, create_time)`。
  - 原因：买家查询历史订单（按状态筛选、按创建时间分页）。取消订单按 `_id` 更新不依赖索引。
- 状态超时扫描索引：`(status, timeout_at)`。
  - 原因：高效扫描未支付且超时的订单以进行自动取消。


### 查询策略与适配
- 全站关键字（Books 文本索引）：
  - 使用 `$text`，按 `textScore` 排序分页；覆盖题目、标签、目录/内容。
- 全站参数化：
  - 题目前缀：`{"search_index.title_lower": {"$regex": "^" + q}}`（锚定前缀）。
  - 标签：`{"search_index.tags_lower": q}` 或 `$in` 多标签。
- 店内搜索：
  - 先取店铺的 `book_id` 列表（走 `inventory.book_id` 索引）。
  - 在 Books 上 `$text` 或前缀/标签过滤，并限制 `_id in 店铺书目列表`。
  - 优点：只需维护 Books 一个文本索引；避免 Stores 文本索引的多键复杂度与额外写入成本。

