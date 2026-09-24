from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class Product(BaseModel):
    id: int
    name: str
    description: str
    price: float
    category: str
    sku: str
    stock: int
    attributes: Dict[str, Any] = Field(default_factory=dict)
    specifications: Dict[str, Any] = Field(default_factory=dict)
    reviews_summary: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    stock: Optional[int] = None
    attributes: Optional[Dict[str, Any]] = None
    specifications: Optional[Dict[str, Any]] = None
    reviews_summary: Optional[str] = None

class LeaderboardItem(BaseModel):
    product_id: int
    views: int

class LeaderboardResponse(BaseModel):
    backend: str
    top_products: List[LeaderboardItem]

class SessionData(BaseModel):
    session_id: str
    user_id: str
    username: str = ""
    role: str = "customer"
    last_login: str = ""
    ip_address: str = "127.0.0.1"
    cart_count: int = 0
    preferences: Dict[str, Any] = Field(default_factory=dict)

class SessionUpdate(BaseModel):
    last_login: Optional[str] = None
    role: Optional[str] = None
    cart_count: Optional[int] = None
    preferences: Optional[Dict[str, Any]] = None
