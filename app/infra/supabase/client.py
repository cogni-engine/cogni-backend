"""Supabase client singleton"""
import os
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client  # type: ignore

load_dotenv(dotenv_path=".env")

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Get or create Supabase client singleton"""
    global _supabase_client
    
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        
        _supabase_client = create_client(url, key)
    
    return _supabase_client


def reset_supabase_client():
    """Reset the Supabase client singleton (useful for testing)"""
    global _supabase_client
    _supabase_client = None

