"""ACE Canteen API: Phase 1 foundation + Phase 2 persistence."""
from contextlib import asynccontextmanager
import csv
import io
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging
import hashlib
import hmac
import json
import time
import uuid
from collections import defaultdict, deque
from threading import Lock
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Header
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text, func, or_, cast, String
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app import models  # noqa: F401 - registers ORM models with Base.metadata
from app.models import Category, Product, User, UserRole, Order, OrderItem, OrderStatus, PaymentStatus, InventoryMovement, InventoryMovementType, AuditEvent, Notification, Favorite, OrderReview, PaymentWebhookEvent
from app.schemas import CategoryOut, ProductOut, ProductCreate, RegisterIn, LoginIn, UserOut, TokenOut, RoleUpdateIn, CategoryCreate, ProductUpdate, CategoryUpdate, ChangePasswordIn, OrderCreateIn, OrderOut, OrderStatusIn, StockAdjustmentIn, StockThresholdUpdate
from app.security import hash_password, verify_password, create_access_token, get_current_user, require_roles
from app.seed import seed_demo_data

PROJECT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_DIR / "frontend"
settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ace_canteen")

# Per-process login throttling. For multi-worker/public deployments, replace this
# in-memory store with a shared Redis-backed limiter.
_LOGIN_LIMIT = 5
_LOGIN_WINDOW_SECONDS = 15 * 60
_login_attempts: dict[str, deque[float]] = defaultdict(deque)
_login_attempts_lock = Lock()

# Low-cardinality process metrics. These are deliberately aggregate-only: no
# URLs, query strings, user IDs, email addresses, or request bodies are recorded.
_metrics_lock = Lock()
_metrics = {"requests_total": 0, "requests_4xx_total": 0, "requests_5xx_total": 0,
            "request_duration_ms_sum": 0.0, "request_duration_ms_max": 0.0}



def _record_stock_movement(db: Session, product: Product, delta: int, movement_type: InventoryMovementType, reason: str, actor_user_id: int | None = None, order_id: int | None = None, before: int | None = None) -> None:
    """Add an immutable audit record for a committed inventory quantity change."""
    old_quantity = product.stock_quantity if before is None else before
    new_quantity = old_quantity + delta
    if delta == 0:
        return
    if new_quantity < 0:
        raise HTTPException(status_code=409, detail="Inventory quantity cannot become negative")
    db.add(InventoryMovement(product_id=product.id, actor_user_id=actor_user_id, order_id=order_id, movement_type=movement_type, quantity_delta=delta, quantity_before=old_quantity, quantity_after=new_quantity, reason=reason[:255]))
    # Notify managers when a stock movement crosses into low-stock territory.
    if new_quantity <= product.low_stock_threshold and old_quantity > product.low_stock_threshold:
        _notify_canteen_managers(db, "low_stock", "Low stock alert", f"{product.name}: {new_quantity} unit(s) remain (alert threshold {product.low_stock_threshold}).", "product", product.id)

def _record_audit(db: Session, action: str, entity_type: str, entity_id: int | str | None, actor_user_id: int | None = None, details: dict[str, Any] | None = None) -> None:
    """Stage a durable audit event in the same transaction as the business change."""
    db.add(AuditEvent(actor_user_id=actor_user_id, action=action[:80], entity_type=entity_type[:80], entity_id=str(entity_id) if entity_id is not None else None, details_json=json.dumps(details or {}, separators=(",", ":"), sort_keys=True, default=str)))

def _create_notification(db: Session, user_id: int, notification_type: str, title: str, message: str, entity_type: str | None = None, entity_id: int | str | None = None) -> None:
    """Stage a durable in-app notification in the current business transaction."""
    db.add(Notification(user_id=user_id, notification_type=notification_type[:40], title=title[:120], message=message[:500], entity_type=entity_type[:40] if entity_type else None, entity_id=str(entity_id)[:80] if entity_id is not None else None))

def _notify_canteen_managers(db: Session, notification_type: str, title: str, message: str, entity_type: str | None = None, entity_id: int | str | None = None) -> None:
    managers = db.scalars(select(User).where(User.is_active.is_(True), User.role.in_([UserRole.STAFF, UserRole.ADMIN]))).all()
    for manager in managers:
        _create_notification(db, manager.id, notification_type, title, message, entity_type, entity_id)

def _login_rate_key(request: Request, email: str) -> str:
    client_ip = request.client.host if request.client else "unknown"
    return f"{client_ip}:{email.strip().lower()}"

def _prune_login_attempts(now: float) -> None:
    """Remove expired keys so arbitrary login identifiers cannot grow memory forever."""
    expired = []
    for key, attempts in _login_attempts.items():
        while attempts and now - attempts[0] >= _LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        if not attempts:
            expired.append(key)
    for key in expired:
        _login_attempts.pop(key, None)

def _check_login_rate(key: str) -> int:
    now = time.monotonic()
    with _login_attempts_lock:
        # Prune periodically, not on every request, to keep normal login checks cheap.
        if len(_login_attempts) > 1024:
            _prune_login_attempts(now)
        attempts = _login_attempts.get(key)
        if attempts is None:
            return 0
        while attempts and now - attempts[0] >= _LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        if not attempts:
            _login_attempts.pop(key, None)
            return 0
        if len(attempts) >= _LOGIN_LIMIT:
            return max(1, int(_LOGIN_WINDOW_SECONDS - (now - attempts[0])))
    return 0

def _record_failed_login(key: str) -> None:
    now = time.monotonic()
    with _login_attempts_lock:
        if len(_login_attempts) > 1024:
            _prune_login_attempts(now)
        attempts = _login_attempts[key]
        while attempts and now - attempts[0] >= _LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        attempts.append(now)

def _clear_login_failures(key: str) -> None:
    with _login_attempts_lock:
        _login_attempts.pop(key, None)

@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting %s in %s mode", settings.app_name, settings.environment)
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            seed_demo_data(db)
    yield
    logger.info("Stopping %s", settings.app_name)

IS_PRODUCTION = settings.environment.lower() in {"production", "prod"}
MAX_REQUEST_BODY_BYTES = 1_048_576  # 1 MiB; catalogue and checkout requests are small JSON payloads.
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="ACE Canteen: student accounts, food/stationery catalogue, verified Razorpay payments, daily pickup tokens, queue overview and order lifecycle.",
    lifespan=lifespan,
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets", check_dir=False), name="assets")

@app.middleware("http")
async def security_and_request_logging(request: Request, call_next):
    # Accept only a simple caller-supplied request ID; otherwise create one. This
    # avoids log injection while making requests traceable across a reverse proxy.
    supplied_id = request.headers.get("x-request-id", "")
    if supplied_id and len(supplied_id) <= 64 and all(ch.isalnum() or ch in "-_" for ch in supplied_id):
        request_id = supplied_id
    else:
        request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()

    # Reject oversized declared bodies before parsing them. Reverse proxies should
    # enforce the same or a stricter limit for chunked requests.
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BODY_BYTES:
                response = JSONResponse(status_code=413, content={"error": {"code": "REQUEST_TOO_LARGE", "message": "Request body exceeds the 1 MiB limit."}})
                response.headers["X-Request-ID"] = request_id
                return _apply_security_headers(response, request)
        except ValueError:
            response = JSONResponse(status_code=400, content={"error": {"code": "INVALID_CONTENT_LENGTH", "message": "Invalid Content-Length header."}})
            response.headers["X-Request-ID"] = request_id
            return _apply_security_headers(response, request)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        with _metrics_lock:
            _metrics["requests_total"] += 1
            if 400 <= response.status_code < 500:
                _metrics["requests_4xx_total"] += 1
            elif response.status_code >= 500:
                _metrics["requests_5xx_total"] += 1
            _metrics["request_duration_ms_sum"] += duration_ms
            _metrics["request_duration_ms_max"] = max(_metrics["request_duration_ms_max"], duration_ms)
        logger.info("request_id=%s method=%s path=%s status=%s duration_ms=%s", request_id, request.method, request.url.path, response.status_code, duration_ms)
        return _apply_security_headers(response, request)
    except Exception:
        with _metrics_lock:
            _metrics["requests_total"] += 1
            _metrics["requests_5xx_total"] += 1
        logger.exception("request_id=%s unhandled error handling %s %s", request_id, request.method, request.url.path)
        raise

def _apply_security_headers(response: JSONResponse, request: Request):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self' https://api.razorpay.com; script-src 'self' https://checkout.razorpay.com; style-src 'self'; img-src 'self' data: https:; connect-src 'self' https://api.razorpay.com https://checkout.razorpay.com; frame-src https://checkout.razorpay.com")
    if IS_PRODUCTION and request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "The request contains invalid data.", "details": jsonable_encoder(exc.errors())}})

@app.exception_handler(Exception)
async def unexpected_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unexpected application error")
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred."}})

@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/manifest.webmanifest", include_in_schema=False)
async def web_app_manifest() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "manifest.webmanifest", media_type="application/manifest+json")

@app.get("/sw.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    # Serve from the origin root so the worker can control the entire app shell.
    return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

@app.get("/api/health", tags=["system"])
async def health() -> dict[str, Any]:
    return {"status": "ok", "application": settings.app_name, "version": settings.app_version, "environment": settings.environment}

@app.get("/api/ready", tags=["system"])
async def readiness(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
        return JSONResponse(status_code=200, content={"status": "ready", "checks": {"database": "ok"}})
    except SQLAlchemyError:
        logger.exception("Database readiness check failed")
        return JSONResponse(status_code=503, content={"status": "not_ready", "checks": {"database": "failed"}})

@app.get("/api/metrics", tags=["system"], include_in_schema=False)
async def metrics(request: Request) -> JSONResponse:
    """Aggregate process metrics for local monitoring and protected scrapers."""
    if IS_PRODUCTION:
        token = __import__("os").environ.get("METRICS_TOKEN", "")
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {token}" if token else ""
        if not expected or not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=404, detail="Not found")
    with _metrics_lock:
        snapshot = dict(_metrics)
    return JSONResponse(content={"application": settings.app_name, "version": settings.app_version,
        "uptime_metrics_scope": "current_process", "metrics": snapshot}, headers={"Cache-Control": "no-store"})

@app.get("/api/info", tags=["system"])
async def info() -> dict[str, str]:
    return {"name": settings.app_name, "version": settings.app_version, "phase": "1-16 database foundation, accounts, catalogue, payments, orders, inventory, reporting and notifications; Phases 17-24 feedback, payment idempotency, CI, PWA, backup recovery, operations monitoring and deployment hardening; Phase 25 aggregate operational metrics and request tracing", "backend": "Python / FastAPI", "frontend": "HTML / CSS / JavaScript", "database": "SQLAlchemy; SQLite by default, PostgreSQL supported"}

@app.get("/api/categories", response_model=list[CategoryOut], tags=["catalogue"])
def list_categories(item_type: str | None = Query(default=None, pattern="^(food|stationery)$"), db: Session = Depends(get_db)):
    stmt = select(Category).where(Category.is_active.is_(True)).order_by(Category.name)
    if item_type:
        stmt = stmt.where(Category.item_type == item_type)
    return db.scalars(stmt).all()

@app.get("/api/products", response_model=list[ProductOut], tags=["catalogue"])
def list_products(item_type: str | None = Query(default=None, pattern="^(food|stationery)$"), category_id: int | None = Query(default=None, gt=0), search: str | None = Query(default=None, min_length=1, max_length=100), available_only: bool = True, sort_by: str = Query(default="name", pattern="^(name|price|stock)$"), sort_order: str = Query(default="asc", pattern="^(asc|desc)$"), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    stmt = select(Product).join(Product.category).where(Category.is_active.is_(True)).options(joinedload(Product.category))
    if item_type:
        stmt = stmt.where(Product.item_type == item_type)
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where((Product.name.ilike(term)) | (Product.description.ilike(term)) | (Category.name.ilike(term)))
    if not available_only:
        raise HTTPException(status_code=403, detail="Unavailable products are only visible to catalogue staff")
    stmt = stmt.where(Product.is_available.is_(True), Product.stock_quantity > 0)
    sort_column = {"name": Product.name, "price": Product.price, "stock": Product.stock_quantity}[sort_by]
    stmt = stmt.order_by(sort_column.desc() if sort_order == "desc" else sort_column.asc(), Product.id.asc()).offset(offset).limit(limit)
    return db.scalars(stmt).all()

@app.get("/api/products/{product_id}", response_model=ProductOut, tags=["catalogue"])
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.scalar(select(Product).join(Product.category).options(joinedload(Product.category)).where(
        Product.id == product_id, Product.is_available.is_(True), Product.stock_quantity > 0, Category.is_active.is_(True)
    ))
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found or unavailable")
    return product

@app.get("/api/catalogue/summary", tags=["catalogue"])
def catalogue_summary(db: Session = Depends(get_db)):
    products = db.scalars(select(Product).join(Product.category).where(Category.is_active.is_(True), Product.is_available.is_(True))).all()
    return {"total_products": len(products), "food_items": sum(p.item_type == "food" for p in products), "stationery_items": sum(p.item_type == "stationery" for p in products), "in_stock": sum(p.stock_quantity > 0 for p in products)}


# Phase 3: authentication and role-based access control. Public registration can only
# create student accounts; privileged roles are assigned by an existing admin.
@app.post("/api/auth/register", response_model=UserOut, status_code=201, tags=["authentication"])
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    full_name = payload.full_name.strip()
    if len(full_name) < 2:
        raise HTTPException(status_code=422, detail="Full name must contain at least two non-space characters")
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(full_name=full_name, email=email, password_hash=hash_password(payload.password), role=UserRole.STUDENT, is_active=True)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create account; check whether the email is already registered")
    return user

@app.post("/api/auth/login", response_model=TokenOut, tags=["authentication"])
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    rate_key = _login_rate_key(request, payload.email)
    retry_after = _check_login_rate(rate_key)
    if retry_after:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.", headers={"Retry-After": str(retry_after)})
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        _record_failed_login(rate_key)
        raise HTTPException(status_code=401, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        _record_failed_login(rate_key)
        raise HTTPException(status_code=403, detail="This account has been disabled")
    _clear_login_failures(rate_key)
    return {"access_token": create_access_token(user), "token_type": "bearer", "expires_in": settings.access_token_minutes * 60, "user": user}

@app.get("/api/auth/me", response_model=UserOut, tags=["authentication"])
def me(user: User = Depends(get_current_user)):
    return user

@app.get("/api/notifications", tags=["notifications"], summary="List current user's in-app notifications")
def list_notifications(limit: int = Query(default=50, ge=1, le=100), unread_only: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    rows = db.scalars(query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)).all()
    unread_count = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id, Notification.is_read.is_(False))) or 0
    return {"items": [{"id": n.id, "type": n.notification_type, "title": n.title, "message": n.message, "entity_type": n.entity_type, "entity_id": n.entity_id, "is_read": n.is_read, "created_at": n.created_at, "read_at": n.read_at} for n in rows], "unread_count": unread_count}

@app.patch("/api/notifications/{notification_id}/read", tags=["notifications"], summary="Mark an owned notification as read")
def mark_notification_read(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    notification = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id))
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now().astimezone()
        db.commit()
    return {"id": notification.id, "is_read": notification.is_read}

@app.post("/api/notifications/read-all", tags=["notifications"], summary="Mark all current user's notifications as read")
def mark_all_notifications_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.now().astimezone()
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))).all()
    for notification in rows:
        notification.is_read = True
        notification.read_at = now
    db.commit()
    return {"marked_read": len(rows)}

@app.post("/api/auth/change-password", tags=["authentication"])
def change_password(payload: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from the current password")
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1
    db.commit()
    return {"message": "Password changed. All existing sessions have been signed out; sign in again."}

@app.get("/api/admin/users", response_model=list[UserOut], tags=["administration"])
def list_users(_: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.created_at.desc())).all()

@app.patch("/api/admin/users/{user_id}/role", response_model=UserOut, tags=["administration"])
def update_user_role(user_id: int, payload: RoleUpdateIn, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and payload.role != UserRole.ADMIN:
        raise HTTPException(status_code=400, detail="You cannot remove your own admin role")
    old_role = user.role.value
    user.role = payload.role
    _record_audit(db, "user.role_changed", "user", user.id, admin.id, {"old_role": old_role, "new_role": payload.role.value})
    db.commit()
    db.refresh(user)
    return user

@app.patch("/api/admin/users/{user_id}/active", response_model=UserOut, tags=["administration"])
def set_user_active(user_id: int, active: bool = Query(...), admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and not active:
        raise HTTPException(status_code=400, detail="You cannot disable your own admin account")
    old_active = user.is_active
    user.is_active = active
    _record_audit(db, "user.activation_changed", "user", user.id, admin.id, {"old_active": old_active, "new_active": active})
    db.commit()
    db.refresh(user)
    return user

@app.get("/api/admin/categories", response_model=list[CategoryOut], tags=["catalogue administration"])
def list_all_categories(_: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return db.scalars(select(Category).order_by(Category.item_type, Category.name)).all()

@app.post("/api/admin/categories", response_model=CategoryOut, status_code=201, tags=["catalogue administration"])
def create_category(payload: CategoryCreate, _: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    name = payload.name.strip()
    slug = payload.slug.strip().lower()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Category name must contain at least two non-space characters")
    if db.scalar(select(Category).where((Category.name.ilike(name)) | (Category.slug == slug))):
        raise HTTPException(status_code=409, detail="Category name or slug already exists")
    category = Category(name=name, slug=slug, item_type=payload.item_type, description=payload.description.strip() if payload.description else None, is_active=True)
    db.add(category)
    try:
        db.flush()
        _record_audit(db, "category.created", "category", category.id, _.id, {"name": category.name, "item_type": category.item_type})
        db.commit()
        db.refresh(category)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category name or slug already exists")
    return category

@app.get("/api/admin/products", response_model=list[ProductOut], tags=["catalogue administration"])
def list_managed_products(_: User = Depends(require_roles("admin", "staff")), db: Session = Depends(get_db)):
    """Return available and archived products to authorized catalogue managers only."""
    stmt = select(Product).join(Product.category).options(joinedload(Product.category)).order_by(Product.item_type, Product.name)
    return db.scalars(stmt).all()

@app.post("/api/admin/products", response_model=ProductOut, status_code=201, tags=["catalogue administration"])
def create_product(payload: ProductCreate, _: User = Depends(require_roles("admin", "staff")), db: Session = Depends(get_db)):
    category = db.get(Category, payload.category_id)
    if category is None or not category.is_active:
        raise HTTPException(status_code=400, detail="A valid active category is required")
    if category.item_type != payload.item_type:
        raise HTTPException(status_code=400, detail="Product type must match its category type")
    values = payload.model_dump()
    values["name"] = values["name"].strip()
    if len(values["name"]) < 2:
        raise HTTPException(status_code=422, detail="Product name must contain at least two non-space characters")
    for key in ("description", "image_url", "dietary_info", "allergens"):
        if isinstance(values.get(key), str):
            values[key] = values[key].strip() or None
    if values.get("image_url") and not values["image_url"].startswith(("https://", "http://", "/assets/")):
        raise HTTPException(status_code=422, detail="Image URL must be HTTP(S) or a local /assets/ path")
    product = Product(**values)
    db.add(product)
    try:
        db.flush()
        _record_audit(db, "product.created", "product", product.id, _.id, {"name": product.name, "item_type": product.item_type, "price": str(product.price), "opening_stock": product.stock_quantity})
        if product.stock_quantity > 0:
            _record_stock_movement(db, product, product.stock_quantity, InventoryMovementType.INITIAL, "Initial stock on product creation", before=0)
        db.commit()
        db.refresh(product)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not save product; verify the category and values")
    return product

@app.patch("/api/admin/products/{product_id}", response_model=ProductOut, tags=["catalogue administration"])
def update_product(product_id: int, payload: ProductUpdate, _: User = Depends(require_roles("admin", "staff")), db: Session = Depends(get_db)):
    product = db.scalar(select(Product).options(joinedload(Product.category)).where(Product.id == product_id))
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    values = payload.model_dump(exclude_unset=True)
    non_nullable_fields = {"category_id", "name", "item_type", "price", "stock_quantity", "is_available"}
    if any(key in values and values[key] is None for key in non_nullable_fields):
        raise HTTPException(status_code=422, detail="Required product fields cannot be null")
    category_id = values.get("category_id", product.category_id)
    item_type = values.get("item_type", product.item_type)
    category = db.get(Category, category_id)
    if category is None or not category.is_active:
        raise HTTPException(status_code=400, detail="A valid active category is required")
    if category.item_type != item_type:
        raise HTTPException(status_code=400, detail="Product type must match its category type")
    if "name" in values and values["name"] is not None:
        values["name"] = values["name"].strip()
        if len(values["name"]) < 2:
            raise HTTPException(status_code=422, detail="Product name must contain at least two non-space characters")
    if values.get("image_url") and not values["image_url"].startswith(("https://", "http://", "/assets/")):
        raise HTTPException(status_code=422, detail="Image URL must be HTTP(S) or a local /assets/ path")
    old_stock = product.stock_quantity
    for key, value in values.items():
        setattr(product, key, value.strip() or None if isinstance(value, str) and key in {"description", "image_url", "dietary_info", "allergens"} else value)
    if values.get("is_available") is True:
        product.is_archived = False
    if product.stock_quantity != old_stock:
        _record_stock_movement(db, product, product.stock_quantity - old_stock, InventoryMovementType.ADJUSTMENT, "Stock changed from catalogue editor", actor_user_id=_.id, before=old_stock)
    _record_audit(db, "product.updated", "product", product.id, _.id, {"changed_fields": sorted(values.keys())})
    try:
        db.commit()
        db.refresh(product)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not update product; verify category and values")
    return product

@app.delete("/api/admin/products/{product_id}", response_model=ProductOut, tags=["catalogue administration"])
def archive_product(product_id: int, _: User = Depends(require_roles("admin", "staff")), db: Session = Depends(get_db)):
    product = db.scalar(select(Product).options(joinedload(Product.category)).where(Product.id == product_id))
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    # Archive instead of hard-delete so future order history can retain product references.
    product.is_available = False
    product.is_archived = True
    old_stock = product.stock_quantity
    product.stock_quantity = 0
    if old_stock > 0:
        _record_stock_movement(db, product, -old_stock, InventoryMovementType.ADJUSTMENT, "Stock removed when product archived", actor_user_id=_.id, before=old_stock)
    _record_audit(db, "product.archived", "product", product.id, _.id, {"name": product.name, "stock_removed": old_stock})
    db.commit()
    db.refresh(product)
    return product

@app.patch("/api/admin/categories/{category_id}", response_model=CategoryOut, tags=["catalogue administration"])
def update_category(category_id: int, payload: CategoryUpdate, _: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    values = payload.model_dump(exclude_unset=True)
    if any(key in values and values[key] is None for key in {"name", "slug", "is_active"}):
        raise HTTPException(status_code=422, detail="Category name, slug and active status cannot be null")
    if "name" in values and values["name"] is not None:
        values["name"] = values["name"].strip()
        if len(values["name"]) < 2:
            raise HTTPException(status_code=422, detail="Category name must contain at least two non-space characters")
    if "slug" in values and values["slug"] is not None:
        values["slug"] = values["slug"].strip().lower()
    if values.get("name") and db.scalar(select(Category).where(Category.id != category_id, Category.name.ilike(values["name"]))):
        raise HTTPException(status_code=409, detail="Category name already exists")
    if values.get("slug") and db.scalar(select(Category).where(Category.id != category_id, Category.slug == values["slug"])):
        raise HTTPException(status_code=409, detail="Category slug already exists")
    for key, value in values.items():
        setattr(category, key, value.strip() if isinstance(value, str) and key == "description" else value)
    _record_audit(db, "category.updated", "category", category.id, _.id, {"changed_fields": sorted(values.keys())})
    try:
        db.commit()
        db.refresh(category)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category update conflicts with existing data")
    return category

@app.get("/api/admin/inventory/summary", tags=["inventory"], summary="Inventory totals and low-stock alerts")
def inventory_summary(_: User = Depends(require_roles("admin", "staff")), db: Session = Depends(get_db)):
    products = db.scalars(select(Product).join(Product.category).options(joinedload(Product.category)).where(Product.is_archived.is_(False), Category.is_active.is_(True)).order_by(Product.name)).all()
    low = [p for p in products if p.stock_quantity <= p.low_stock_threshold]
    out_of_stock = [p for p in products if p.stock_quantity == 0]
    return {"tracked_products": len(products), "low_stock_count": len(low), "out_of_stock_count": len(out_of_stock), "total_units": sum(p.stock_quantity for p in products), "low_stock_items": [{"product_id": p.id, "name": p.name, "item_type": p.item_type, "category_name": p.category.name if p.category else None, "stock_quantity": p.stock_quantity, "low_stock_threshold": p.low_stock_threshold, "is_out_of_stock": p.stock_quantity == 0} for p in low]}

@app.get("/api/admin/inventory/movements", tags=["inventory"], summary="Search the inventory audit ledger")
def inventory_movements(product_id: int | None = Query(default=None, gt=0), movement_type: str | None = Query(default=None, pattern="^(initial|receipt|adjustment|waste|reservation|release)$"), limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0), _: User = Depends(require_roles("admin", "staff")), db: Session = Depends(get_db)):
    stmt = select(InventoryMovement).options(joinedload(InventoryMovement.product), joinedload(InventoryMovement.actor)).order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc())
    if product_id is not None: stmt = stmt.where(InventoryMovement.product_id == product_id)
    if movement_type is not None: stmt = stmt.where(InventoryMovement.movement_type == InventoryMovementType(movement_type))
    rows = db.scalars(stmt.offset(offset).limit(limit)).unique().all()
    return [{"id": m.id, "product_id": m.product_id, "actor_user_id": m.actor_user_id, "order_id": m.order_id, "movement_type": m.movement_type.value, "quantity_delta": m.quantity_delta, "quantity_before": m.quantity_before, "quantity_after": m.quantity_after, "reason": m.reason, "created_at": m.created_at, "product_name": m.product.name if m.product else f"Product #{m.product_id}", "actor_name": m.actor.full_name if m.actor else None} for m in rows]

@app.post("/api/admin/inventory/adjustments", status_code=201, tags=["inventory"], summary="Receive, adjust or write off inventory")
def adjust_inventory(payload: StockAdjustmentIn, staff: User = Depends(require_roles("admin", "staff")), db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.id == payload.product_id).with_for_update())
    if product is None: raise HTTPException(status_code=404, detail="Product not found")
    before = product.stock_quantity
    if payload.movement_type == "receipt":
        after = before + payload.quantity
        movement = InventoryMovementType.RECEIPT
    elif payload.movement_type == "waste":
        after = before - payload.quantity
        movement = InventoryMovementType.WASTE
        if after < 0: raise HTTPException(status_code=409, detail="Write-off quantity exceeds current stock")
    else:
        after = payload.quantity
        movement = InventoryMovementType.ADJUSTMENT
        if after == before: raise HTTPException(status_code=422, detail="Counted stock matches current stock; no movement to record")
    delta = after - before
    if after > 0 and product.category.is_active and not product.is_archived: product.is_available = True
    elif after == 0: product.is_available = False
    product.stock_quantity = after
    _record_stock_movement(db, product, delta, movement, payload.reason.strip(), actor_user_id=staff.id, before=before)
    _record_audit(db, "inventory.stock_changed", "product", product.id, staff.id, {"movement_type": movement.value, "delta": delta, "before": before, "after": after, "reason": payload.reason.strip()})

    try:
        db.commit(); db.refresh(product)
    except SQLAlchemyError:
        db.rollback(); raise HTTPException(status_code=409, detail="Inventory update failed; no changes were saved")
    return {"product_id": product.id, "product_name": product.name, "stock_quantity": product.stock_quantity, "low_stock_threshold": product.low_stock_threshold, "movement_type": movement.value, "quantity_delta": delta}

@app.patch("/api/admin/inventory/products/{product_id}/threshold", tags=["inventory"], summary="Configure a product low-stock threshold")
def update_stock_threshold(product_id: int, payload: StockThresholdUpdate, _: User = Depends(require_roles("admin", "staff")), db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None: raise HTTPException(status_code=404, detail="Product not found")
    old_threshold = product.low_stock_threshold
    product.low_stock_threshold = payload.low_stock_threshold
    _record_audit(db, "inventory.threshold_changed", "product", product.id, _.id, {"old_threshold": old_threshold, "new_threshold": payload.low_stock_threshold})
    db.commit(); db.refresh(product)
    return {"product_id": product.id, "low_stock_threshold": product.low_stock_threshold, "stock_quantity": product.stock_quantity, "is_low_stock": product.stock_quantity <= product.low_stock_threshold}

# Phase 12: admin-only operational reports and immutable audit history.
def _report_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Dates must use YYYY-MM-DD format")

@app.get("/api/admin/reports/overview", tags=["admin reporting"], summary="Revenue and order KPI summary")
def admin_report_overview(start_date: str | None = Query(default=None), end_date: str | None = Query(default=None), admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    today = datetime.now().date()
    start = _report_date(start_date, today - timedelta(days=29))
    end = _report_date(end_date, today)
    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time())
    paid_filter = (Order.created_at >= start_dt, Order.created_at < end_dt, Order.payment_status == PaymentStatus.PAID)
    paid_orders = db.scalars(select(Order).where(*paid_filter)).all()
    all_orders = db.scalars(select(Order).where(Order.created_at >= start_dt, Order.created_at < end_dt)).all()
    by_status = {status.value: sum(o.status == status for o in all_orders) for status in OrderStatus}
    revenue = sum((Decimal(o.subtotal) for o in paid_orders), Decimal("0.00"))
    return {"start_date": start.isoformat(), "end_date": end.isoformat(), "paid_revenue": str(revenue), "paid_orders": len(paid_orders), "all_orders": len(all_orders), "average_paid_order_value": str((revenue / len(paid_orders)).quantize(Decimal("0.01")) if paid_orders else Decimal("0.00")), "orders_by_status": by_status, "pending_payments": sum(o.payment_status == PaymentStatus.PENDING for o in all_orders), "failed_payments": sum(o.payment_status == PaymentStatus.FAILED for o in all_orders), "refunded_orders": sum(o.payment_status == PaymentStatus.REFUNDED for o in all_orders)}

@app.get("/api/admin/reports/daily-sales", tags=["admin reporting"], summary="Daily paid sales for a date range")
def admin_report_daily_sales(start_date: str | None = Query(default=None), end_date: str | None = Query(default=None), _: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    today = datetime.now().date()
    start = _report_date(start_date, today - timedelta(days=13))
    end = _report_date(end_date, today)
    if start > end: raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if (end - start).days > 365: raise HTTPException(status_code=422, detail="Report range cannot exceed 366 days")
    rows = db.execute(select(func.date(Order.created_at).label("day"), func.count(Order.id).label("orders"), func.coalesce(func.sum(Order.subtotal), 0).label("revenue")).where(Order.created_at >= datetime.combine(start, datetime.min.time()), Order.created_at < datetime.combine(end + timedelta(days=1), datetime.min.time()), Order.payment_status == PaymentStatus.PAID).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at))).all()
    data = {str(row.day): {"orders": int(row.orders), "revenue": str(row.revenue)} for row in rows}
    result = []
    day = start
    while day <= end:
        item = data.get(day.isoformat(), {"orders": 0, "revenue": "0.00"})
        result.append({"date": day.isoformat(), **item})
        day += timedelta(days=1)
    return result

@app.get("/api/admin/reports/top-products", tags=["admin reporting"], summary="Top-selling products by quantity and sales")
def admin_report_top_products(start_date: str | None = Query(default=None), end_date: str | None = Query(default=None), limit: int = Query(default=10, ge=1, le=50), _: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    today = datetime.now().date(); start = _report_date(start_date, today - timedelta(days=29)); end = _report_date(end_date, today)
    if start > end: raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    rows = db.execute(select(OrderItem.product_id, OrderItem.product_name, func.sum(OrderItem.quantity).label("quantity_sold"), func.sum(OrderItem.line_total).label("sales")).join(OrderItem.order).where(Order.created_at >= datetime.combine(start, datetime.min.time()), Order.created_at < datetime.combine(end + timedelta(days=1), datetime.min.time()), Order.payment_status == PaymentStatus.PAID).group_by(OrderItem.product_id, OrderItem.product_name).order_by(func.sum(OrderItem.quantity).desc(), func.sum(OrderItem.line_total).desc()).limit(limit)).all()
    return [{"product_id": row.product_id, "product_name": row.product_name, "quantity_sold": int(row.quantity_sold), "sales": str(row.sales)} for row in rows]

@app.get("/api/admin/audit-events", tags=["admin audit"], summary="Search administrative and operational audit events")
def admin_audit_events(action: str | None = Query(default=None, max_length=80), entity_type: str | None = Query(default=None, max_length=80), limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0), _: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    stmt = select(AuditEvent).options(joinedload(AuditEvent.actor)).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    if action: stmt = stmt.where(AuditEvent.action == action)
    if entity_type: stmt = stmt.where(AuditEvent.entity_type == entity_type)
    rows = db.scalars(stmt.offset(offset).limit(limit)).unique().all()
    return [{"id": e.id, "actor_user_id": e.actor_user_id, "actor_name": e.actor.full_name if e.actor else None, "action": e.action, "entity_type": e.entity_type, "entity_id": e.entity_id, "details": json.loads(e.details_json or "{}"), "created_at": e.created_at} for e in rows]

@app.get("/api/staff/dashboard", tags=["staff tools"])
def staff_dashboard(user: User = Depends(require_roles("staff", "admin")), db: Session = Depends(get_db)):
    return {"message": "Staff access granted", "signed_in_as": user.full_name, "role": user.role.value, "catalogue": db.scalar(select(text("count(*)")).select_from(Product.__table__)) or 0}


# Phase 5–7: checkout, payment-gated order lifecycle, daily pickup tokens, and staff/admin queue.
def _order_payload(order: Order) -> dict[str, Any]:
    return {
        "id": order.id, "user_id": order.user_id, "token_number": order.token_number,
        "token_date": order.token_date, "status": order.status.value,
        "payment_status": order.payment_status.value, "subtotal": str(order.subtotal),
        "notes": order.notes, "gateway_order_id": order.gateway_order_id, "gateway_payment_id": order.gateway_payment_id, "created_at": order.created_at, "updated_at": order.updated_at,
        "items": [{"id": item.id, "product_id": item.product_id, "product_name": item.product_name,
                   "unit_price": str(item.unit_price), "quantity": item.quantity, "line_total": str(item.line_total)}
                  for item in order.items]
    }

@app.post("/api/orders/quote", tags=["checkout"])
def quote_order(payload: OrderCreateIn, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    """Validate a cart and return server-priced totals without reserving stock."""
    from decimal import Decimal
    quantities: dict[int, int] = {}
    for line in payload.items:
        quantities[line.product_id] = quantities.get(line.product_id, 0) + line.quantity
    products = db.scalars(select(Product).where(Product.id.in_(list(quantities))).options(joinedload(Product.category))).all()
    by_id = {product.id: product for product in products}
    if len(by_id) != len(quantities):
        raise HTTPException(status_code=422, detail="One or more products no longer exist")
    lines = []
    subtotal = Decimal("0.00")
    for product_id, quantity in quantities.items():
        product = by_id[product_id]
        if not product.is_available or not product.category.is_active or product.stock_quantity < quantity:
            raise HTTPException(status_code=409, detail=f"{product.name} is unavailable or has insufficient stock")
        unit_price = Decimal(product.price)
        line_total = (unit_price * quantity).quantize(Decimal("0.01"))
        subtotal += line_total
        lines.append({"product_id": product.id, "product_name": product.name, "unit_price": str(unit_price), "quantity": quantity, "line_total": str(line_total), "stock_available": product.stock_quantity})
    return {"items": lines, "subtotal": str(subtotal.quantize(Decimal("0.01"))), "currency": "INR", "payment_status": "pending", "stock_reserved": False}

def _release_expired_payment_reservations(db: Session) -> None:
    """Release stock reserved by abandoned, unpaid checkouts after 30 minutes."""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    pending = db.scalars(select(Order).where(Order.gateway_order_id.is_not(None), Order.payment_status == PaymentStatus.PENDING, Order.status == OrderStatus.PENDING).options(joinedload(Order.items))).unique().all()
    changed = False
    for order in pending:
        created = order.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created is not None and created < cutoff:
            _release_batch_stock(db, order.id)
            for line in order.items:
                product = db.get(Product, line.product_id)
                if product:
                    before_stock = product.stock_quantity
                    product.stock_quantity += line.quantity
                    _record_stock_movement(db, product, line.quantity, InventoryMovementType.RELEASE, f"Released expired checkout reservation for order {order.id}", order_id=order.id, before=before_stock)
                    if product.category.is_active:
                        product.is_available = True
            order.status = OrderStatus.CANCELLED
            order.payment_status = PaymentStatus.FAILED
            _record_audit(db, "payment.checkout_expired", "order", order.id, None, {"stock_released": True})
            changed = True
    if changed:
        db.commit()


@app.post("/api/payments/create-order", status_code=201, tags=["payments"])
def create_payment_order(payload: OrderCreateIn, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    """Create a Razorpay order and reserve stock for a checkout attempt."""
    import httpx
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(status_code=503, detail="Online payments are not configured. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to .env.")
    _release_expired_payment_reservations(db)
    quantities: dict[int, int] = {}
    for line in payload.items:
        quantities[line.product_id] = quantities.get(line.product_id, 0) + line.quantity
    products = db.scalars(select(Product).where(Product.id.in_(list(quantities))).options(joinedload(Product.category)).with_for_update()).all()
    by_id = {product.id: product for product in products}
    if len(by_id) != len(quantities):
        raise HTTPException(status_code=422, detail="One or more products no longer exist")
    lines = []
    subtotal = Decimal("0.00")
    for product_id, quantity in quantities.items():
        product = by_id[product_id]
        if not product.is_available or not product.category.is_active or product.stock_quantity < quantity:
            raise HTTPException(status_code=409, detail=f"{product.name} is unavailable or has insufficient stock")
        price = Decimal(product.price)
        total = (price * quantity).quantize(Decimal("0.01"))
        subtotal += total
        lines.append((product, quantity, price, total))
    amount_paise = int((subtotal * 100).quantize(Decimal("1")))
    try:
        response = httpx.post("https://api.razorpay.com/v1/orders", auth=(settings.razorpay_key_id, settings.razorpay_key_secret), json={"amount": amount_paise, "currency": settings.payment_currency, "receipt": f"ace-{user.id}-{int(time.time())}", "notes": {"user_id": str(user.id)}}, timeout=15.0)
        response.raise_for_status()
        gateway_order = response.json()
    except Exception as exc:
        logger.warning("Razorpay order creation failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Payment provider could not create the checkout. No order was placed; please retry.")
    today = datetime.now().date().isoformat()
    last_token = db.scalar(select(func.max(Order.token_number)).where(Order.token_date == today)) or 0
    order = Order(user_id=user.id, token_number=last_token + 1, token_date=today, status=OrderStatus.PENDING, payment_status=PaymentStatus.PENDING, subtotal=subtotal, notes=payload.notes, gateway_order_id=gateway_order["id"])
    try:
        db.add(order)
        db.flush()
        _record_audit(db, "order.checkout_created", "order", order.id, user.id, {"subtotal": str(order.subtotal), "item_count": len(lines), "gateway_order_id": gateway_order["id"]})
        for product, quantity, price, line_total in lines:
            _reserve_batch_stock(db, product.id, quantity, order.id)
            before_stock = product.stock_quantity
            product.stock_quantity -= quantity
            _record_stock_movement(db, product, -quantity, InventoryMovementType.RESERVATION, f"Reserved for checkout order {gateway_order['id']}", actor_user_id=user.id, order_id=order.id, before=before_stock)
            if product.stock_quantity == 0:
                product.is_available = False
            order.items.append(OrderItem(product_id=product.id, product_name=product.name, unit_price=price, quantity=quantity, line_total=line_total))
        db.commit()
        db.refresh(order)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Order reservation failed after gateway order creation")
        raise HTTPException(status_code=409, detail="Could not reserve stock for checkout. No payment has been collected.")
    return {"order": _order_payload(order), "payment": {"key_id": settings.razorpay_key_id, "gateway_order_id": gateway_order["id"], "amount": amount_paise, "currency": settings.payment_currency, "name": settings.app_name, "description": f"Canteen order #{order.id}", "prefill": {"name": user.full_name, "email": user.email}}}

@app.post("/api/payments/verify", tags=["payments"])
def verify_payment(payload: dict[str, str], user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    """Verify Razorpay checkout signature before marking an order as paid."""
    gateway_order_id = payload.get("razorpay_order_id", "")
    payment_id = payload.get("razorpay_payment_id", "")
    signature = payload.get("razorpay_signature", "")
    if not all((gateway_order_id, payment_id, signature)):
        raise HTTPException(status_code=422, detail="Missing payment verification fields")
    if not settings.razorpay_key_secret:
        raise HTTPException(status_code=503, detail="Payment verification is not configured")
    order = db.scalar(select(Order).where(Order.gateway_order_id == gateway_order_id, Order.user_id == user.id).options(joinedload(Order.items)))
    if order is None:
        raise HTTPException(status_code=404, detail="Checkout order not found for this account")
    if order.status == OrderStatus.CANCELLED or order.payment_status == PaymentStatus.FAILED:
        raise HTTPException(status_code=409, detail="This checkout has expired or failed. Check your payment history before retrying.")
    if order.payment_status == PaymentStatus.PAID:
        if order.gateway_payment_id == payment_id:
            return {"verified": True, "order": _order_payload(order)}
        raise HTTPException(status_code=409, detail="This order has already been paid with a different payment")
    expected = hmac.new(settings.razorpay_key_secret.encode(), f"{gateway_order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=400, detail="Payment signature is invalid")
    order.payment_status = PaymentStatus.PAID
    order.gateway_payment_id = payment_id
    order.payment_signature = signature
    _create_notification(db, user.id, "payment", "Payment successful", f"Payment received for order #{order.id}. Your pickup token will appear in order history.", "order", order.id)
    _record_audit(db, "payment.verified", "order", order.id, user.id, {"payment_id": payment_id, "amount": str(order.subtotal), "provider": "razorpay"})
    try:
        db.commit(); db.refresh(order)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Payment was verified but the order could not be updated. Contact the canteen administrator with your payment ID.")
    return {"verified": True, "order": _order_payload(order)}

@app.post("/api/payments/webhook", include_in_schema=False)
async def razorpay_webhook(request: Request, x_razorpay_signature: str | None = Header(default=None), x_razorpay_event_id: str | None = Header(default=None)):
    """Razorpay webhook signature validation; payment.captured reconciles delayed callbacks."""
    if not settings.razorpay_webhook_secret:
        raise HTTPException(status_code=503, detail="Payment webhook is not configured")
    body = await request.body()
    expected = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not x_razorpay_signature or not hmac.compare_digest(expected, x_razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    try:
        event = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Webhook body must be valid JSON")
    event_name = event.get("event") if isinstance(event, dict) else None
    payment = event.get("payload", {}).get("payment", {}).get("entity", {}) if isinstance(event, dict) else {}
    # Razorpay retries deliveries. Use its event ID, or a body digest for providers
    # or test fixtures that omit the header, to prevent replayed side effects.
    webhook_id = (x_razorpay_event_id or hashlib.sha256(body).hexdigest()).strip()
    if not webhook_id or len(webhook_id) > 160:
        raise HTTPException(status_code=400, detail="Invalid webhook event ID")
    with SessionLocal() as db:
        prior = db.scalar(select(PaymentWebhookEvent).where(PaymentWebhookEvent.event_id == webhook_id))
        if prior is not None:
            return {"received": True, "duplicate": True}
        db.add(PaymentWebhookEvent(event_id=webhook_id, event_name=str(event_name or "unknown")[:100]))
        try:
            db.flush()
        except SQLAlchemyError:
            db.rollback()
            # A concurrent delivery may have won the unique-key race. Treat it as a retry.
            with SessionLocal() as check_db:
                if check_db.scalar(select(PaymentWebhookEvent.id).where(PaymentWebhookEvent.event_id == webhook_id)):
                    return {"received": True, "duplicate": True}
            raise HTTPException(status_code=503, detail="Could not record webhook delivery; provider may retry")
        if event_name in {"payment.captured", "payment.failed"} and payment.get("order_id"):
            order = db.scalar(select(Order).where(Order.gateway_order_id == payment["order_id"]).options(joinedload(Order.items)))
            if order and event_name == "payment.captured" and payment.get("id") and order.status != OrderStatus.CANCELLED and order.payment_status != PaymentStatus.FAILED:
                expected_amount = int((Decimal(order.subtotal) * 100).quantize(Decimal("1")))
                if int(payment.get("amount", 0)) == expected_amount and payment.get("currency", settings.payment_currency) == settings.payment_currency and order.payment_status != PaymentStatus.PAID:
                    order.payment_status = PaymentStatus.PAID
                    order.gateway_payment_id = payment["id"]
                    _create_notification(db, order.user_id, "payment", "Payment confirmed", f"Payment for order #{order.id} has been confirmed.", "order", order.id)
                    _record_audit(db, "payment.captured_webhook", "order", order.id, None, {"payment_id": payment["id"], "amount_minor": int(payment.get("amount", 0))})
                    db.commit()
            elif order and event_name == "payment.failed" and order.payment_status != PaymentStatus.PAID and order.status != OrderStatus.CANCELLED:
                _release_batch_stock(db, order.id)
                for line in order.items:
                    product = db.get(Product, line.product_id)
                    if product:
                        before_stock = product.stock_quantity
                        product.stock_quantity += line.quantity
                        _record_stock_movement(db, product, line.quantity, InventoryMovementType.RELEASE, f"Released failed payment reservation for order {order.id}", order_id=order.id, before=before_stock)
                        if product.category.is_active:
                            product.is_available = True
                order.status = OrderStatus.CANCELLED
                order.payment_status = PaymentStatus.FAILED
                _create_notification(db, order.user_id, "payment", "Payment failed", f"Payment for order #{order.id} failed. Reserved stock was released; please retry checkout if needed.", "order", order.id)
                _record_audit(db, "payment.failed_webhook", "order", order.id, None, {"payment_id": payment.get("id"), "stock_released": True})
                db.commit()
        db.commit()
    return {"received": True}

@app.post("/api/orders", status_code=410, tags=["orders"], include_in_schema=False)
def legacy_create_order(_: OrderCreateIn, user: User = Depends(require_roles("student"))):
    """Block the legacy unpaid order endpoint so checkout cannot bypass payment verification."""
    raise HTTPException(status_code=410, detail="Direct order placement is disabled. Use /api/payments/create-order to pay and place an order.")

@app.get("/api/queue/overview", tags=["order queue"])
def queue_overview(db: Session = Depends(get_db)):
    """Public, privacy-preserving daily pickup board: tokens only, no student details."""
    today = datetime.now().date().isoformat()
    active_statuses = [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY]
    orders = db.scalars(
        select(Order)
        .where(Order.token_date == today, Order.payment_status == PaymentStatus.PAID, Order.status.in_(active_statuses))
        .order_by(Order.created_at.asc(), Order.id.asc())
    ).all()
    preparing = [o.token_number for o in orders if o.status == OrderStatus.PREPARING]
    ready = [o.token_number for o in orders if o.status == OrderStatus.READY]
    active_queue = [o for o in orders if o.status in {OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PREPARING}]
    # This is an estimate, not a promise: five minutes per active order ahead.
    token_rows = []
    for order in orders:
        position = next((i for i, queued in enumerate(active_queue) if queued.id == order.id), None)
        token_rows.append({
            "token_number": order.token_number,
            "status": order.status.value,
            "estimated_wait_minutes": (position * 5) if position is not None else 0,
            "created_at": order.created_at,
        })
    return {
        "token_date": today,
        "active_orders": len(orders),
        "preparing_tokens": preparing,
        "ready_tokens": ready,
        "queue": token_rows,
        "estimate_minutes_per_order": 5,
        "estimate_note": "Wait times are approximate and may change with preparation time.",
    }


@app.get("/api/orders/{order_id}/queue-position", tags=["orders"])
def order_queue_position(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != user.id and user.role not in {UserRole.STAFF, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="You can only view your own order queue position")
    if order.payment_status != PaymentStatus.PAID:
        return {"order_id": order.id, "token_number": order.token_number, "status": order.status.value, "queue_position": None, "estimated_wait_minutes": None, "message": "Queue position is available after payment is verified."}
    active_statuses = [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PREPARING]
    ahead = db.scalars(
        select(Order.id).where(
            Order.token_date == order.token_date,
            Order.payment_status == PaymentStatus.PAID,
            Order.status.in_(active_statuses),
            Order.created_at < order.created_at,
        )
    ).all()
    is_active = order.status in active_statuses
    position = len(ahead) + 1 if is_active else 0
    return {
        "order_id": order.id,
        "token_number": order.token_number,
        "status": order.status.value,
        "queue_position": position if is_active else None,
        "estimated_wait_minutes": (position - 1) * 5 if is_active else 0,
        "message": "Approximate estimate only; preparation times can vary." if is_active else "Your order is not waiting in the active preparation queue.",
    }


@app.get("/api/orders/mine", tags=["orders"])
def my_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.scalars(select(Order).where(Order.user_id == user.id).options(joinedload(Order.items)).order_by(Order.created_at.desc()).limit(100)).unique().all()
    return [_order_payload(order) for order in orders]

@app.get("/api/favorites", tags=["student tools"])
def list_favorites(user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    """Return the signed-in student's saved items, never another user's."""
    rows = db.scalars(select(Favorite).where(Favorite.user_id == user.id).options(joinedload(Favorite.product).joinedload(Product.category)).order_by(Favorite.created_at.desc())).unique().all()
    return [{"id": row.product.id, "name": row.product.name, "description": row.product.description, "price": str(row.product.price), "stock_quantity": row.product.stock_quantity, "is_available": row.product.is_available and not row.product.is_archived, "item_type": row.product.item_type, "category_name": row.product.category.name if row.product.category else None, "image_url": row.product.image_url, "dietary_info": row.product.dietary_info, "allergens": row.product.allergens, "saved_at": row.created_at} for row in rows]

@app.post("/api/favorites/{product_id}", status_code=201, tags=["student tools"])
def add_favorite(product_id: int, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.id == product_id, Product.is_archived.is_(False)))
    if not product:
        raise HTTPException(status_code=404, detail="Catalogue item not found")
    existing = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id))
    if existing:
        return {"saved": True, "product_id": product_id, "message": "Already in your saved items"}
    db.add(Favorite(user_id=user.id, product_id=product_id))
    db.commit()
    return {"saved": True, "product_id": product_id}

@app.delete("/api/favorites/{product_id}", tags=["student tools"])
def remove_favorite(product_id: int, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    favorite = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id))
    if favorite:
        db.delete(favorite)
        db.commit()
    return {"saved": False, "product_id": product_id}

@app.post("/api/orders/{order_id}/reorder-quote", tags=["student tools"])
def reorder_quote(order_id: int, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    """Build a fresh quote from a student's own historical order; never reuses stale prices."""
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user.id).options(joinedload(Order.items)))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    lines = []
    unavailable = []
    for old_line in order.items:
        product = db.get(Product, old_line.product_id)
        if not product or product.is_archived or not product.is_available or product.stock_quantity < 1:
            unavailable.append(old_line.product_name)
            continue
        qty = min(old_line.quantity, product.stock_quantity, 50)
        lines.append({"product_id": product.id, "product_name": product.name, "quantity": qty, "unit_price": str(product.price), "line_total": str((product.price * qty).quantize(Decimal("0.01"))), "stock_available": product.stock_quantity, "quantity_adjusted": qty != old_line.quantity})
    subtotal = sum((Decimal(line["line_total"]) for line in lines), Decimal("0.00")).quantize(Decimal("0.01"))
    return {"source_order_id": order.id, "items": lines, "unavailable_items": unavailable, "subtotal": str(subtotal), "currency": settings.payment_currency, "requires_fresh_checkout": True, "message": "Prices and availability were refreshed. Review the cart and complete a new checkout."}

@app.get("/api/orders/{order_id}/review", tags=["student feedback"])
def get_order_review(order_id: int, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user.id))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    review = db.scalar(select(OrderReview).where(OrderReview.order_id == order_id, OrderReview.user_id == user.id))
    return {"eligible": order.payment_status == PaymentStatus.PAID and order.status == OrderStatus.COMPLETED, "review": ({"id": review.id, "rating": review.rating, "comment": review.comment, "created_at": review.created_at} if review else None)}

@app.post("/api/orders/{order_id}/review", tags=["student feedback"])
def submit_order_review(order_id: int, payload: dict[str, Any], user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    rating = payload.get("rating")
    comment = payload.get("comment", "")
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
        raise HTTPException(status_code=422, detail="Rating must be a whole number from 1 to 5")
    if not isinstance(comment, str) or len(comment.strip()) > 500:
        raise HTTPException(status_code=422, detail="Comment must be 500 characters or fewer")
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user.id))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.payment_status != PaymentStatus.PAID or order.status != OrderStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Feedback is available after a paid order has been collected")
    review = db.scalar(select(OrderReview).where(OrderReview.order_id == order_id))
    if review and review.user_id != user.id:
        raise HTTPException(status_code=409, detail="This order already has feedback")
    if review:
        review.rating = rating
        review.comment = comment.strip() or None
        review.updated_at = datetime.now().astimezone()
    else:
        review = OrderReview(order_id=order.id, user_id=user.id, rating=rating, comment=comment.strip() or None)
        db.add(review)
    db.commit()
    db.refresh(review)
    return {"id": review.id, "order_id": review.order_id, "rating": review.rating, "comment": review.comment, "created_at": review.created_at, "message": "Thank you for helping improve ACE Canteen!"}

@app.get("/api/feedback/summary", tags=["student feedback"])
def feedback_summary(_: User = Depends(require_roles("staff", "admin")), db: Session = Depends(get_db)):
    rows = db.execute(select(OrderReview.rating, func.count(OrderReview.id)).group_by(OrderReview.rating)).all()
    counts = {int(rating): int(count) for rating, count in rows}
    total = sum(counts.values())
    average = round(sum(rating * count for rating, count in counts.items()) / total, 2) if total else None
    recent = db.scalars(select(OrderReview).options(joinedload(OrderReview.user)).order_by(OrderReview.created_at.desc()).limit(100)).all()
    return {"count": total, "average_rating": average, "rating_counts": {str(i): counts.get(i, 0) for i in range(1, 6)}, "recent": [{"order_id": r.order_id, "student_name": r.user.full_name, "rating": r.rating, "comment": r.comment, "created_at": r.created_at} for r in recent]}

@app.get("/api/staff/workflow-summary", tags=["staff tools"])
def staff_workflow_summary(_: User = Depends(require_roles("staff", "admin")), db: Session = Depends(get_db)):
    """Operational counts for the kitchen and pickup counter dashboards."""
    today = datetime.now().date().isoformat()
    paid = Order.payment_status == PaymentStatus.PAID
    def count_for(*statuses):
        return db.scalar(select(func.count(Order.id)).where(paid, Order.status.in_(statuses))) or 0
    today_orders = db.scalar(select(func.count(Order.id)).where(paid, Order.token_date == today)) or 0
    today_completed = db.scalar(select(func.count(Order.id)).where(paid, Order.token_date == today, Order.status == OrderStatus.COMPLETED)) or 0
    return {
        "token_date": today,
        "kitchen_waiting": count_for(OrderStatus.PENDING, OrderStatus.CONFIRMED),
        "kitchen_preparing": count_for(OrderStatus.PREPARING),
        "ready_for_pickup": count_for(OrderStatus.READY),
        "completed_today": today_completed,
        "paid_orders_today": today_orders,
    }

@app.get("/api/admin/orders", tags=["order queue"])
def order_queue(status: str | None = Query(default=None, pattern="^(pending|confirmed|preparing|ready|completed|cancelled)$"), _: User = Depends(require_roles("staff", "admin")), db: Session = Depends(get_db)):
    stmt = select(Order).where(Order.payment_status == PaymentStatus.PAID).options(joinedload(Order.items), joinedload(Order.user)).order_by(Order.created_at.asc()).limit(250)
    if status:
        stmt = stmt.where(Order.status == OrderStatus(status))
    orders = db.scalars(stmt).unique().all()
    result = []
    for order in orders:
        data = _order_payload(order)
        data["customer_name"] = order.user.full_name
        data["customer_email"] = order.user.email
        result.append(data)
    return result

@app.get("/api/admin/orders/all", tags=["admin order verification"], summary="Admin-only complete order register")
def admin_all_orders(
    status: str | None = Query(default=None, pattern="^(pending|confirmed|preparing|ready|completed|cancelled)$"),
    payment_status: str | None = Query(default=None, pattern="^(pending|paid|failed|refunded)$"),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """Return paid, unpaid, failed and completed orders for administrator review.

    Staff keep using the operational paid-order queue; this register is admin-only
    so payment exceptions and customer details are not exposed to ordinary staff.
    """
    stmt = select(Order).options(joinedload(Order.items), joinedload(Order.user)).order_by(Order.created_at.desc()).offset(offset).limit(limit)
    if status:
        stmt = stmt.where(Order.status == OrderStatus(status))
    if payment_status:
        stmt = stmt.where(Order.payment_status == PaymentStatus(payment_status))
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.join(Order.user).where(or_(Order.user.has(User.full_name.ilike(term)), Order.user.has(User.email.ilike(term)), cast(Order.id, String).ilike(term), Order.gateway_order_id.ilike(term)))
    orders = db.scalars(stmt).unique().all()
    result = []
    for order in orders:
        data = _order_payload(order)
        data["customer_name"] = order.user.full_name
        data["customer_email"] = order.user.email
        result.append(data)
    return {"items": result, "limit": limit, "offset": offset, "returned": len(result)}

@app.get("/api/admin/dashboard/summary", tags=["administration"], summary="Cross-module admin overview")
def admin_dashboard_summary(_: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    """Aggregate operational KPIs for administrators without exposing individual records."""
    total_orders = db.scalar(select(func.count(Order.id))) or 0
    paid_orders = db.scalar(select(func.count(Order.id)).where(Order.payment_status == PaymentStatus.PAID)) or 0
    pending_payments = db.scalar(select(func.count(Order.id)).where(Order.payment_status == PaymentStatus.PENDING)) or 0
    failed_payments = db.scalar(select(func.count(Order.id)).where(Order.payment_status == PaymentStatus.FAILED)) or 0
    open_orders = db.scalar(select(func.count(Order.id)).where(Order.status.in_([OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY]))) or 0
    paid_revenue = db.scalar(select(func.coalesce(func.sum(Order.subtotal), 0)).where(Order.payment_status == PaymentStatus.PAID)) or Decimal("0.00")
    low_stock = db.scalar(select(func.count(Product.id)).where(Product.is_archived.is_(False), Product.stock_quantity <= Product.low_stock_threshold)) or 0
    active_users = db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0
    webhook_events = db.scalar(select(func.count(PaymentWebhookEvent.id))) or 0
    return {"orders_total": total_orders, "orders_paid": paid_orders, "orders_open": open_orders,
            "payments_pending": pending_payments, "payments_failed": failed_payments,
            "paid_revenue": str(paid_revenue), "low_stock_products": low_stock,
            "active_users": active_users, "webhook_events_received": webhook_events}

@app.get("/api/admin/orders/export.csv", tags=["admin order verification"], summary="Export order register as CSV")
def admin_export_orders_csv(
    status: str | None = Query(default=None, pattern="^(pending|confirmed|preparing|ready|completed|cancelled)$"),
    payment_status: str | None = Query(default=None, pattern="^(pending|paid|failed|refunded)$"),
    _: User = Depends(require_roles("admin")), db: Session = Depends(get_db),
):
    """Download a bounded CSV of orders for reconciliation; no payment secrets are exported."""
    stmt = select(Order).options(joinedload(Order.user)).order_by(Order.created_at.desc()).limit(10000)
    if status:
        stmt = stmt.where(Order.status == OrderStatus(status))
    if payment_status:
        stmt = stmt.where(Order.payment_status == PaymentStatus(payment_status))
    orders = db.scalars(stmt).unique().all()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["order_id", "created_at", "customer_name", "customer_email", "order_status", "payment_status", "amount", "pickup_token", "gateway_order_id", "gateway_payment_id"])
    for order in orders:
        writer.writerow([order.id, order.created_at.isoformat() if order.created_at else "", order.user.full_name if order.user else "", order.user.email if order.user else "", order.status.value, order.payment_status.value, str(order.subtotal), order.token_number or "", order.gateway_order_id or "", order.gateway_payment_id or ""])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=ace-canteen-orders.csv", "Cache-Control": "no-store"})

@app.get("/api/admin/payments/webhook-events", tags=["admin payment verification"], summary="Inspect received payment webhook event ledger")
def admin_payment_webhook_events(
    limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0),
    _: User = Depends(require_roles("admin")), db: Session = Depends(get_db),
):
    events = db.scalars(select(PaymentWebhookEvent).order_by(PaymentWebhookEvent.received_at.desc()).offset(offset).limit(limit)).all()
    return {"items": [{"id": event.id, "event_id": event.event_id, "event_name": event.event_name, "received_at": event.received_at.isoformat()} for event in events], "limit": limit, "offset": offset, "returned": len(events)}

@app.patch("/api/admin/orders/{order_id}/status", tags=["order queue"])
def update_order_status(order_id: int, payload: OrderStatusIn, staff: User = Depends(require_roles("staff", "admin")), db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where(Order.id == order_id).options(joinedload(Order.items)))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.payment_status != PaymentStatus.PAID:
        raise HTTPException(status_code=409, detail="Only paid orders can enter the preparation queue")
    target = OrderStatus(payload.status)
    allowed = {
        OrderStatus.PENDING: {OrderStatus.CONFIRMED},
        OrderStatus.CONFIRMED: {OrderStatus.PREPARING},
        OrderStatus.PREPARING: {OrderStatus.READY},
        OrderStatus.READY: {OrderStatus.COMPLETED},
        OrderStatus.COMPLETED: set(), OrderStatus.CANCELLED: set(),
    }
    if target not in allowed[order.status]:
        raise HTTPException(status_code=409, detail=f"Cannot change order from {order.status.value} to {target.value}")
    if target == OrderStatus.CANCELLED:
        # Restore reserved stock when staff cancels an uncompleted order.
        _release_batch_stock(db, order.id)
        for line in order.items:
            product = db.get(Product, line.product_id)
            if product:
                before_stock = product.stock_quantity
                product.stock_quantity += line.quantity
                _record_stock_movement(db, product, line.quantity, InventoryMovementType.RELEASE, f"Released stock for cancelled order {order.id}", actor_user_id=staff.id, order_id=order.id, before=before_stock)
                if product.category.is_active:
                    product.is_available = True
    previous_status = order.status.value
    order.status = target
    status_messages = {OrderStatus.CONFIRMED: ("Order confirmed", "The canteen has confirmed your order."), OrderStatus.PREPARING: ("Order is being prepared", "Your order is now being prepared."), OrderStatus.READY: ("Ready for pickup", f"Order #{order.id} is ready. Please collect it using token {order.token_number or '—'}."), OrderStatus.COMPLETED: ("Order collected", "Your order has been marked as collected. Thank you!")}
    notification_title, notification_message = status_messages[target]
    _create_notification(db, order.user_id, "order_status", notification_title, notification_message, "order", order.id)
    _record_audit(db, "order.status_changed", "order", order.id, staff.id, {"old_status": previous_status, "new_status": target.value, "token_number": order.token_number})
    try:
        db.commit(); db.refresh(order)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not update order status")
    return _order_payload(order)

# Phase 26-37 operational release: supplier traceability, batch expiry, and demand insights.
from pydantic import BaseModel, Field
from datetime import date as _date
from app.models import Supplier, ProductBatch, BatchReservation

def _reserve_batch_stock(db: Session, product_id: int, quantity: int, order_id: int) -> None:
    """Consume available non-expired batches in FEFO order and retain allocations.

    Any remainder may be legacy/untracked stock, which is reported by reconciliation.
    """
    today = _date.today()
    batches = db.scalars(select(ProductBatch).where(
        ProductBatch.product_id == product_id, ProductBatch.quantity_remaining > 0,
        (ProductBatch.expiry_date.is_(None)) | (ProductBatch.expiry_date >= today),
    ).order_by(ProductBatch.expiry_date.is_(None), ProductBatch.expiry_date.asc(), ProductBatch.received_date.asc(), ProductBatch.id.asc()).with_for_update()).all()
    remaining = quantity
    for batch in batches:
        if remaining <= 0:
            break
        take = min(remaining, batch.quantity_remaining)
        if take:
            batch.quantity_remaining -= take
            db.add(BatchReservation(order_id=order_id, batch_id=batch.id, quantity=take))
            remaining -= take

def _release_batch_stock(db: Session, order_id: int) -> int:
    """Release batch allocations once only; returns total units restored."""
    rows = db.scalars(select(BatchReservation).where(BatchReservation.order_id == order_id, BatchReservation.released_at.is_(None)).with_for_update()).all()
    restored = 0
    now = datetime.now().astimezone()
    for allocation in rows:
        batch = db.get(ProductBatch, allocation.batch_id)
        if batch is not None:
            batch.quantity_remaining += allocation.quantity
            restored += allocation.quantity
        allocation.released_at = now
    return restored

class SupplierCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=500)

class BatchReceiptIn(BaseModel):
    product_id: int = Field(gt=0)
    supplier_id: int | None = Field(default=None, gt=0)
    batch_code: str = Field(min_length=1, max_length=80)
    quantity: int = Field(gt=0, le=100000)
    unit_cost: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    expiry_date: _date | None = None
    notes: str | None = Field(default=None, max_length=255)

@app.post("/api/admin/suppliers", status_code=201, tags=["procurement"])
def create_supplier(payload: SupplierCreateIn, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    db.flush()
    _record_audit(db, "supplier.created", "supplier", supplier.id, admin.id, {"name": supplier.name})
    db.commit(); db.refresh(supplier)
    return {"id": supplier.id, "name": supplier.name, "contact_name": supplier.contact_name, "phone": supplier.phone, "email": supplier.email, "notes": supplier.notes, "is_active": supplier.is_active}

@app.get("/api/admin/suppliers", tags=["procurement"])
def list_suppliers(_: User = Depends(require_roles("admin", "staff")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Supplier).order_by(Supplier.name.asc())).all()
    return [{"id": x.id, "name": x.name, "contact_name": x.contact_name, "phone": x.phone, "email": x.email, "notes": x.notes, "is_active": x.is_active} for x in rows]

@app.post("/api/admin/inventory/batches", status_code=201, tags=["inventory", "procurement"])
def receive_batch(payload: BatchReceiptIn, staff: User = Depends(require_roles("admin", "staff")), db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.id == payload.product_id).options(joinedload(Product.category)))
    if product is None or product.is_archived:
        raise HTTPException(status_code=404, detail="Active product not found")
    if payload.supplier_id is not None and db.get(Supplier, payload.supplier_id) is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    if payload.expiry_date and payload.expiry_date < _date.today():
        raise HTTPException(status_code=422, detail="Cannot receive a batch with an expiry date in the past")
    batch = ProductBatch(product_id=product.id, supplier_id=payload.supplier_id, batch_code=payload.batch_code.strip(), quantity_received=payload.quantity, quantity_remaining=payload.quantity, unit_cost=payload.unit_cost, expiry_date=payload.expiry_date, notes=payload.notes, created_by_user_id=staff.id)
    before = product.stock_quantity
    product.stock_quantity += payload.quantity
    product.is_available = product.category.is_active and product.stock_quantity > 0
    db.add(batch)
    _record_stock_movement(db, product, payload.quantity, InventoryMovementType.RECEIPT, f"Batch receipt {payload.batch_code}"[:255], actor_user_id=staff.id, before=before)
    _record_audit(db, "inventory.batch_received", "product_batch", None, staff.id, {"product_id": product.id, "batch_code": payload.batch_code, "quantity": payload.quantity, "supplier_id": payload.supplier_id})
    db.commit(); db.refresh(batch)
    return {"id": batch.id, "product_id": batch.product_id, "supplier_id": batch.supplier_id, "batch_code": batch.batch_code, "quantity_received": batch.quantity_received, "quantity_remaining": batch.quantity_remaining, "expiry_date": batch.expiry_date, "stock_after": product.stock_quantity}

@app.get("/api/admin/inventory/expiry", tags=["inventory"])
def inventory_expiry(days: int = Query(default=30, ge=0, le=365), _: User = Depends(require_roles("admin", "staff")), db: Session = Depends(get_db)):
    today = _date.today(); cutoff = today + timedelta(days=days)
    batches = db.scalars(select(ProductBatch).options(joinedload(ProductBatch.product), joinedload(ProductBatch.supplier)).where(ProductBatch.quantity_remaining > 0, ProductBatch.expiry_date.is_not(None), ProductBatch.expiry_date <= cutoff).order_by(ProductBatch.expiry_date.asc()).limit(500)).all()
    return {"as_of": today.isoformat(), "window_days": days, "count": len(batches), "batches": [{"id": b.id, "product_id": b.product_id, "product_name": b.product.name, "supplier_id": b.supplier_id, "supplier_name": b.supplier.name if b.supplier else None, "batch_code": b.batch_code, "quantity_remaining": b.quantity_remaining, "expiry_date": b.expiry_date.isoformat() if b.expiry_date else None, "expired": bool(b.expiry_date and b.expiry_date < today)} for b in batches]}

@app.get("/api/admin/inventory/reconciliation", tags=["inventory"], summary="Compare aggregate product stock with traceable batch stock")
def inventory_reconciliation(_: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    """Read-only reconciliation; never silently rewrites stock to hide discrepancies."""
    products = db.scalars(select(Product).where(Product.is_archived.is_(False)).order_by(Product.name.asc())).all()
    result = []
    for product in products:
        batches = db.scalars(select(ProductBatch).where(ProductBatch.product_id == product.id)).all()
        traceable = sum(max(0, int(batch.quantity_remaining)) for batch in batches)
        has_batches = bool(batches)
        difference = int(product.stock_quantity) - traceable
        result.append({
            "product_id": product.id,
            "product_name": product.name,
            "aggregate_stock": int(product.stock_quantity),
            "batch_stock": traceable if has_batches else None,
            "difference": difference if has_batches else None,
            "has_batches": has_batches,
            "status": ("matched" if difference == 0 else "mismatch") if has_batches else "untracked_legacy_stock",
        })
    mismatches = sum(1 for row in result if row["status"] == "mismatch")
    untracked = sum(1 for row in result if row["status"] == "untracked_legacy_stock")
    return {"products_checked": len(result), "mismatches": mismatches, "untracked_legacy_products": untracked, "items": result}


@app.get("/api/admin/analytics/demand", tags=["admin reporting"])
def demand_analytics(days: int = Query(default=30, ge=7, le=180), limit: int = Query(default=20, ge=1, le=100), _: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    """Simple transparent demand estimate from paid orders; not an ML guarantee."""
    since = datetime.now() - timedelta(days=days)
    rows = db.execute(select(OrderItem.product_id, OrderItem.product_name, func.sum(OrderItem.quantity).label("units"), func.count(func.distinct(OrderItem.order_id)).label("orders")).join(Order, Order.id == OrderItem.order_id).where(Order.payment_status == PaymentStatus.PAID, Order.created_at >= since).group_by(OrderItem.product_id, OrderItem.product_name).order_by(func.sum(OrderItem.quantity).desc()).limit(limit)).all()
    return {"window_days": days, "generated_at": datetime.now().isoformat(), "method": "historical paid-order average; excludes seasonality and stockouts", "products": [{"product_id": int(r.product_id), "product_name": r.product_name, "units_sold": int(r.units or 0), "orders": int(r.orders or 0), "average_units_per_day": round(float(r.units or 0) / days, 2), "suggested_reorder_units": max(0, round(float(r.units or 0) / days * 3))} for r in rows]}
