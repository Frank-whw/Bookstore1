import pytest

from fe import conf
from fe.test.gen_book_data import GenBook
from fe.access.new_buyer import register_new_buyer
from fe.access.book import Book
from be.model.store import get_db
import uuid


class TestSearchBooks:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.seller_id = "test_search_books_seller_id_{}".format(str(uuid.uuid1()))
        self.store_id = "test_search_books_store_id_{}".format(str(uuid.uuid1()))
        self.buyer_id = "test_search_books_buyer_id_{}".format(str(uuid.uuid1()))
        self.password = self.seller_id
        
        gen_book = GenBook(self.seller_id, self.store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=25
        )
        self.buy_book_info_list = gen_book.buy_book_info_list
        assert ok
        
        self.buyer = register_new_buyer(self.buyer_id, self.password)
        
        yield

    def test_search_books_global(self):
        # 全站搜索
        # 一个通用关键词
        code, result = self.buyer.search_books("小说")
        assert code == 200
        assert "books" in result
        assert "pagination" in result
        
        # 验证分页信息
        pagination = result["pagination"]
        assert pagination["page"] == 1
        assert pagination["page_size"] == 10
        assert pagination["total_count"] >= 0

    def test_search_books_in_store(self):
        # 在特定店铺内搜索
        code, result = self.buyer.search_books("小说", store_id=self.store_id)
        assert code == 200
        assert "books" in result
        assert "pagination" in result

    def test_search_books_empty_keyword(self):
        code, result = self.buyer.search_books("")
        assert code != 200

    def test_search_books_non_exist_store(self):
        code, result = self.buyer.search_books("小说", store_id="non_exist_store")
        assert code != 200

    def test_search_books_pagination(self):
        # 第一页
        code, result = self.buyer.search_books("小说", page=1)
        assert code == 200
        assert result["pagination"]["page"] == 1
        assert len(result["books"]) <= 10
        
        # 测试用例25本书，能测试到第三页
        if result["pagination"]["total_count"] > 10:
            code, result2 = self.buyer.search_books("小说", page=2)
            assert code == 200
            assert result2["pagination"]["page"] == 2
            # 验证第二页的数据与第一页不同
            if result["books"] and result2["books"]:
                assert result["books"][0]["id"] != result2["books"][0]["id"]

        if result["pagination"]["total_count"] > 20:
            code, result3 = self.buyer.search_books("小说", page=3)
            assert code == 200
            assert result3["pagination"]["page"] == 3

    def test_search_books_invalid_page(self):
        code, result = self.buyer.search_books("小说", page="invalid")
        assert code != 200

    def test_search_books_pagination_comprehensive(self):
        # 全面测试分页
        code, result = self.buyer.search_books("小说")
        assert code == 200
        
        total_count = result["pagination"]["total_count"]
        total_pages = result["pagination"]["total_pages"]
        
        # 验证分页计算正确
        expected_pages = (total_count + 9) // 10
        assert total_pages == expected_pages
        
        # 验证分页基本功能
        if total_pages > 1:
            # 测试第一页
            code, page1_result = self.buyer.search_books("小说", page=1)
            assert code == 200
            assert page1_result["pagination"]["page"] == 1
            assert len(page1_result["books"]) == 10  # 第一页应该有10条
            
            # 测试第二页
            code, page2_result = self.buyer.search_books("小说", page=2)
            assert code == 200
            assert page2_result["pagination"]["page"] == 2
            assert len(page2_result["books"]) > 0
            
            # 验证分页信息一致性
            assert page1_result["pagination"]["total_count"] == page2_result["pagination"]["total_count"]
            assert page1_result["pagination"]["total_pages"] == page2_result["pagination"]["total_pages"]
            
            # 验证has_next和has_prev标志
            assert page1_result["pagination"]["has_next"] == True
            assert page1_result["pagination"]["has_prev"] == False
            assert page2_result["pagination"]["has_prev"] == True
            
            # 测试最后一页
            if total_pages > 2:
                code, last_page_result = self.buyer.search_books("小说", page=total_pages)
                assert code == 200
                assert last_page_result["pagination"]["page"] == total_pages
                assert last_page_result["pagination"]["has_next"] == False
                assert len(last_page_result["books"]) <= 10

    def test_search_books_advanced_title_prefix(self):
        # 标题前缀
        code, result = self.buyer.search_books_advanced(title_prefix="小")
        assert code == 200
        assert "books" in result
        assert "pagination" in result

    def test_search_books_advanced_tags(self):
        # 标签
        code, result = self.buyer.search_books_advanced(tags=["小说", "文学"])
        assert code == 200
        assert "books" in result
        assert "pagination" in result

    def test_search_books_advanced_combined(self):
        # 组合条件
        code, result = self.buyer.search_books_advanced(
            title_prefix="小", 
            tags=["小说"], 
            store_id=self.store_id
        )
        assert code == 200
        assert "books" in result
        assert "pagination" in result

    def test_search_books_advanced_empty_conditions(self):
        code, result = self.buyer.search_books_advanced()
        assert code != 200

    def test_search_books_advanced_in_store(self):
        # 店铺内搜索
        code, result = self.buyer.search_books_advanced(
            title_prefix="小", 
            store_id=self.store_id
        )
        assert code == 200
        assert "books" in result

    def test_search_books_advanced_non_exist_store(self):
        code, result = self.buyer.search_books_advanced(
            title_prefix="小", 
            store_id="non_exist_store"
        )
        assert code != 200

    def test_search_books_result_format(self):
        code, result = self.buyer.search_books("小说")
        assert code == 200
        
        if result["books"]:
            book = result["books"][0]
            # 书籍基本信息字段
            required_fields = ["id", "title", "author", "book_intro", "tags"]
            for field in required_fields:
                assert field in book

    def test_search_books_text_score(self):
        # 文本搜索评分
        code, result = self.buyer.search_books("小说")
        assert code == 200
        
        if result["books"]:
            book = result["books"][0]
            # text_score字段文本搜索时出现
            if "text_score" in book:
                assert isinstance(book["text_score"], (int, float))

    def test_get_book_detail(self):
        code, result = self.buyer.search_books("小说")
        assert code == 200
        
        if result["books"]:
            book_id = result["books"][0]["id"]
            
            # 获取书籍详情
            code, detail = self.buyer.get_book_detail(book_id)
            assert code == 200

            required_fields = [
                "id", "title", "author", "publisher", "original_title",
                "translator", "pub_year", "pages", "price", "currency_unit",
                "binding", "isbn", "author_intro", "book_intro", "content",
                "tags", "pictures"
            ]
            for field in required_fields:
                assert field in detail

    def test_get_book_detail_empty_id(self):
        code, detail = self.buyer.get_book_detail("")
        assert code != 200

    def test_get_book_detail_non_exist(self):
        code, detail = self.buyer.get_book_detail("non_exist_book_id")
        assert code != 200
