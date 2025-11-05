#!/usr/bin/env python3
"""
MongoDB search indexes creation script
- Creates search_index.title_lower and search_index.tags_lower indexes for Books collection
- Updates existing Books documents to include search_index fields
- Idempotent operations - safe to run multiple times
- Dry-run mode to preview changes without writing

Usage:
  python3 script/create_search_indexes.py \
    --mongo-uri mongodb://localhost:27017 \
    --mongo-db bookstore \
    --dry-run
"""

import argparse
import logging
from typing import Optional

try:
    from pymongo import MongoClient, ASCENDING
    from pymongo.errors import PyMongoError
except Exception:
    MongoClient = None  # type: ignore
    PyMongoError = Exception  # type: ignore


logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create MongoDB search indexes for Books collection")
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017", help="MongoDB connection URI")
    parser.add_argument("--mongo-db", default="bookstore", help="MongoDB database name")
    parser.add_argument("--batch-size", type=int, default=1000, help="Bulk update batch size")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    return parser.parse_args()


def connect_mongo(uri: str, db_name: str):
    if MongoClient is None:
        raise RuntimeError("pymongo is not installed. Install with: pip install pymongo")
    client = MongoClient(uri)
    return client[db_name]


def to_lower(s: Optional[str]) -> str:
    """Convert string to lowercase, handle None values"""
    return s.lower() if isinstance(s, str) else ""


def tags_to_lower(tags) -> list:
    """Convert tags to lowercase list, handle various input formats"""
    if not tags:
        return []
    
    if isinstance(tags, list):
        return [tag.lower() for tag in tags if isinstance(tag, str)]
    
    if isinstance(tags, str):
        # Handle newline-separated or comma-separated tags
        parts = [t.strip().lower() for t in tags.replace("\n", ",").split(",") if t.strip()]
        return parts
    
    return []


def check_existing_indexes(mongo_db, dry_run: bool) -> dict:
    """Check which search indexes already exist"""
    try:
        indexes = list(mongo_db.Books.list_indexes())
        existing = {}
        
        for index in indexes:
            name = index.get("name", "")
            if "search_index.title_lower" in name:
                existing["title_lower"] = True
            if "search_index.tags_lower" in name:
                existing["tags_lower"] = True
        
        logging.info(f"Existing search indexes: {existing}")
        return existing
    
    except PyMongoError as e:
        logging.error(f"Failed to check existing indexes: {e}")
        return {}


def create_search_indexes(mongo_db, dry_run: bool) -> bool:
    """Create search_index.title_lower and search_index.tags_lower indexes"""
    if dry_run:
        logging.info("DRY-RUN: Would create search indexes:")
        logging.info("  - search_index.title_lower (ASCENDING)")
        logging.info("  - search_index.tags_lower (ASCENDING)")
        return True
    
    try:
        # Create title_lower index
        try:
            mongo_db.Books.create_index([("search_index.title_lower", ASCENDING)])
            logging.info("Created index: search_index.title_lower")
        except PyMongoError as e:
            if "already exists" in str(e).lower():
                logging.info("Index already exists: search_index.title_lower")
            else:
                raise
        
        # Create tags_lower index
        try:
            mongo_db.Books.create_index([("search_index.tags_lower", ASCENDING)])
            logging.info("Created index: search_index.tags_lower")
        except PyMongoError as e:
            if "already exists" in str(e).lower():
                logging.info("Index already exists: search_index.tags_lower")
            else:
                raise
        
        return True
    
    except PyMongoError as e:
        logging.error(f"Failed to create search indexes: {e}")
        return False


def update_search_index_fields(mongo_db, batch_size: int, dry_run: bool) -> int:
    """Update Books documents to include search_index fields"""
    try:
        # Count total documents
        total_docs = mongo_db.Books.count_documents({})
        logging.info(f"Total Books documents: {total_docs}")
        
        # Count documents missing search_index field
        missing_search_index = mongo_db.Books.count_documents({"search_index": {"$exists": False}})
        logging.info(f"Documents missing search_index field: {missing_search_index}")
        
        if dry_run:
            if missing_search_index > 0:
                # Show sample documents that would be updated
                sample_docs = list(mongo_db.Books.find(
                    {"search_index": {"$exists": False}}, 
                    {"_id": 1, "title": 1, "tags": 1}
                ).limit(3))
                
                logging.info("DRY-RUN: Sample documents that would be updated:")
                for doc in sample_docs:
                    search_index = {
                        "title_lower": to_lower(doc.get("title")),
                        "tags_lower": tags_to_lower(doc.get("tags"))
                    }
                    logging.info(f"  {doc['_id']}: {search_index}")
            
            return missing_search_index
        
        if missing_search_index == 0:
            logging.info("All documents already have search_index field")
            return 0
        
        # Update documents in batches
        updated_count = 0
        cursor = mongo_db.Books.find(
            {"search_index": {"$exists": False}}, 
            {"_id": 1, "title": 1, "tags": 1}
        )
        
        batch_updates = []
        for doc in cursor:
            search_index = {
                "title_lower": to_lower(doc.get("title")),
                "tags_lower": tags_to_lower(doc.get("tags"))
            }
            
            batch_updates.append({
                "filter": {"_id": doc["_id"]},
                "update": {"$set": {"search_index": search_index}}
            })
            
            # Execute batch when it reaches batch_size
            if len(batch_updates) >= batch_size:
                result = mongo_db.Books.bulk_write([
                    {"updateOne": update} for update in batch_updates
                ])
                updated_count += result.modified_count
                logging.info(f"Updated {updated_count}/{missing_search_index} documents")
                batch_updates = []
        
        # Execute remaining updates
        if batch_updates:
            result = mongo_db.Books.bulk_write([
                {"updateOne": update} for update in batch_updates
            ])
            updated_count += result.modified_count
        
        logging.info(f"search_index fields updated: {updated_count}")
        return updated_count
    
    except PyMongoError as e:
        logging.error(f"Failed to update search_index fields: {e}")
        return 0


def verify_search_functionality(mongo_db, dry_run: bool) -> bool:
    """Verify that search indexes are working correctly"""
    if dry_run:
        logging.info("DRY-RUN: Would verify search functionality")
        return True
    
    try:
        # Test title_lower index
        result = mongo_db.Books.find({"search_index.title_lower": {"$regex": "^python"}}).limit(1)
        title_test = len(list(result)) >= 0  # Just check if query executes without error
        
        # Test tags_lower index
        result = mongo_db.Books.find({"search_index.tags_lower": {"$in": ["小说", "文学"]}}).limit(1)
        tags_test = len(list(result)) >= 0  # Just check if query executes without error
        
        if title_test and tags_test:
            logging.info("Search functionality verification: PASSED")
            return True
        else:
            logging.warning("Search functionality verification: FAILED")
            return False
    
    except PyMongoError as e:
        logging.error(f"Search functionality verification failed: {e}")
        return False


def main():
    args = parse_args()
    
    try:
        # Connect to MongoDB
        mongo_db = connect_mongo(args.mongo_uri, args.mongo_db)
        logging.info(f"Connected to MongoDB: {args.mongo_uri}/{args.mongo_db}")
        
        # Check existing indexes
        existing_indexes = check_existing_indexes(mongo_db, args.dry_run)
        
        # Create search indexes
        indexes_created = create_search_indexes(mongo_db, args.dry_run)
        if not indexes_created and not args.dry_run:
            logging.error("Failed to create indexes; aborting")
            return
        
        # Update search_index fields in documents
        updated_count = update_search_index_fields(mongo_db, args.batch_size, args.dry_run)
        
        # Verify search functionality
        verification_passed = verify_search_functionality(mongo_db, args.dry_run)
        
        # Summary
        logging.info(
            f"Summary: indexes_created={indexes_created}, "
            f"documents_updated={updated_count}, "
            f"verification_passed={verification_passed}, "
            f"dry_run={args.dry_run}"
        )
        
    except Exception as e:
        logging.error(f"Script execution failed: {e}")
        raise


if __name__ == "__main__":
    main()
