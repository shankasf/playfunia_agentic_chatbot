import os
import requests
import json
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

load_dotenv()

class SupabaseClient:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_ANON_KEY")
        
        if not self.url or not self.key:
            print("⚠️ Warning: SUPABASE_URL or SUPABASE_ANON_KEY not found in environment variables")
        
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Any:
        """Make HTTP request to Supabase"""
        url = f"{self.url}/rest/v1/{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers)
            elif method == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            elif method == "PATCH":
                response = requests.patch(url, headers=self.headers, json=data)
            elif method == "DELETE":
                response = requests.delete(url, headers=self.headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if response.status_code == 401:
                print(f"❌ 401 Unauthorized: Check your SUPABASE_ANON_KEY")
                print(f"   Also ensure Row Level Security (RLS) policies allow access")
            
            response.raise_for_status()
            return response.json() if response.text else {}
        
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            raise
    
    def get_all(self, table: str, select: str = "*", filters: Optional[str] = None) -> List[Dict]:
        """Fetch all records from a table with optional filters"""
        endpoint = f"{table}?select={select}"
        if filters:
            endpoint += f"&{filters}"
        return self._make_request("GET", endpoint)
    
    def get_by_id(self, table: str, id_column: str, id_value: Any) -> Optional[Dict]:
        """Fetch a single record by ID"""
        endpoint = f"{table}?{id_column}=eq.{id_value}"
        result = self._make_request("GET", endpoint)
        return result[0] if result else None
    
    def search(self, table: str, column: str, value: str, select: str = "*") -> List[Dict]:
        """Search records with ILIKE (case-insensitive)"""
        endpoint = f"{table}?select={select}&{column}=ilike.*{value}*"
        return self._make_request("GET", endpoint)
    
    def insert(self, table: str, data: Dict) -> List[Dict]:
        """Insert a new record and return the inserted row"""
        return self._make_request("POST", table, data)
    
    def update(self, table: str, id_column: str, id_value: Any, data: Dict) -> List[Dict]:
        """Update a record by ID"""
        endpoint = f"{table}?{id_column}=eq.{id_value}"
        return self._make_request("PATCH", endpoint, data)
    
    def delete(self, table: str, id_column: str, id_value: Any) -> None:
        """Delete a record by ID"""
        endpoint = f"{table}?{id_column}=eq.{id_value}"
        self._make_request("DELETE", endpoint)
    
    def test_connection(self) -> bool:
        """Test if connection works"""
        try:
            response = requests.get(f"{self.url}/rest/v1/", headers=self.headers)
            return response.status_code == 200
        except:
            return False


# Initialize global client
db = SupabaseClient()
