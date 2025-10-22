## Todo
- [x] 设计[Schema](##Schema) 10.21
- [x] 迁移数据库
  - [x] 创建MongoDB连接配置
  - [x] 编写数据迁移脚本
  - [x] 从SQLite导入book.db数据到MongoDB
- [ ] 修改[buyer.py](be/model/buyer.py) - 买家相关业务逻辑
  - [ ] 适配MongoDB的订单创建逻辑
  - [ ] 实现订单状态管理（发货/收货）
  - [ ] 添加订单查询和取消功能
- [ ] 修改[db_conn.py](be/model/db_conn.py) - 数据库连接层
  - [ ] 替换SQLite连接为MongoDB连接
  - [ ] 实现MongoDB基础操作封装
- [ ] 修改[error.py](be/model/error.py) - 错误处理
  - [ ] 添加MongoDB相关错误处理
  - [ ] 添加订单状态相关错误码
- [ ] 修改[seller.py](be/model/seller.py) - 卖家相关业务逻辑
  - [ ] 适配新的Stores集合结构
  - [ ] 实现发货功能
  - [ ] 添加订单管理功能
- [ ] 修改[user.py](be/model/user.py) - 用户认证逻辑
  - [ ] 适配MongoDB的用户数据操作
- [ ] 修改[store.py](be/model/store.py) - 数据库初始化
  - [ ] 替换SQLite表创建为MongoDB集合初始化
  - [ ] 创建必要的索引
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
  
  // 全文搜索优化字段
  "search_index": {
    "title_lower": String, // 小写标题，便于搜索
    "author_lower": String, // 小写作者
    "tags_lower": [String], // 小写标签
    "content_lower": String // 小写内容摘要
  }
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
	  "book_info":
	  {
		"title": String,
		"tag":String,
		"content": String
		
	  }
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