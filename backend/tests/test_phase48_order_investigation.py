"""Phase 48: admin-only complete order investigation dossier."""
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.database import SessionLocal, Base, engine
from app.models import User, UserRole, Order, OrderItem, OrderStatus, PaymentStatus, AuditEvent, InventoryMovement, InventoryMovementType, Product
from app.security import hash_password


def _login(role='admin'):
    email = f'phase48-{role}-{uuid.uuid4().hex[:10]}@example.edu'
    password = 'Phase48-test-password!'
    with SessionLocal() as db:
        db.add(User(full_name=f'Phase 48 {role}', email=email, password_hash=hash_password(password), role=UserRole(role), is_active=True))
        db.commit()
    response = TestClient(app).post('/api/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200, response.text
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


def _make_order():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email.like('phase48-student-%@example.edu')))
        if not user:
            user = User(full_name='Investigation Customer', email=f'phase48-student-{uuid.uuid4().hex[:8]}@example.edu', password_hash=hash_password('Student-password-48!'), role=UserRole('student'), is_active=True)
            db.add(user); db.flush()
        product = db.scalar(select(Product).limit(1))
        if product is None:
            from app.models import Category
            category = Category(name=f'Phase48-{uuid.uuid4().hex[:5]}', slug=f'phase48-{uuid.uuid4().hex[:8]}', item_type='food', is_active=True)
            db.add(category); db.flush()
            product = Product(name='Investigation Test Item', description='test', price=10, stock_quantity=10, category_id=category.id, is_available=True)
            db.add(product); db.flush()
        order = Order(user_id=user.id, status=OrderStatus.PENDING, payment_status=PaymentStatus.PENDING, subtotal=10, gateway_order_id=f'order_{uuid.uuid4().hex}')
        db.add(order); db.flush()
        db.add(OrderItem(order_id=order.id, product_id=product.id, product_name=product.name, unit_price=10, quantity=1, line_total=10))
        db.add(AuditEvent(action='test.order_event', entity_type='order', entity_id=str(order.id), details_json='{"test": true}'))
        db.add(InventoryMovement(product_id=product.id, order_id=order.id, movement_type=InventoryMovementType.RESERVATION, quantity_delta=-1, quantity_before=10, quantity_after=9, reason='Phase 48 test reservation'))
        db.commit(); return order.id


def test_admin_investigation_includes_order_snapshot_and_timeline():
    order_id = _make_order()
    with TestClient(app) as client:
        headers = _login('admin')
        response = client.get(f'/api/admin/orders/{order_id}/investigation', headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['order']['id'] == order_id
        assert body['order']['items'] and body['order']['items'][0]['quantity'] == 1
        assert body['investigation']['audit_event_count'] >= 1
        assert body['investigation']['inventory_movement_count'] >= 1
        assert any(event['kind'] == 'audit' for event in body['investigation']['timeline'])
        assert any(event['kind'] == 'inventory' for event in body['investigation']['timeline'])
        assert 'independently verified' in body['investigation']['payment_evidence']['note']


def test_staff_and_students_cannot_access_investigation():
    order_id = _make_order()
    with TestClient(app) as client:
        assert client.get(f'/api/admin/orders/{order_id}/investigation', headers=_login('staff')).status_code == 403
        assert client.get(f'/api/admin/orders/{order_id}/investigation', headers=_login('student')).status_code == 403


def test_investigation_returns_404_for_unknown_order():
    with TestClient(app) as client:
        response = client.get('/api/admin/orders/987654321/investigation', headers=_login('admin'))
        assert response.status_code == 404


def test_investigation_requires_authentication():
    with TestClient(app) as client:
        assert client.get('/api/admin/orders/1/investigation').status_code == 401
