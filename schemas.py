"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal

# Example schemas (you can keep these if useful):

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Membership schemas for Bebahan site

Tier = Literal["bronze", "silver", "gold"]

class Member(BaseModel):
    """Bebahan membership records. Collection name: "member"""
    email: EmailStr = Field(..., description="Member email address")
    tier: Tier = Field(..., description="Membership tier: bronze($4.99), silver($9.99), gold($24.99)")
    status: Literal["active", "incomplete", "canceled", "past_due"] = Field("incomplete")
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    username: Optional[str] = Field(None, description="Optional display name")
