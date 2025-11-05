#!/usr/bin/env python3
"""
增强的会话管理，支持全功能性能测试
"""

import sys
import os
import time
import threading
import logging
import random

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

from fe.bench.enhanced_workload import EnhancedWorkload


class EnhancedSession(threading.Thread):    
    def __init__(self, workload: EnhancedWorkload, session_id: int):
        threading.Thread.__init__(self)
        self.workload = workload
        self.session_id = session_id
        self.operations = []
        self.results = {
            'total_operations': 0,
            'successful_operations': 0,
            'total_time': 0,
        }
        self.gen_operations()

    def gen_operations(self):
        # 不预生成操作，改为动态生成
        pass

    def run(self):
        total_operations = self.workload.procedure_per_session
        logging.info(f"会话 {self.session_id} 开始: {total_operations} 个操作")
        
        start_time = time.time()
        
        for i in range(total_operations):
            # 动态生成操作
            operation = self.workload.get_random_operation()
            if not operation:
                continue
            op_start = time.time()
            try:
                result = operation.run()
                # NewOrder返回(bool,str)
                if isinstance(result, tuple):
                    success, order_id = result
                    # 成功的订单创建需要保存订单ID
                    if success and hasattr(operation, '__class__') and operation.__class__.__name__ == 'NewOrder':
                        self.workload.add_order_id(order_id)
                else:
                    success = result
            except Exception as e:
                logging.error(f"操作异常: {e}")
                success = False
            op_end = time.time()
            
            elapsed = op_end - op_start
            
            self.results['total_operations'] += 1
            if success:
                self.results['successful_operations'] += 1
            self.results['total_time'] += elapsed
            
            operation_type = self.get_operation_type(operation)
            self.workload.update_stats(operation_type, success, elapsed)
            
            if (i + 1) % 200 == 0:
                progress = (i + 1) / total_operations * 100
                logging.info(f"会话 {self.session_id}: {progress:.0f}%")
        
        end_time = time.time()
        total_session_time = end_time - start_time
        
        success_rate = (self.results['successful_operations'] / self.results['total_operations']) * 100
        avg_latency = self.results['total_time'] / self.results['total_operations']
        
        logging.info(f"会话 {self.session_id} 完成: 成功率{success_rate:.1f}% 延迟{avg_latency:.3f}s")

    def get_operation_type(self, operation) -> str:
        class_name = operation.__class__.__name__
        # 映射类名到统计键
        type_mapping = {
            'SearchBooks': 'search_basic' if getattr(operation, 'search_type', '') == 'basic' else 'search_advanced',
            'QueryOrders': 'query_orders',
            'CancelOrder': 'cancel_order',
            'ShipOrder': 'ship_order',
            'ReceiveOrder': 'receive_order',
            'AddFunds': 'add_funds',
            'NewOrder': 'new_order',
            'Payment': 'payment',
        }
        
        return type_mapping.get(class_name, 'unknown')
