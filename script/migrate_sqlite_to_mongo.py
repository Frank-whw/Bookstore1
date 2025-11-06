#!/usr/bin/env python3
"""
SQLite -> MongoDB migration script
- Supports be.db (users, user_store, store, new_order, new_order_detail)
- Optionally supports fe/data/book.db (book)
- Idempotent upserts and safe re-runs
- Dry-run mode to preview changes without writing
- Creates helpful indexes

Usage:
  python3 script/migrate_sqlite_to_mongo.py \
    --be-db be/be.db \
    --book-db fe/data/book.db \
    --mongo-uri mongodb://localhost:27017 \
    --mongo-db bookstore \
    --dry-run
"""

import argparse
import json
import logging
import os
import sqlite3
import time
from typing import Dict, List, Optional, Tuple

try:
    from pymongo import MongoClient, ASCENDING
    from pymongo.errors import PyMongoError
except Exception:
    MongoClient = None  # type: ignore
    PyMongoError = Exception  # type: ignore


logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate SQLite data to MongoDB")
    parser.add_argument("--be-db", default=os.path.join("be.db"), help="Path to be.db")
    parser.add_argument("--book-db", default=os.path.join("fe", "data", "book_lx.db"), help="Path to book.db (optional)")
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017", help="MongoDB connection URI")
    parser.add_argument("--mongo-db", default="bookstore", help="MongoDB database name")
    parser.add_argument("--batch-size", type=int, default=1000, help="Bulk write batch size")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    return parser.parse_args()


def connect_sqlite(path: str) -> Optional[sqlite3.Connection]:
    if not os.path.exists(path):
        logging.warning(f"SQLite file not found: {path}")
        return None
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logging.error(f"SQLite connect failed for {path}: {e}")
        return None


def connect_mongo(uri: str, db_name: str):
    if MongoClient is None:
        raise RuntimeError("pymongo is not installed. Install with: pip install pymongo")
    client = MongoClient(uri)
    return client[db_name]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        return cur.fetchone() is not None
    except sqlite3.Error:
        return False


def row_count(conn: sqlite3.Connection, table: str) -> int:
    cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
    return int(cur.fetchone()[0])


def migrate_users(be_conn: sqlite3.Connection, mongo_db, dry_run: bool) -> int:
    if dry_run:
        total = row_count(be_conn, "user")
        logging.info(f"users: {total} rows")
        sample = be_conn.execute(
            "SELECT user_id, password, balance, token, terminal FROM user LIMIT 3"
        ).fetchall()
        for r in sample:
            logging.info(f"sample user: {dict(r)}")
        return total

    count = 0
    cur = be_conn.execute(
        "SELECT user_id, password, balance, token, terminal FROM user"
    )
    for r in cur:
        doc = {
            "_id": r["user_id"],
            "password": r["password"],
            "balance": int(r["balance"]) if r["balance"] is not None else 0,
            "token": r["token"],
            "terminal": r["terminal"],
        }
        mongo_db.Users.update_one({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
        count += 1
    logging.info(f"users migrated: {count}")
    return count


def first_tag(tags) -> Optional[str]:
    if tags is None:
        return None
    if isinstance(tags, list):
        return tags[0] if tags else None
    if isinstance(tags, str):
        # handle newline-separated or comma-separated
        parts = [t.strip() for t in tags.replace("\n", ",").split(",") if t.strip()]
        return parts[0] if parts else None
    return None


def migrate_stores(be_conn: sqlite3.Connection, mongo_db, dry_run: bool) -> int:
    owners_total = row_count(be_conn, "user_store")
    inv_total = row_count(be_conn, "store")
    logging.info(f"stores: {owners_total} owners, {inv_total} inventory rows")

    if dry_run:
        sample_store_ids = [
            row[0]
            for row in be_conn.execute(
                "SELECT DISTINCT store_id FROM store LIMIT 3"
            ).fetchall()
        ]
        for sid in sample_store_ids:
            cnt = be_conn.execute(
                "SELECT COUNT(*) FROM store WHERE store_id=?", (sid,)
            ).fetchone()[0]
            sample_items = be_conn.execute(
                "SELECT store_id, book_id, book_info, stock_level FROM store WHERE store_id=? LIMIT 2",
                (sid,),
            ).fetchall()
            logging.info(
                f"sample store: {sid} items={cnt} sample_items={[{'book_id': i['book_id'], 'stock_level': i['stock_level']} for i in sample_items]}"
            )
        return int(inv_total)

    count = 0
    cur = be_conn.execute(
        "SELECT store_id, book_id, book_info, stock_level FROM store ORDER BY store_id"
    )
    current_store_id = None
    inventory = []

    def flush_store(store_id: Optional[str], inventory: List[Dict]):
        if not store_id:
            return
        owner_row = be_conn.execute(
            "SELECT user_id FROM user_store WHERE store_id=?", (store_id,)
        ).fetchone()
        user_id = owner_row[0] if owner_row else None
        doc = {
            "_id": store_id,
            "user_id": user_id,
            "inventory": inventory,
        }
        mongo_db.Stores.update_one({"_id": doc["_id"]}, {"$set": doc}, upsert=True)

    for r in cur:
        sid = r["store_id"]
        if current_store_id is None:
            current_store_id = sid
        if sid != current_store_id:
            flush_store(current_store_id, inventory)
            count += 1
            current_store_id = sid
            inventory = []
        try:
            info = json.loads(r["book_info"]) if r["book_info"] else {}
        except Exception:
            info = {}
        item = {
            "book_id": r["book_id"],
            "stock_level": int(r["stock_level"]) if r["stock_level"] is not None else 0,
            "price": info.get("price"),
        }
        inventory.append(item)

    # flush last store
    if current_store_id is not None:
        flush_store(current_store_id, inventory)
        count += 1

    logging.info(f"stores migrated: {count}")
    return count


def migrate_orders(be_conn: sqlite3.Connection, mongo_db, dry_run: bool) -> int:
    total_orders = row_count(be_conn, "new_order")
    logging.info(f"orders: {total_orders} in new_order")
    if dry_run:
        sample_orders = be_conn.execute(
            "SELECT order_id, user_id, store_id FROM new_order LIMIT 3"
        ).fetchall()
        for r in sample_orders:
            dcnt = be_conn.execute(
                "SELECT COUNT(*) FROM new_order_detail WHERE order_id=?",
                (r["order_id"],),
            ).fetchone()[0]
            logging.info(
                f"sample order: {r['order_id']} user={r['user_id']} items={dcnt}"
            )
        return int(total_orders)

    count = 0
    cur = be_conn.execute(
        "SELECT order_id, user_id, store_id FROM new_order"
    )
    for r in cur:
        order_id = r["order_id"]
        items = []
        dcur = be_conn.execute(
            "SELECT book_id, count, price FROM new_order_detail WHERE order_id=?",
            (order_id,),
        )
        for dr in dcur:
            # 获取书籍快照（来自 store 表的 book_info）
            snapshot = {"title": None, "tag": None, "content": None}
            try:
                prow = be_conn.execute(
                    "SELECT book_info FROM store WHERE store_id=? AND book_id=? LIMIT 1",
                    (r["store_id"], dr["book_id"]),
                ).fetchone()
                info = json.loads(prow["book_info"]) if (prow and prow["book_info"]) else None
                if isinstance(info, dict):
                    snapshot = {
                        "title": info.get("title"),
                        "tag": first_tag(info.get("tags")),
                        "content": info.get("content") or info.get("book_intro") or info.get("author_intro"),
                    }
            except Exception:
                pass
            items.append(
                {
                    "book_id": dr["book_id"],
                    "quantity": int(dr["count"]) if dr["count"] is not None else 0,
                    "unit_price": int(dr["price"]) if dr["price"] is not None else 0,
                    "book_snapshot": snapshot,
                }
            )
        total_amount = sum(i["quantity"] * i["unit_price"] for i in items)
        doc = {
            "_id": order_id,
            "buyer_id": r["user_id"],
            "store_id": r["store_id"],
            "items": items,
            "total_amount": total_amount,
            "status": "unpaid",
            # 与后端保持一致：使用 time.time()（秒）
            "create_time": time.time(),
            "pay_time": None,
            "ship_time": None,
            "deliver_time": None,
            "cancel_time": None,
            "timeout_at": None,
        }
        mongo_db.Orders.update_one(
            {"_id": doc["_id"]},
            {"$set": doc, "$unset": {"user_id": "", "total_price": ""}},
            upsert=True,
        )
        count += 1
    logging.info(f"orders migrated: {count}")
    return count


def migrate_books(book_conn: Optional[sqlite3.Connection], mongo_db, dry_run: bool) -> int:
    if book_conn is None:
        logging.info("book.db not available; skipping Books migration")
        return 0
    if not table_exists(book_conn, "book"):
        logging.info("book.db has no table 'book'; skipping")
        return 0

    total = row_count(book_conn, "book")
    logging.info(f"books: {total} rows")

    def to_lower(s: Optional[str]) -> Optional[str]:
        return s.lower() if isinstance(s, str) else None

    def tags_lower(tags: Optional[str]) -> List[str]:
        if not tags:
            return []
        parts = [t.strip().lower() for t in tags.replace("\n", ",").split(",") if t.strip()]
        return parts

    if dry_run:
        sample = book_conn.execute(
            "SELECT id, title, author, tags FROM book LIMIT 3"
        ).fetchall()
        for r in sample:
            logging.info(f"sample book: id={r['id']} title={r['title']} tags={r['tags']}")
        return int(total)

    count = 0
    cur = book_conn.execute(
        "SELECT id, title, author, publisher, original_title, translator, pub_year, pages, price, currency_unit, binding, isbn, author_intro, book_intro, content, tags, picture FROM book"
    )
    for r in cur:
        doc = {
            "_id": r["id"],
            "title": r["title"],
            "author": r["author"],
            "publisher": r["publisher"],
            "original_title": r["original_title"],
            "translator": r["translator"],
            "pub_year": r["pub_year"],
            "pages": int(r["pages"]) if r["pages"] is not None else None,
            "price": int(r["price"]) if r["price"] is not None else None,
            "currency_unit": r["currency_unit"],
            "binding": r["binding"],
            "isbn": r["isbn"],
            "author_intro": r["author_intro"],
            "book_intro": r["book_intro"],
            "content": r["content"],
            "tags": r["tags"],
            "picture": r["picture"],
            "search_index": {
                "title_lower": to_lower(r["title"]),
                "tags_lower": tags_lower(r["tags"]),
            },
        }
        mongo_db.Books.update_one({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
        count += 1
    logging.info(f"books migrated: {count}")
    return count


def create_indexes(mongo_db):
    try:
        mongo_db.Users.create_index([("token", ASCENDING)], sparse=True)
        mongo_db.Stores.create_index([("user_id", ASCENDING)])
        mongo_db.Stores.create_index([("inventory.book_id", ASCENDING)])
        # Orders 复合索引 + 超时索引
        mongo_db.Orders.create_index([("buyer_id", ASCENDING), ("status", ASCENDING), ("create_time", -1)], name="orders_by_buyer_status_time")
        mongo_db.Orders.create_index([("status", ASCENDING), ("create_time", ASCENDING)], name="orders_status_create_time")
        mongo_db.Orders.create_index([("status", ASCENDING), ("timeout_at", ASCENDING)], name="orders_timeout_scan")
        # Books 文本索引（集合只能有一个 text 索引）
        try:
            mongo_db.Books.create_index([
                ("title", "text"),
                ("author", "text"),
                ("book_intro", "text"),
                ("content", "text"),
                ("tags", "text"),
            ], name="books_text", default_language="none", weights={
                "title": 10,
                "author": 7,
                "tags": 5,
                "book_intro": 2,
                "content": 2,
            })
        except Exception:
            pass
        # 前缀索引：title/tags
        mongo_db.Books.create_index([("search_index.title_lower", ASCENDING)])
        mongo_db.Books.create_index([("search_index.tags_lower", ASCENDING)])
        logging.info("indexes created/verified")
    except PyMongoError as e:
        logging.error(f"create_indexes failed: {e}")


def main():
    args = parse_args()

    be_conn = connect_sqlite(args.be_db)
    book_conn = connect_sqlite(args.book_db)
    if be_conn is None:
        logging.error("be.db connection failed; aborting")
        return

    # Dry-run avoids connecting to Mongo to simplify preview
    mongo_db = None
    if not args.dry_run:
        mongo_db = connect_mongo(args.mongo_uri, args.mongo_db)

    # migrate be.db tables
    users_count = migrate_users(be_conn, mongo_db, args.dry_run)
    stores_count = migrate_stores(be_conn, mongo_db, args.dry_run)
    orders_count = migrate_orders(be_conn, mongo_db, args.dry_run)

    # migrate book.db tables (optional)
    books_count = migrate_books(book_conn, mongo_db, args.dry_run)

    # create indexes
    if not args.dry_run:
        create_indexes(mongo_db)

    logging.info(
        f"Summary: users={users_count}, stores={stores_count}, orders={orders_count}, books={books_count}, dry_run={args.dry_run}"
    )


if __name__ == "__main__":
    main()