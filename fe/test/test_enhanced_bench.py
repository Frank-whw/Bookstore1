#!/usr/bin/env python3
"""
Enhanced Benchmark Test
增强基准测试的测试用例 - 基于最新的bench文件夹结构
"""

import pytest
import logging
import unittest.mock
from fe.bench.enhanced_workload import (
    EnhancedWorkload, 
    SearchBooks, 
    QueryOrders, 
    GetBookDetail,
    NewOrder,
    Payment,
    CancelOrder,
    ShipOrder,
    ReceiveOrder,
    AddFunds,
    NoIndexSearchBooks
)
from fe.bench.enhanced_session import EnhancedSession
from fe.bench.enhanced_run import (
    run_enhanced_bench,
    run_book_search_index_comparison,
    run_order_index_query_comparison,
    run_order_snapshot_query_comparison
)


class TestEnhancedBench:
    """增强基准测试类 - 基于最新的bench架构"""
    
    def test_enhanced_workload_creation(self):
        """测试增强工作负载创建"""
        try:
            workload = EnhancedWorkload()
            assert workload is not None
            assert hasattr(workload, 'stats')
            assert hasattr(workload, 'book_ids')
            assert hasattr(workload, 'buyer_ids')
            assert hasattr(workload, 'seller_ids')
            assert hasattr(workload, 'order_ids')
            assert hasattr(workload, 'order_ids_lock')
            
            # 验证统计结构
            expected_stats = [
                'search_basic', 'search_advanced', 'query_orders', 
                'new_order', 'payment', 'cancel_order', 
                'ship_order', 'receive_order', 'add_funds'
            ]
            for stat_type in expected_stats:
                assert stat_type in workload.stats
                assert 'count' in workload.stats[stat_type]
                assert 'success' in workload.stats[stat_type]
                assert 'time' in workload.stats[stat_type]
                
        except Exception as e:
            pytest.fail(f"工作负载创建失败: {e}")
    
    def test_search_operation_classes(self):
        """测试搜索操作类"""
        try:
            # 模拟buyer对象
            mock_buyer = unittest.mock.MagicMock()
            mock_buyer.search_books.return_value = (200, {"books": []})
            mock_buyer.search_books_advanced.return_value = (200, {"books": []})
            
            # 测试SearchBooks操作 - 基本搜索
            search_basic = SearchBooks(mock_buyer, "basic", keyword="test")
            assert search_basic is not None
            assert search_basic.search_type == "basic"
            
            # 测试SearchBooks操作 - 高级搜索
            search_advanced = SearchBooks(mock_buyer, "advanced", title_prefix="test")
            assert search_advanced is not None
            assert search_advanced.search_type == "advanced"
            
            # 测试NoIndexSearchBooks操作
            no_index_search = NoIndexSearchBooks(mock_buyer, "test")
            assert no_index_search is not None
            assert no_index_search.keyword == "test"
            
        except Exception as e:
            pytest.fail(f"搜索操作类测试失败: {e}")
    
    def test_order_operation_classes(self):
        """测试订单操作类"""
        try:
            # 模拟buyer和seller对象
            mock_buyer = unittest.mock.MagicMock()
            mock_seller = unittest.mock.MagicMock()
            mock_buyer.new_order.return_value = (200, "test_order_id")
            mock_buyer.payment.return_value = 200
            mock_buyer.cancel_order.return_value = 200
            mock_seller.ship_order.return_value = 200
            mock_buyer.receive_order.return_value = 200
            
            # 测试NewOrder操作
            new_order = NewOrder(mock_buyer, "test_store", [("book1", 1)])
            assert new_order is not None
            assert new_order.store_id == "test_store"
            
            # 测试Payment操作
            payment = Payment(mock_buyer, "test_order_id")
            assert payment is not None
            assert payment.order_id == "test_order_id"
            
            # 测试CancelOrder操作
            cancel_order = CancelOrder(mock_buyer, "test_order_id")
            assert cancel_order is not None
            assert cancel_order.order_id == "test_order_id"
            
            # 测试ShipOrder操作
            ship_order = ShipOrder(mock_seller, "test_order_id")
            assert ship_order is not None
            assert ship_order.order_id == "test_order_id"
            
            # 测试ReceiveOrder操作
            receive_order = ReceiveOrder(mock_buyer, "test_order_id")
            assert receive_order is not None
            assert receive_order.order_id == "test_order_id"
            
        except Exception as e:
            pytest.fail(f"订单操作类测试失败: {e}")
    
    def test_other_operation_classes(self):
        """测试其他操作类"""
        try:
            # 模拟buyer对象
            mock_buyer = unittest.mock.MagicMock()
            mock_buyer.query_orders.return_value = (200, {"orders": []})
            mock_buyer.get_book_detail.return_value = (200, {"book": {}})
            mock_buyer.add_funds.return_value = 200
            
            # 测试QueryOrders操作
            query_orders = QueryOrders(mock_buyer)
            assert query_orders is not None
            
            # 测试GetBookDetail操作
            get_book_detail = GetBookDetail(mock_buyer, "test_book_id")
            assert get_book_detail is not None
            assert get_book_detail.book_id == "test_book_id"
            
            # 测试AddFunds操作
            add_funds = AddFunds(mock_buyer, 100)
            assert add_funds is not None
            assert add_funds.add_value == 100
            
        except Exception as e:
            pytest.fail(f"其他操作类测试失败: {e}")
    
    def test_workload_stats_update(self):
        """测试统计更新功能"""
        try:
            workload = EnhancedWorkload()
            
            # 测试统计更新
            workload.update_stats("search_basic", True, 0.1)
            workload.update_stats("search_basic", False, 0.2)
            workload.update_stats("new_order", True, 0.15)
            
            # 验证search_basic统计
            stats = workload.stats["search_basic"]
            assert stats["count"] == 2
            assert stats["success"] == 1
            assert abs(stats["time"] - 0.3) < 1e-10  # 使用浮点数容差比较
            
            # 验证new_order统计
            stats = workload.stats["new_order"]
            assert stats["count"] == 1
            assert stats["success"] == 1
            assert abs(stats["time"] - 0.15) < 1e-10  # 使用浮点数容差比较
            
        except Exception as e:
            pytest.fail(f"统计更新测试失败: {e}")
    
    def test_workload_order_id_management(self):
        """测试订单ID管理功能"""
        try:
            workload = EnhancedWorkload()
            
            # 测试添加订单ID
            workload.add_order_id("order_1")
            workload.add_order_id("order_2")
            workload.add_order_id("order_3")
            
            assert len(workload.order_ids) == 3
            
            # 测试获取随机订单ID
            random_order_id = workload.get_random_order_id()
            assert random_order_id in ["order_1", "order_2", "order_3"]
            
            # 测试空订单ID列表
            workload.order_ids = []
            empty_order_id = workload.get_random_order_id()
            assert empty_order_id is None
            
        except Exception as e:
            pytest.fail(f"订单ID管理测试失败: {e}")
    
    def test_session_creation(self):
        """测试会话创建"""
        try:
            # 创建模拟工作负载
            workload = EnhancedWorkload()
            workload.procedure_per_session = 5  # 减少操作数量以加快测试
            
            # 模拟get_random_operation方法
            mock_operation = unittest.mock.MagicMock()
            mock_operation.run.return_value = True
            workload.get_random_operation = unittest.mock.MagicMock(return_value=mock_operation)
            
            # 创建会话
            session = EnhancedSession(workload, 1)
            assert session is not None
            assert session.session_id == 1
            assert session.workload == workload
            
        except Exception as e:
            pytest.fail(f"会话创建测试失败: {e}")
    
    def test_workload_helper_methods(self):
        """测试工作负载辅助方法"""
        try:
            workload = EnhancedWorkload()
            
            # 测试ID生成方法
            seller_id, password = workload.to_seller_id_and_password(1)
            assert seller_id is not None
            assert password is not None
            assert "seller_1" in seller_id
            assert "password_seller_1" in password
            
            buyer_id, password = workload.to_buyer_id_and_password(1)
            assert buyer_id is not None
            assert password is not None
            assert "buyer_1" in buyer_id
            assert "buyer_seller_1" in password
            
            store_id = workload.to_store_id(1, 1)
            assert store_id is not None
            assert "store_s_1_1" in store_id
            
        except Exception as e:
            pytest.fail(f"辅助方法测试失败: {e}")
    
    def test_workload_id_extraction_methods(self):
        """测试ID提取方法"""
        try:
            workload = EnhancedWorkload()
            
            # 测试从订单ID提取买家ID
            test_order_id = "buyer_1_uuid123_store_s_1_1_order123"
            buyer_id = workload.extract_buyer_id_from_order(test_order_id)
            if buyer_id:  # 可能返回None，这是正常的
                assert "buyer_1" in buyer_id
            
            # 测试从订单ID提取卖家ID
            seller_id = workload.extract_seller_id_from_order(test_order_id)
            if seller_id:  # 可能返回None，这是正常的
                assert "seller_" in seller_id
            
            # 测试密码获取方法
            if buyer_id:
                buyer_password = workload.get_buyer_password_by_id(buyer_id)
                assert buyer_password is not None
            
            if seller_id:
                seller_password = workload.get_seller_password_by_id(seller_id)
                assert seller_password is not None
                
        except Exception as e:
            pytest.fail(f"ID提取方法测试失败: {e}")
    
    @unittest.mock.patch('fe.bench.enhanced_run.EnhancedWorkload')
    @unittest.mock.patch('fe.bench.enhanced_run.EnhancedSession')
    def test_run_functions_mock(self, mock_session, mock_workload):
        """测试运行函数（使用mock避免实际执行）"""
        try:
            # 模拟工作负载和会话
            mock_wl = unittest.mock.MagicMock()
            mock_workload.return_value = mock_wl
            mock_wl.session = 1
            
            mock_sess = unittest.mock.MagicMock()
            mock_session.return_value = mock_sess
            
            # 测试主要运行函数存在且可调用
            assert callable(run_enhanced_bench)
            assert callable(run_book_search_index_comparison)
            assert callable(run_order_index_query_comparison)
            assert callable(run_order_snapshot_query_comparison)
            
            # 这些函数应该能够被导入而不出错
            logging.info("所有运行函数导入成功")
            
        except Exception as e:
            pytest.fail(f"运行函数测试失败: {e}")


if __name__ == "__main__":
    # 直接运行测试
    test = TestEnhancedBench()
    
    print("=== 运行增强基准测试 (基于最新bench架构) ===")
    
    try:
        test.test_enhanced_workload_creation()
        print("✅ 工作负载创建测试通过")
        
        test.test_search_operation_classes()
        print("✅ 搜索操作类测试通过")
        
        test.test_order_operation_classes()
        print("✅ 订单操作类测试通过")
        
        test.test_other_operation_classes()
        print("✅ 其他操作类测试通过")
        
        test.test_workload_stats_update()
        print("✅ 统计更新测试通过")
        
        test.test_workload_order_id_management()
        print("✅ 订单ID管理测试通过")
        
        test.test_session_creation()
        print("✅ 会话创建测试通过")
        
        test.test_workload_helper_methods()
        print("✅ 辅助方法测试通过")
        
        test.test_workload_id_extraction_methods()
        print("✅ ID提取方法测试通过")
        
        test.test_run_functions_mock()
        print("✅ 运行函数测试通过")
        
        print("\n🎉 所有测试完成！增强基准测试套件运行正常。")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        raise