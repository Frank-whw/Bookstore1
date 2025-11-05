#!/usr/bin/env python3
import sys
import os
import logging
import time
import uuid

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

from fe.bench.enhanced_workload import EnhancedWorkload
from fe.bench.enhanced_session import EnhancedSession

def run_enhanced_bench(test_name: str = "综合功能测试"):
    logging.info(f"{test_name}:")
    
    wl = EnhancedWorkload()
    
    logging.info("生成测试数据...")
    data_start = time.time()
    wl.gen_database()
    data_end = time.time()
    logging.info(f"数据生成: {data_end - data_start:.1f}s")
    
    sessions = []
    for i in range(wl.session):
        session = EnhancedSession(wl, i + 1)
        sessions.append(session)
    
    logging.info(f"启动 {len(sessions)} 个并发会话")
    test_start = time.time()
    
    for session in sessions:
        session.start()
    
    for session in sessions:
        session.join()
    
    test_end = time.time()
    logging.info(f"测试完成: {test_end - test_start:.1f}s")
    wl.print_stats()

def run_book_search_index_comparison():
    """书籍搜索索引性能对比: 无索引vs文本索引vs参数化索引"""
    logging.info("书籍搜索索引性能对比")
    
    logging.info("1.无索引搜索(正则表达式)")
    run_search_performance_test("no_index")
    
    logging.info("2.文本索引搜索")
    run_search_performance_test("text_index")
    
    logging.info("3.参数化索引搜索")
    run_search_performance_test("param_index")

def run_order_index_query_comparison():
    """订单索引查询对比: 无索引 vs 有索引"""
    logging.info("订单索引查询对比")
    
    logging.info("1.无索引订单查询")
    run_order_query_test(use_index=False)
    
    logging.info("2.有索引订单查询")
    run_order_query_test(use_index=True)

def run_order_snapshot_query_comparison():
    """订单快照查询对比: 无冗余数据 vs 有冗余数据"""
    logging.info("订单快照查询对比")
    
    logging.info("1.无冗余数据查询(需要关联)")
    run_snapshot_query_test(use_redundant=False)
    
    logging.info("2.有冗余数据查询(直接查询)")
    run_snapshot_query_test(use_redundant=True)
def run_search_performance_test(search_type: str):
    """搜索性能测试"""
    from fe.bench.enhanced_workload import SearchBooks, NoIndexSearchBooks
    from fe.access.new_buyer import register_new_buyer
    from fe.access.buyer import Buyer
    from fe import conf
    
    buyer_id = f"search_test_{uuid.uuid1()}"
    buyer = register_new_buyer(buyer_id, "password")
    buyer_client = Buyer(url_prefix=conf.URL, user_id=buyer_id, password="password")
    
    test_keywords = ['小说', '文学', '历史', '科学', '技术', '中国']
    test_count = 15000
    
    total_time = 0
    success_count = 0
    
    logging.info(f"开始 {search_type} 测试: {test_count} 次")
    
    for i in range(test_count):
        if search_type == "no_index":
            keyword = test_keywords[i % len(test_keywords)]
            operation = NoIndexSearchBooks(buyer_client, keyword=keyword)
        elif search_type == "text_index":
            keyword = test_keywords[i % len(test_keywords)]
            operation = SearchBooks(buyer_client, "basic", keyword=keyword)
        else:  # param_index
            if i % 2 == 0:
                prefix = test_keywords[i % len(test_keywords)][:2]
                operation = SearchBooks(buyer_client, "advanced", title_prefix=prefix)
            else:
                tag = test_keywords[i % len(test_keywords)]
                operation = SearchBooks(buyer_client, "advanced", tags=[tag])
        
        start_time = time.time()
        success = operation.run()
        end_time = time.time()
        
        elapsed = end_time - start_time
        total_time += elapsed
        
        if success:
            success_count += 1
    
    avg_latency = total_time / test_count
    success_rate = (success_count / test_count) * 100
    tps = success_count / total_time if total_time > 0 else 0
    
    logging.info(f"{search_type} 结果:")
    logging.info(f"  平均延迟: {avg_latency:.3f}s")
    logging.info(f"  成功率: {success_rate:.1f}%")
    logging.info(f"  TPS: {tps:.1f}")


def run_order_query_test(use_index: bool):
    """订单查询测试 - 对比有无索引的性能"""
    from fe.access.new_buyer import register_new_buyer
    from fe.access.buyer import Buyer
    from fe import conf
    import uuid
    
    buyer_id = f"order_test_{uuid.uuid1()}"
    buyer = register_new_buyer(buyer_id, "password")
    buyer_client = Buyer(url_prefix=conf.URL, user_id=buyer_id, password="password")
    
    test_count = 6000
    total_time = 0
    success_count = 0
    
    index_type = "有索引" if use_index else "无索引"
    logging.info(f"开始{index_type}订单查询测试: {test_count} 次")
    
    for i in range(test_count):
        start_time = time.time()
        from be.model.store import get_db
        db = get_db()
        try:
            if use_index:
                # 使用索引的查询 - 利用复合索引 (buyer_id, create_time)
                orders = list(db["Orders"].find(
                    {"buyer_id": buyer_id}
                ).sort("create_time", -1).limit(10))
                success = True
            else:
                # 无索引查询 - 强制全表扫描（禁用索引）
                orders = list(db["Orders"].find(
                    {"buyer_id": buyer_id}
                ).hint({"$natural": 1}).limit(10))  # hint强制不使用索引
                success = True
        except Exception as e:
            success = False
        
        end_time = time.time()
        elapsed = end_time - start_time
        total_time += elapsed
        
        if success:
            success_count += 1
    
    avg_latency = total_time / test_count
    success_rate = (success_count / test_count) * 100
    tps = success_count / total_time if total_time > 0 else 0
    
    logging.info(f"{index_type}订单查询结果:")
    logging.info(f"  平均延迟: {avg_latency:.3f}s")
    logging.info(f"  成功率: {success_rate:.1f}%")
    logging.info(f"  TPS: {tps:.1f}")


def run_snapshot_query_test(use_redundant: bool):
    """订单快照查询测试"""
    import time
    
    test_count = 3000
    total_time = 0
    success_count = 0
    
    redundant_type = "有冗余数据" if use_redundant else "无冗余数据"
    logging.info(f"开始{redundant_type}查询测试: {test_count} 次")
    
    for i in range(test_count):
        start_time = time.time()
        
        from be.model.store import get_db
        db = get_db()
        
        try:
            if use_redundant:
                # 有冗余数据：直接从订单快照中查询商品信息
                orders = list(db["Orders"].find(
                    {"items.book_snapshot": {"$exists": True}},
                    {"items.book_snapshot.title": 1, "items.book_snapshot.tag": 1}
                ).limit(10))
                success = True
            else:
                # 无冗余数据：需要关联查询Orders和Books集合
                orders = list(db["Orders"].find({}, {"items.book_id": 1}).limit(10))
                for order in orders:
                    for item in order.get("items", []):
                        book_id = item.get("book_id")
                        if book_id:
                            # 需要额外查询Books集合获取书籍信息
                            book = db["Books"].find_one({"_id": book_id}, {"title": 1, "tags": 1})
                success = True
        except Exception as e:
            success = False
        
        end_time = time.time()
        elapsed = end_time - start_time
        total_time += elapsed
        
        if success:
            success_count += 1
    
    avg_latency = total_time / test_count
    success_rate = (success_count / test_count) * 100
    tps = success_count / total_time if total_time > 0 else 0
    
    logging.info(f"{redundant_type}查询结果:")
    logging.info(f"  平均延迟: {avg_latency:.3f}s")
    logging.info(f"  成功率: {success_rate:.1f}%")
    logging.info(f"  TPS: {tps:.1f}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    
    print("数据库结构&操作性能测试:")
    print("1.综合功能测试")
    print("2.书籍搜索索引对比")
    print("3.订单索引查询对比")
    print("4.订单快照查询对比")
    
    choice = input("选择(1-4):").strip()
    
    if choice == "1":
        run_enhanced_bench()
    elif choice == "2":
        run_book_search_index_comparison()
    elif choice == "3":
        run_order_index_query_comparison()
    elif choice == "4":
        run_order_snapshot_query_comparison()
    else:
        print("默认运行综合测试")
        run_enhanced_bench()