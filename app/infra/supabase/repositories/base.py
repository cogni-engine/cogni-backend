"""Base repository with common CRUD operations"""
from typing import Generic, TypeVar, Type, Optional, List, Dict, Any
from pydantic import BaseModel
from supabase import Client

T = TypeVar('T', bound=BaseModel)
CreateT = TypeVar('CreateT', bound=BaseModel)
UpdateT = TypeVar('UpdateT', bound=BaseModel)


class BaseRepository(Generic[T, CreateT, UpdateT]):
    """
    Base repository providing common database operations.
    Hides Supabase implementation details from the rest of the application.
    """
    
    def __init__(self, client: Client, table_name: str, model_class: Type[T]):
        self._client = client
        self._table_name = table_name
        self._model_class = model_class
    
    def _to_model(self, data: Dict[str, Any]) -> T:
        """Convert database dict to domain model"""
        return self._model_class(**data)
    
    def _to_models(self, data: List[Dict[str, Any]]) -> List[T]:
        """Convert list of database dicts to domain models"""
        return [self._to_model(item) for item in data]
    
    async def find_by_id(self, id: int) -> Optional[T]:
        """Find a single record by ID"""
        response = self._client.table(self._table_name).select("*").eq("id", id).execute()
        
        if not response.data:
            return None
        
        return self._to_model(response.data[0])
    
    async def find_all(self, limit: Optional[int] = None, offset: int = 0) -> List[T]:
        """Find all records with optional pagination"""
        query = self._client.table(self._table_name).select("*")
        
        if limit:
            query = query.limit(limit)
        
        if offset:
            query = query.offset(offset)
        
        response = query.execute()
        return self._to_models(response.data)
    
    async def find_by_filters(self, filters: Dict[str, Any], limit: Optional[int] = None) -> List[T]:
        """Find records matching filters"""
        query = self._client.table(self._table_name).select("*")
        
        for key, value in filters.items():
            query = query.eq(key, value)
        
        if limit:
            query = query.limit(limit)
        
        response = query.execute()
        return self._to_models(response.data)
    
    async def create(self, data: CreateT) -> T:
        """Create a new record"""
        data_dict = data.model_dump(exclude_unset=True, mode='json')
        response = self._client.table(self._table_name).insert(data_dict).execute()
        
        if not response.data:
            raise ValueError("Failed to create record")
        
        return self._to_model(response.data[0])
    
    async def update(self, id: int, data: UpdateT) -> Optional[T]:
        """Update a record by ID"""
        data_dict = data.model_dump(exclude_unset=True, mode='json')
        
        if not data_dict:
            # No fields to update
            return await self.find_by_id(id)
        
        response = self._client.table(self._table_name).update(data_dict).eq("id", id).execute()
        
        if not response.data:
            return None
        
        return self._to_model(response.data[0])
    
    async def delete(self, id: int) -> bool:
        """Delete a record by ID"""
        response = self._client.table(self._table_name).delete().eq("id", id).execute()
        return len(response.data) > 0
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count records matching filters"""
        query = self._client.table(self._table_name).select("id", count="exact")
        
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)
        
        response = query.execute()
        return response.count or 0

