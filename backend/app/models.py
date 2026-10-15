"""Phase 2 relational schema for ACE Canteen."""
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Index, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum

def utcnow():
    return datetime.now(timezone.utc)

class UserRole(str, enum.Enum):
    STUDENT = "student"
    STAFF = "staff"
    ADMIN = "admin"

class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="!not-set!")
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False), default=UserRole.STUDENT, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    orders: Mapped[list["Order"]] = relationship(back_populates="user")

class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (CheckConstraint("item_type IN ('food', 'stationery')", name="ck_categories_item_type"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(90), unique=True, nullable=False)
    item_type: Mapped[str] = mapped_column(String(20), default="food", nullable=False)  # food or stationery
    description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    products: Mapped[list["Product"]] = relationship(back_populates="category")

class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_category_active", "category_id", "is_available"),
        CheckConstraint("price > 0", name="ck_products_price_positive"),
        CheckConstraint("stock_quantity >= 0", name="ck_products_stock_nonnegative"),
        CheckConstraint("item_type IN ('food', 'stationery')", name="ck_products_item_type"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    item_type: Mapped[str] = mapped_column(String(20), default="food", nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500))
    dietary_info: Mapped[str | None] = mapped_column(String(255))
    allergens: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    category: Mapped[Category] = relationship(back_populates="products")
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product")

    @property
    def category_name(self) -> str | None:
        return self.category.name if self.category else None

class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("token_number", "token_date", name="uq_order_daily_token"), Index("ix_orders_status_created", "status", "created_at"), CheckConstraint("subtotal >= 0", name="ck_orders_subtotal_nonnegative"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    token_number: Mapped[int | None] = mapped_column(Integer)
    token_date: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, native_enum=False), default=OrderStatus.PENDING, nullable=False)
    payment_status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, native_enum=False), default=PaymentStatus.PENDING, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    gateway_order_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    gateway_payment_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    payment_signature: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    user: Mapped[User] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"), CheckConstraint("unit_price > 0", name="ck_order_items_unit_price_positive"), CheckConstraint("line_total >= 0", name="ck_order_items_line_total_nonnegative"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(120), nullable=False)  # historical snapshot
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="order_items")


class InventoryMovementType(str, enum.Enum):
    INITIAL = "initial"
    RECEIPT = "receipt"
    ADJUSTMENT = "adjustment"
    WASTE = "waste"
    RESERVATION = "reservation"
    RELEASE = "release"

class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint("quantity_delta != 0", name="ck_inventory_movement_nonzero_delta"),
        CheckConstraint("quantity_before >= 0", name="ck_inventory_movement_before_nonnegative"),
        CheckConstraint("quantity_after >= 0", name="ck_inventory_movement_after_nonnegative"),
        Index("ix_inventory_movements_product_created", "product_id", "created_at"),
        Index("ix_inventory_movements_created", "created_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    movement_type: Mapped[InventoryMovementType] = mapped_column(Enum(InventoryMovementType, native_enum=False), nullable=False)
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_before: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    product: Mapped[Product] = relationship()
    actor: Mapped[User | None] = relationship()
    order: Mapped[Order | None] = relationship()


class AuditEvent(Base):
    """Append-only record of privileged operational changes and important events."""
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_created", "created_at"), Index("ix_audit_events_actor_created", "actor_user_id", "created_at"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80))
    details_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    actor: Mapped[User | None] = relationship()


class Notification(Base):
    """Durable, per-user in-app notification with explicit read state."""
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_user_read", "user_id", "is_read"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(40), nullable=False, default="general")
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Favorite(Base):
    """Student's saved catalogue items; one row per student/product."""
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_favorites_user_product"), Index("ix_favorites_user_created", "user_id", "created_at"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    product: Mapped[Product] = relationship()


class OrderReview(Base):
    """Verified student feedback; one review per completed paid order."""
    __tablename__ = "order_reviews"
    __table_args__ = (UniqueConstraint("order_id", name="uq_order_reviews_order"), CheckConstraint("rating >= 1 AND rating <= 5", name="ck_order_reviews_rating_range"), Index("ix_order_reviews_created", "created_at"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    order: Mapped[Order] = relationship()
    user: Mapped[User] = relationship()


class PaymentWebhookEvent(Base):
    """Durable idempotency ledger for payment-provider webhook deliveries."""
    __tablename__ = "payment_webhook_events"
    __table_args__ = (Index("ix_payment_webhook_events_received", "received_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    event_name: Mapped[str] = mapped_column(String(100), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

class Supplier(Base):
    """Canteen supplier contact record."""
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

class ProductBatch(Base):
    """Received stock batch with optional expiry date and supplier traceability."""
    __tablename__ = "product_batches"
    __table_args__ = (CheckConstraint("quantity_received > 0", name="ck_batch_received_positive"), CheckConstraint("quantity_remaining >= 0", name="ck_batch_remaining_nonnegative"), Index("ix_product_batches_expiry", "expiry_date"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    batch_code: Mapped[str] = mapped_column(String(80), nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    received_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String(255))
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    product: Mapped[Product] = relationship()
    supplier: Mapped[Supplier | None] = relationship()


class BatchReservation(Base):
    """Tracks which received stock batches were consumed by a checkout reservation.

    Rows are retained after fulfillment for traceability; a released reservation is
    marked with released_at so webhook retries cannot restore it twice.
    """
    __tablename__ = "batch_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_batch_reservation_quantity_positive"),
        Index("ix_batch_reservations_order", "order_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    batch_id: Mapped[int] = mapped_column(ForeignKey("product_batches.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
