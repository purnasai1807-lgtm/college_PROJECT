from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    item_type: str
    description: str | None = None
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

class ProductOut(BaseModel):
    id: int
    category_id: int
    name: str
    description: str | None = None
    item_type: str
    price: Decimal
    stock_quantity: int
    low_stock_threshold: int = 5
    is_archived: bool = False
    is_available: bool
    image_url: str | None = None
    dietary_info: str | None = None
    allergens: str | None = None
    category_name: str | None = None
    model_config = ConfigDict(from_attributes=True)

class ProductCreate(BaseModel):
    category_id: int
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    item_type: str = Field(default="food", pattern="^(food|stationery)$")
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    stock_quantity: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=5, ge=0, le=100000)
    is_available: bool = True
    image_url: str | None = Field(default=None, max_length=500)
    dietary_info: str | None = Field(default=None, max_length=255)
    allergens: str | None = Field(default=None, max_length=255)

from datetime import datetime
from pydantic import EmailStr
from app.models import UserRole

class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class UserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    must_change_password: bool = False
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut

class RoleUpdateIn(BaseModel):
    role: UserRole

class AdminUserCreateIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    role: UserRole = UserRole.STAFF
    temporary_password: str = Field(min_length=12, max_length=128)

class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    slug: str = Field(min_length=2, max_length=90, pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$")
    item_type: str = Field(pattern="^(food|stationery)$")
    description: str | None = Field(default=None, max_length=255)


class ProductUpdate(BaseModel):
    category_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    item_type: str | None = Field(default=None, pattern="^(food|stationery)$")
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    stock_quantity: int | None = Field(default=None, ge=0)
    low_stock_threshold: int | None = Field(default=None, ge=0, le=100000)
    is_available: bool | None = None
    image_url: str | None = Field(default=None, max_length=500)
    dietary_info: str | None = Field(default=None, max_length=255)
    allergens: str | None = Field(default=None, max_length=255)

class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    slug: str | None = Field(default=None, min_length=2, max_length=90, pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class ForgotPasswordIn(BaseModel):
    email: EmailStr

class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=20, max_length=600)
    new_password: str = Field(min_length=12, max_length=128)

class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class OrderItemIn(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=50)

class OrderCreateIn(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1, max_length=30)
    notes: str | None = Field(default=None, max_length=500)

class OrderStatusIn(BaseModel):
    status: str = Field(pattern="^(confirmed|preparing|ready|completed|cancelled)$")

class OrderItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    model_config = ConfigDict(from_attributes=True)

class OrderOut(BaseModel):
    id: int
    user_id: int
    token_number: int | None
    token_date: str | None
    status: str
    payment_status: str
    subtotal: Decimal
    notes: str | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut]
    model_config = ConfigDict(from_attributes=True)


class OrderItemIn(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=50)

class OrderCreateIn(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1, max_length=30)
    notes: str | None = Field(default=None, max_length=500)

class OrderStatusIn(BaseModel):
    status: str = Field(pattern="^(confirmed|preparing|ready|completed|cancelled)$")

class OrderItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    model_config = ConfigDict(from_attributes=True)

class OrderOut(BaseModel):
    id: int
    user_id: int
    token_number: int | None
    token_date: str | None
    status: str
    payment_status: str
    subtotal: Decimal
    notes: str | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut]
    model_config = ConfigDict(from_attributes=True)


class StockAdjustmentIn(BaseModel):
    product_id: int = Field(gt=0)
    movement_type: str = Field(pattern="^(receipt|adjustment|waste)$")
    quantity: int = Field(gt=0, le=100000)
    reason: str = Field(min_length=3, max_length=255)

class InventoryMovementOut(BaseModel):
    id: int
    product_id: int
    actor_user_id: int | None
    order_id: int | None
    movement_type: str
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    reason: str
    created_at: datetime
    product_name: str
    actor_name: str | None = None

class StockThresholdUpdate(BaseModel):
    low_stock_threshold: int = Field(ge=0, le=100000)
