#!/usr/bin/env python3
"""
Enhanced Benchmark Test
增强基准测试的测试用例
"""

import pytest
import logging
import unittest.mock
from fe.bench.enhanced_workload import EnhancedWorkload, SearchBooks, QueryOrders, GetBookDetail
from fe.bench.enhanced_session import EnhancedSession


class TestEnhancedBench:
    """增强基准测试类"""
    
    def test_enhanced_workload_creation(self):
        """测试增强工作负载创建"""
        try:
            workload = EnhancedWorkload()
            assert workload is not None
            assert hasattr(workload, 'stats')
            assert hasattr(workload, 'book_ids')
            assert hasattr(workload, 'buyer_ids')
            assert hasattr(workload, 'seller_ids')
        except Exception as e:
            pytest.fail(f"工作负载创建失败: {e}")
    
    def test_operation_classes(self):
        """测试操作类的创建"""
        try:
            # 模拟buyer对象
            mock_buyer = unittest.mock.MagicMock()
            mock_buyer.search_books.return_value = (200, {"books": []})
            mock_buyer.search_books_advanced.return_value = (200, {"books": []})
            mock_buyer.query_orders.return_value = (200, {"orders": []})
            mock_buyer.get_book_detail.return_value = (200, {"book": {}})
            
            # 测试SearchBooks操作
            search_op = SearchBooks(mock_buyer, "basic", keyword="test")
            assert search_op is not None
            assert search_op.search_type == "basic"
            
            # 测试QueryOrders操作
            query_op = QueryOrders(mock_buyer)
            assert query_op is not None
            
            # 测试GetBookDetail操作
            detail_op = GetBookDetail(mock_buyer, "test_book_id")
            assert detail_op is not None
            assert detail_op.book_id == "test_book_id"
            
        except Exception as e:
            pytest.fail(f"操作类测试失败: {e}")
    
    def test_workload_stats_update(self):
        """测试统计更新功能"""
        try:
            workload = EnhancedWorkload()
            
            # 测试统计更新
            workload.update_stats("search_basic", True, 0.1)
            workload.update_stats("search_basic", False, 0.2)
            
            stats = workload.stats["search_basic"]
            assert stats["count"] == 2
            assert stats["success"] == 1
            assert stats["time"] == 0.3
            
        except Exception as e:
            pytest.fail(f"统计更新测试失败: {e}")
    
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
            assert len(session.operations) == 5
            
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
            
            buyer_id, password = workload.to_buyer_id_and_password(1)
            assert buyer_id is not None
            assert password is not None
            assert "buyer_1" in buyer_id
            
            store_id = workload.to_store_id(1, 1)
            assert store_id is not None
            assert "store_s_1_1" in store_id
            
        except Exception as e:
            pytest.fail(f"辅助方法测试失败: {e}")


if __name__ == "__main__":
    # 直接运行测试
    test = TestEnhancedBench()
    
    print("=== 运行增强基准测试 ===")
    test.test_enhanced_workload_creation()
    test.test_operation_classes()
    test.test_workload_stats_update()
    test.test_session_creation()
    test.test_workload_helper_methods()
    print("所有测试完成！")
