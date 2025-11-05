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

def run_order_index_performance_comparison():
    """订单索引性能对比: 查询效率vs更新效率"""
    logging.info("订单索引性能对比")
    
    logging.info("1.订单查询性能(索引受益)")
    run_order_performance_test("query")
    
    logging.info("2.订单更新性能(索引开销)")
    run_order_performance_test("update")
def run_inventory_index_performance_test():
    """库存多键索引性能测试: 查询vs更新"""
    logging.info("库存多键索引性能测试")
    
    logging.info("1.库存查询性能")
    run_inventory_performance_test("query")
    
    logging.info("2.库存更新性能")
    run_inventory_performance_test("update")

def run_order_snapshot_redundancy_test():
    """订单快照冗余数据性能测试: 查询优势vs插入开销"""
    logging.info("订单快照冗余数据性能测试")
    
    logging.info("1.快照查询性能(冗余数据优势)")
    run_snapshot_performance_test("query")
    
    logging.info("2.快照插入性能(冗余数据开销)")
    run_snapshot_performance_test("insert")
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
    test_count = 30
    
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
        
        if (i + 1) % 10 == 0:
            logging.info(f"进度: {i+1}/{test_count}")
    
    avg_latency = total_time / test_count
    success_rate = (success_count / test_count) * 100
    tps = success_count / total_time if total_time > 0 else 0
    
    logging.info(f"{search_type} 结果:")
    logging.info(f"  平均延迟: {avg_latency:.3f}s")
    logging.info(f"  成功率: {success_rate:.1f}%")
    logging.info(f"  TPS: {tps:.1f}")


def run_order_performance_test(test_type: str):
    """订单性能测试"""
    from fe.bench.enhanced_workload import OrderQueryTest, OrderUpdateTest
    from fe.access.new_buyer import register_new_buyer
    from fe.access.buyer import Buyer
    from fe import conf
    import uuid
    
    buyer_id = f"order_test_{uuid.uuid1()}"
    buyer = register_new_buyer(buyer_id, "password")
    buyer_client = Buyer(url_prefix=conf.URL, user_id=buyer_id, password="password")
    
    test_count = 20
    total_time = 0
    success_count = 0
    
    logging.info(f"开始订单{test_type}测试: {test_count} 次")
    
    for i in range(test_count):
        if test_type == "query":
            operation = OrderQueryTest(buyer_client)
        else:  # update
            operation = OrderUpdateTest(buyer_client)
        
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
    
    logging.info(f"订单{test_type} 结果:")
    logging.info(f"  平均延迟: {avg_latency:.3f}s")
    logging.info(f"  成功率: {success_rate:.1f}%")
    logging.info(f"  TPS: {tps:.1f}")


def run_inventory_performance_test(test_type: str):
    """库存性能测试"""
    from fe.bench.enhanced_workload import InventoryQueryTest, InventoryUpdateTest
    from fe.access.new_seller import register_new_seller
    from fe.access.seller import Seller
    from fe import conf
    import uuid
    
    seller_id = f"inventory_test_{uuid.uuid1()}"
    seller = register_new_seller(seller_id, "password")
    seller_client = Seller(url_prefix=conf.URL, seller_id=seller_id, password="password")
    
    test_count = 20
    total_time = 0
    success_count = 0
    
    logging.info(f"开始库存{test_type}测试: {test_count} 次")
    
    for i in range(test_count):
        if test_type == "query":
            operation = InventoryQueryTest(seller_client)
        else:  # update
            operation = InventoryUpdateTest(seller_client)
        
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
    
    logging.info(f"库存{test_type} 结果:")
    logging.info(f"  平均延迟: {avg_latency:.3f}s")
    logging.info(f"  成功率: {success_rate:.1f}%")
    logging.info(f"  TPS: {tps:.1f}")


def run_snapshot_performance_test(test_type: str):
    """订单快照性能测试"""
    from fe.bench.enhanced_workload import OrderSnapshotQueryTest, OrderSnapshotInsertTest
    import time
    
    test_count = 20
    total_time = 0
    success_count = 0
    
    logging.info(f"开始快照{test_type}测试: {test_count} 次")
    
    for i in range(test_count):
        if test_type == "query":
            operation = OrderSnapshotQueryTest()
        else:  # insert
            operation = OrderSnapshotInsertTest()
        
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
    
    logging.info(f"快照{test_type} 结果:")
    logging.info(f"  平均延迟: {avg_latency:.3f}s")
    logging.info(f"  成功率: {success_rate:.1f}%")
    logging.info(f"  TPS: {tps:.1f}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    
    print("数据库索引性能测试:")
    print("1. 综合功能测试")
    print("2. 书籍搜索索引对比")
    print("3. 订单索引性能对比")
    print("4. 库存多键索引测试")
    print("5. 订单快照冗余数据测试")
    
    choice = input("选择 (1-5): ").strip()
    
    if choice == "1":
        run_enhanced_bench()
    elif choice == "2":
        run_book_search_index_comparison()
    elif choice == "3":
        run_order_index_performance_comparison()
    elif choice == "4":
        run_inventory_index_performance_test()
    elif choice == "5":
        run_order_snapshot_redundancy_test()
    else:
        print("默认运行综合测试")
        run_enhanced_bench()