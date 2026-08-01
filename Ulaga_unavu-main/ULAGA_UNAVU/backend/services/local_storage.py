"""
Local Storage Service - JSON file-based storage
Replaces MongoDB for simple, reliable local development
"""

import os
import json
import logging
import copy
from datetime import datetime, date
from pathlib import Path
from threading import Lock
import uuid

logger = logging.getLogger(__name__)

class LocalStorageService:
    """JSON file-based storage service - MongoDB replacement"""
    
    def __init__(self, data_dir=None):
        # Set data directory
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            # Default: backend/data folder
            self.data_dir = Path(__file__).parent.parent / 'data'
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._locks = {}  # Thread locks for each collection
        self._cache = {}  # In-memory cache
        
        # Initialize default collections
        self._init_collections()
        logger.info(f"✅ LocalStorage initialized at: {self.data_dir}")
    
    def _init_collections(self):
        """Initialize default collection files"""
        collections = [
            'users',
            'counters',
            'user_settings',
            'soil_results',
            'crop_selections',
            'disease_results',
            'fertilizer_schedules',
            'growth_tracking',
            'market_snapshots',
            'chat_history',
            'news_cache',
            'notifications'
        ]
        
        for collection in collections:
            file_path = self.data_dir / f"{collection}.json"
            if not file_path.exists():
                self._write_file(collection, [])
            self._locks[collection] = Lock()
    
    def _get_file_path(self, collection_name):
        """Get file path for collection"""
        return self.data_dir / f"{collection_name}.json"
    
    def _read_file(self, collection_name):
        """Read collection from file with thread safety"""
        # Ensure lock exists
        if collection_name not in self._locks:
            self._locks[collection_name] = Lock()
            
        with self._locks[collection_name]:
            # Check cache first
            if collection_name in self._cache:
                return self._cache[collection_name]
            
            file_path = self._get_file_path(collection_name)
            
            if not file_path.exists():
                return []
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._cache[collection_name] = data
                    return data
            except json.JSONDecodeError:
                logger.error(f"❌ Invalid JSON in {collection_name}.json - returning empty list but NOT wiping file.")
                # Return empty list in memory, but DO NOT call _write_file (don't wipe the disk!)
                return []
            except Exception as e:
                logger.error(f"Error reading {collection_name}: {str(e)}")
                return []
    
    def _write_file(self, collection_name, data):
        """Write collection to file atomically with thread safety"""
        if collection_name not in self._locks:
            self._locks[collection_name] = Lock()
            
        file_path = self._get_file_path(collection_name)
        temp_path = file_path.with_suffix('.tmp')
        
        with self._locks[collection_name]:
            try:
                # Write to temporary file first
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=self._json_serializer)
                
                # Atomic replace (Windows handles this via os.replace, though directory must exist)
                import os
                os.replace(temp_path, file_path)
                
                # Cache a JSON-safe copy to avoid datetime objects breaking sort/comparisons.
                try:
                    self._cache[collection_name] = json.loads(
                        json.dumps(data, default=self._json_serializer)
                    )
                except Exception:
                    # If serialization fails, clear cache to avoid stale/invalid data.
                    self._cache.pop(collection_name, None)
                return True
            except Exception as e:
                logger.error(f"Error writing {collection_name}: {str(e)}")
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except:
                        pass
                return False
    
    def _json_serializer(self, obj):
        """Custom JSON serializer for datetime objects"""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def _parse_datetime(self, value):
        """Parse datetime from ISO format string"""
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except:
                return value
        return value
    
    def _generate_id(self):
        """Generate unique document ID"""
        # 24-char hex keeps compatibility with code that expects Mongo-like IDs.
        return uuid.uuid4().hex[:24]
    
    # ==========================================
    # Status Methods
    # ==========================================
    
    def is_available(self):
        """Always available - local storage"""
        return True
    
    def is_offline(self):
        """Not offline mode - we have persistent storage"""
        return False
    
    def get_status(self):
        """Get storage status"""
        return {
            "status": "online",
            "type": "local_storage",
            "path": str(self.data_dir),
            "message": "Local JSON storage active"
        }
    
    def get_collection(self, collection_name):
        """
        Get a collection wrapper for MongoDB-compatible API
        Returns a CollectionWrapper that supports find_one, insert_one, etc.
        """
        return CollectionWrapper(self, collection_name)
    
    # ==========================================
    # CRUD Operations
    # ==========================================
    
    def insert_one(self, collection_name, document):
        """Insert single document"""
        # ID generation and data manipulation don't need lock, but _read/_write do.
        # We handle locks inside _read_file and _write_file.
        data = self._read_file(collection_name)
        
        # Generate ID if not present
        if '_id' not in document:
            document['_id'] = self._generate_id()
        
        # Add timestamps
        document['created_at'] = datetime.utcnow().isoformat()
        document['updated_at'] = datetime.utcnow().isoformat()
        
        data.append(document)
        self._write_file(collection_name, data)
        
        # Return result object
        return type('InsertResult', (), {'inserted_id': document['_id']})()
    
    def find_one(self, collection_name, query=None, projection=None, sort=None, **kwargs):
        """Find single document matching query with optional sort support."""
        data = self._read_file(collection_name)
        query = query or {}

        # Filter by query first.
        if query:
            data = [doc for doc in data if self._match_query(doc, query)]

        # Apply sorting if requested (Mongo-style [(field, direction)]).
        if sort:
            for key, direction in reversed(sort):
                reverse = (direction == -1)
                data = sorted(
                    data,
                    key=lambda x: self._get_nested(x, key) or "",
                    reverse=reverse
                )

        if not data:
            return None

        # Return a deepcopy to prevent in-memory mutation by callers (e.g., pop('_id'))
        doc = copy.deepcopy(data[0])
        return self._apply_projection(doc, projection)
    
    def find(self, collection_name, query=None, projection=None, sort=None, limit=0):
        """Find multiple documents"""
        data = self._read_file(collection_name)
        
        # Filter by query
        if query:
            data = [doc for doc in data if self._match_query(doc, query)]
        
        # Apply sorting
        if sort:
            for key, direction in reversed(sort):
                reverse = (direction == -1)
                data = sorted(data, key=lambda x: self._get_nested(x, key) or '', reverse=reverse)
        
        # Apply limit
        if limit > 0:
            data = data[:limit]
        
        # Apply projection and ensure deepcopy for all results to prevent in-memory mutation
        return [self._apply_projection(copy.deepcopy(doc), projection) for doc in data]
    
    def update_one(self, collection_name, query, update, upsert=False, return_document=False):
        """Update single document matching query. Returns result with optional updated doc."""
        data = self._read_file(collection_name)
        modified = False
        upserted_id = None
        updated_doc = None
        
        for i, doc in enumerate(data):
            if self._match_query(doc, query):
                # Apply update operators
                if '$set' in update:
                    for k, v in update['$set'].items():
                        self._set_nested(data[i], k, v)
                if '$inc' in update:
                    for k, v in update['$inc'].items():
                        current = self._get_nested(data[i], k) or 0
                        self._set_nested(data[i], k, current + v)
                if '$push' in update:
                    for k, v in update['$push'].items():
                        current = self._get_nested(data[i], k) or []
                        current.append(v)
                        self._set_nested(data[i], k, current)
                
                data[i]['updated_at'] = datetime.utcnow().isoformat()
                modified = True
                updated_doc = copy.deepcopy(data[i])
                break
        
        # Upsert if not found
        if not modified and upsert:
            new_doc = dict(query)
            # Only generate _id if not already in query
            if '_id' not in new_doc:
                new_doc['_id'] = self._generate_id()
            new_doc['created_at'] = datetime.utcnow().isoformat()
            new_doc['updated_at'] = datetime.utcnow().isoformat()
            
            if '$set' in update:
                for k, v in update['$set'].items():
                    self._set_nested(new_doc, k, v)
            if '$inc' in update:
                for k, v in update['$inc'].items():
                    self._set_nested(new_doc, k, v)
            
            data.append(new_doc)
            upserted_id = new_doc['_id']
            updated_doc = copy.deepcopy(new_doc)
        
        self._write_file(collection_name, data)
        
        return type('UpdateResult', (), {
            'modified_count': 1 if modified else 0,
            'upserted_id': upserted_id,
            'updated_document': updated_doc
        })()

    def update_many(self, collection_name, query, update, upsert=False):
        """Update multiple documents"""
        data = self._read_file(collection_name)
        modified_count = 0
        upserted_id = None

        for i, doc in enumerate(data):
            if self._match_query(doc, query):
                # Apply update operators
                if '$set' in update:
                    for k, v in update['$set'].items():
                        self._set_nested(data[i], k, v)
                if '$inc' in update:
                    for k, v in update['$inc'].items():
                        current = self._get_nested(data[i], k) or 0
                        self._set_nested(data[i], k, current + v)
                if '$push' in update:
                    for k, v in update['$push'].items():
                        current = self._get_nested(data[i], k) or []
                        current.append(v)
                        self._set_nested(data[i], k, current)

                data[i]['updated_at'] = datetime.utcnow().isoformat()
                modified_count += 1

        # Upsert if no matches
        if modified_count == 0 and upsert:
            new_doc = dict(query)
            if '_id' not in new_doc:
                new_doc['_id'] = self._generate_id()
            new_doc['created_at'] = datetime.utcnow().isoformat()
            new_doc['updated_at'] = datetime.utcnow().isoformat()

            if '$set' in update:
                for k, v in update['$set'].items():
                    self._set_nested(new_doc, k, v)
            if '$inc' in update:
                for k, v in update['$inc'].items():
                    self._set_nested(new_doc, k, v)
            if '$push' in update:
                for k, v in update['$push'].items():
                    self._set_nested(new_doc, k, [v])

            data.append(new_doc)
            upserted_id = new_doc['_id']

        self._write_file(collection_name, data)

        return type('UpdateResult', (), {
            'modified_count': modified_count,
            'upserted_id': upserted_id
        })()
    
    def delete_one(self, collection_name, query):
        """Delete single document"""
        data = self._read_file(collection_name)
        
        for i, doc in enumerate(data):
            if self._match_query(doc, query):
                del data[i]
                self._write_file(collection_name, data)
                return type('DeleteResult', (), {'deleted_count': 1})()
        
        return type('DeleteResult', (), {'deleted_count': 0})()
    
    def delete_many(self, collection_name, query):
        """Delete multiple documents"""
        data = self._read_file(collection_name)
        original_count = len(data)
        
        data = [doc for doc in data if not self._match_query(doc, query)]
        deleted_count = original_count - len(data)
        
        self._write_file(collection_name, data)
        return type('DeleteResult', (), {'deleted_count': deleted_count})()
    
    def count_documents(self, collection_name, query=None):
        """Count documents matching query"""
        data = self._read_file(collection_name)
        
        if query:
            data = [doc for doc in data if self._match_query(doc, query)]
        
        return len(data)
    
    def aggregate(self, collection_name, pipeline):
        """Simple aggregation support"""
        data = self._read_file(collection_name)
        
        for stage in pipeline:
            if '$match' in stage:
                data = [doc for doc in data if self._match_query(doc, stage['$match'])]
            elif '$sort' in stage:
                for key, direction in reversed(list(stage['$sort'].items())):
                    data = sorted(data, key=lambda x: self._get_nested(x, key) or '', reverse=(direction == -1))
            elif '$limit' in stage:
                data = data[:stage['$limit']]
            elif '$skip' in stage:
                data = data[stage['$skip']:]
        
        return data
    
    # ==========================================
    # Helper Methods
    # ==========================================
    
    def _match_query(self, document, query):
        """Check if document matches query"""
        for key, value in query.items():
            # Handle special operators
            if key.startswith('$'):
                if key == '$or':
                    if not any(self._match_query(document, q) for q in value):
                        return False
                elif key == '$and':
                    if not all(self._match_query(document, q) for q in value):
                        return False
                continue
            
            doc_value = self._get_nested(document, key)
            
            # Handle comparison operators
            if isinstance(value, dict):
                for op, op_val in value.items():
                    if op == '$eq' and doc_value != op_val:
                        return False
                    elif op == '$ne' and doc_value == op_val:
                        return False
                    elif op == '$gt' and (doc_value is None or doc_value <= op_val):
                        return False
                    elif op == '$gte' and (doc_value is None or doc_value < op_val):
                        return False
                    elif op == '$lt' and (doc_value is None or doc_value >= op_val):
                        return False
                    elif op == '$lte' and (doc_value is None or doc_value > op_val):
                        return False
                    elif op == '$in' and doc_value not in op_val:
                        return False
                    elif op == '$nin' and doc_value in op_val:
                        return False
                    elif op == '$exists':
                        exists = key in document
                        if op_val and not exists:
                            return False
                        if not op_val and exists:
                            return False
            else:
                # Direct equality check
                if doc_value != value:
                    return False
        
        return True
    
    def _get_nested(self, document, key):
        """Get nested value using dot notation"""
        keys = key.split('.')
        value = document
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return None
        
        return value
    
    def _set_nested(self, document, key, value):
        """Set nested value using dot notation"""
        keys = key.split('.')
        
        for k in keys[:-1]:
            if k not in document:
                document[k] = {}
            document = document[k]
        
        document[keys[-1]] = value
    
    def _delete_nested(self, document, key):
        """Delete nested key using dot notation"""
        keys = key.split('.')
        target = document

        for k in keys[:-1]:
            if not isinstance(target, dict) or k not in target:
                return
            target = target[k]

        if isinstance(target, dict):
            target.pop(keys[-1], None)

    def _apply_projection(self, document, projection):
        """Apply Mongo-like projection include/exclude behavior."""
        if not projection:
            return document

        # List-style include projection.
        if isinstance(projection, (list, tuple, set)):
            projected = {}
            for key in projection:
                value = self._get_nested(document, key)
                if value is not None:
                    self._set_nested(projected, key, value)
            return projected

        # Dict-style projection.
        if isinstance(projection, dict):
            include_keys = [k for k, v in projection.items() if bool(v)]
            exclude_keys = [k for k, v in projection.items() if not bool(v)]

            # Include mode (e.g. {"field": 1, "_id": 0})
            if include_keys:
                projected = {}
                for key in include_keys:
                    if key == "_id" and key in projection and projection[key] == 0:
                        continue
                    value = self._get_nested(document, key)
                    if value is not None:
                        self._set_nested(projected, key, value)
                return projected

            # Exclude mode (e.g. {"_id": 0})
            projected = copy.deepcopy(document)
            for key in exclude_keys:
                self._delete_nested(projected, key)
            return projected

        # Unknown projection format: return full doc safely.
        return document
    
    # ==========================================
    # User-Specific Operations
    # ==========================================
    
    def get_next_user_id(self):
        """Generate next user ID (Agri_1, Agri_2, ...) atomically."""
        # Use return_document=True to avoid race condition between update and find
        result = self.update_one(
            'counters',
            {'_id': 'user_id'},
            {'$inc': {'count': 1}},
            upsert=True,
            return_document=True
        )
        count = result.updated_document['count']
        return f"Agri_{count}"
    
    def create_user(self, firebase_uid, email, name=""):
        """Create new user profile"""
        user_id = self.get_next_user_id()
        
        user_doc = {
            'user_id': user_id,
            'firebase_uid': firebase_uid,
            'email': email,
            'name': name,
            'role': 'user',
            'profile': {
                'phone': '',
                'district': '',
                'state': '',
                'farm_size': '',
                'preferred_crops': []
            },
            'settings': {
                'language': 'mixed',
                'notifications': {
                    'weather_alerts': True,
                    'fertilizer_reminders': True,
                    'growth_alerts': True,
                    'market_alerts': True,
                    'news': True
                },
                'theme': 'light',
                'units': {
                    'temperature': 'celsius',
                    'weight': 'kg'
                }
            },
            'last_login': datetime.utcnow().isoformat()
        }
        
        self.insert_one('users', user_doc)
        return user_doc
    
    def get_user_by_firebase_uid(self, firebase_uid):
        """Get user by Firebase UID"""
        return self.find_one('users', {'firebase_uid': firebase_uid})
    
    def get_user_by_user_id(self, user_id):
        """Get user by user_id"""
        return self.find_one('users', {'user_id': user_id})
    
    def update_user(self, user_id, update_data):
        """Update user profile"""
        return self.update_one(
            'users',
            {'user_id': user_id},
            {'$set': update_data}
        )
    
    # ==========================================
    # Utility Methods
    # ==========================================
    
    def to_json(self, data):
        """Convert data to JSON-serializable format"""
        return json.loads(json.dumps(data, default=self._json_serializer))
    
    def clear_cache(self):
        """Clear in-memory cache"""
        self._cache.clear()
    
    def backup(self, backup_dir=None):
        """Create backup of all data"""
        if backup_dir is None:
            backup_dir = self.data_dir / 'backups'
        
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f"backup_{timestamp}.json"
        
        all_data = {}
        for file in self.data_dir.glob('*.json'):
            collection = file.stem
            all_data[collection] = self._read_file(collection)
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, indent=2, default=self._json_serializer)
        
        logger.info(f"Backup created: {backup_file}")
        return str(backup_file)


class CollectionWrapper:
    """
    MongoDB-compatible collection wrapper
    Provides find_one, insert_one, update_one, find methods on a collection
    """
    
    def __init__(self, storage_service, collection_name):
        self._storage = storage_service
        self._collection = collection_name
    
    def find_one(self, query=None, projection=None, **kwargs):
        """Find single document"""
        sort = kwargs.get('sort')
        if sort:
            # If sort provided with find_one, get all and take first
            results = self._storage.find(self._collection, query, projection, sort=sort, limit=1)
            return results[0] if results else None
        return self._storage.find_one(self._collection, query or {}, projection)
    
    def find(self, query=None, projection=None, **kwargs):
        """Find multiple documents - returns a cursor-like object"""
        return CollectionCursor(self._storage, self._collection, query, projection, kwargs)
    
    def insert_one(self, document):
        """Insert single document"""
        return self._storage.insert_one(self._collection, document)
    
    def update_one(self, query, update, upsert=False):
        """Update single document"""
        return self._storage.update_one(self._collection, query, update, upsert)

    def update_many(self, query, update, upsert=False):
        """Update multiple documents"""
        return self._storage.update_many(self._collection, query, update, upsert)
    
    def delete_one(self, query):
        """Delete single document"""
        return self._storage.delete_one(self._collection, query)

    def delete_many(self, query):
        """Delete multiple documents"""
        return self._storage.delete_many(self._collection, query)
    
    def count_documents(self, query=None):
        """Count documents matching query"""
        return self._storage.count_documents(self._collection, query)
    
    def aggregate(self, pipeline):
        """Basic aggregation support"""
        # Simple implementation - just return all matching documents
        # Production would need proper aggregation framework
        data = self._storage._read_file(self._collection)
        return data


class CollectionCursor:
    """
    MongoDB-compatible cursor for iteration and chaining
    """
    
    def __init__(self, storage, collection, query, projection, kwargs):
        self._storage = storage
        self._collection = collection
        self._query = query
        self._projection = projection
        self._sort = kwargs.get('sort')
        self._limit = kwargs.get('limit', 0)
        self._skip = kwargs.get('skip', 0)
        self._data = None
    
    def _execute(self):
        """Execute the query if not already done"""
        if self._data is None:
            self._data = self._storage.find(
                self._collection,
                self._query,
                self._projection,
                sort=self._sort,
                limit=self._limit
            )
            if self._skip > 0:
                self._data = self._data[self._skip:]
        return self._data
    
    def sort(self, key_or_list, direction=None):
        """Add sort to cursor"""
        if isinstance(key_or_list, str):
            self._sort = [(key_or_list, direction or 1)]
        else:
            self._sort = key_or_list
        self._data = None  # Reset to re-execute
        return self
    
    def limit(self, limit):
        """Add limit to cursor"""
        self._limit = limit
        self._data = None  # Reset to re-execute
        return self
    
    def skip(self, skip):
        """Add skip to cursor"""
        self._skip = skip
        self._data = None  # Reset to re-execute
        return self
    
    def __iter__(self):
        """Iterate over results"""
        return iter(self._execute())
    
    def __list__(self):
        """Convert to list"""
        return list(self._execute())
    
    def toArray(self):
        """Convert to array (MongoDB compatibility)"""
        return self._execute()


# Create singleton instance
db_service = LocalStorageService()
