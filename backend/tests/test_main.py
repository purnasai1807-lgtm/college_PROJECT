from fastapi.testclient import TestClient
from app.main import app


def test_homepage_serves_html():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "ACE Canteen" in response.text
        assert "catalogue-grid" in response.text


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["application"] == "ACE Canteen"


def test_ready_endpoint_checks_database():
    with TestClient(app) as client:
        response = client.get("/api/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


def test_info_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/info")
        assert response.status_code == 200
        assert "database" in response.json()["phase"]


def test_catalogue_is_seeded_and_returns_products():
    with TestClient(app) as client:
        categories = client.get("/api/categories")
        products = client.get("/api/products")
        assert categories.status_code == 200
        assert products.status_code == 200
        assert len(categories.json()) >= 3
        assert len(products.json()) >= 9
        assert all(float(product["price"]) > 0 for product in products.json())


def test_catalogue_filters():
    with TestClient(app) as client:
        food = client.get("/api/products", params={"item_type": "food"})
        stationery = client.get("/api/products", params={"item_type": "stationery"})
        search = client.get("/api/products", params={"search": "notebook"})
        assert food.status_code == 200 and food.json()
        assert all(p["item_type"] == "food" for p in food.json())
        assert stationery.status_code == 200 and all(p["item_type"] == "stationery" for p in stationery.json())
        assert any(p["name"] == "Notebook" for p in search.json())


def test_catalogue_summary():
    with TestClient(app) as client:
        response = client.get("/api/catalogue/summary")
        assert response.status_code == 200
        assert response.json()["total_products"] >= 9


def test_unknown_route_returns_404():
    with TestClient(app) as client:
        assert client.get("/route-that-does-not-exist").status_code == 404


def test_student_registration_login_and_me():
    with TestClient(app) as client:
        email = "phase3-student@example.edu"
        # Make the test repeatable when run against the local development database.
        from app.database import SessionLocal
        from app.models import User
        from sqlalchemy import select
        with SessionLocal() as db:
            existing = db.scalar(select(User).where(User.email == email))
            if existing:
                db.delete(existing)
                db.commit()
        registered = client.post("/api/auth/register", json={"full_name": "Test Student", "email": email, "password": "correct-horse-123"})
        assert registered.status_code == 201, registered.text
        assert registered.json()["role"] == "student"
        assert "password_hash" not in registered.json()
        login = client.post("/api/auth/login", json={"email": email, "password": "correct-horse-123"})
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == email


def test_auth_rejects_bad_password_and_duplicate_email():
    with TestClient(app) as client:
        email = "phase3-duplicate@example.edu"
        from app.database import SessionLocal
        from app.models import User
        from sqlalchemy import select
        with SessionLocal() as db:
            existing = db.scalar(select(User).where(User.email == email))
            if existing:
                db.delete(existing)
                db.commit()
        payload = {"full_name": "Another Student", "email": email, "password": "secure-password-123"}
        assert client.post("/api/auth/register", json=payload).status_code == 201
        assert client.post("/api/auth/register", json=payload).status_code == 409
        assert client.post("/api/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401


def test_auth_and_rbac_protect_privileged_routes():
    with TestClient(app) as client:
        assert client.get("/api/auth/me").status_code == 401
        email = "phase3-rbac@example.edu"
        from app.database import SessionLocal
        from app.models import User
        from sqlalchemy import select
        with SessionLocal() as db:
            existing = db.scalar(select(User).where(User.email == email))
            if existing:
                db.delete(existing)
                db.commit()
        assert client.post("/api/auth/register", json={"full_name": "RBAC Student", "email": email, "password": "secure-password-123"}).status_code == 201
        token = client.post("/api/auth/login", json={"email": email, "password": "secure-password-123"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/admin/users", headers=headers).status_code == 403
        assert client.get("/api/staff/dashboard", headers=headers).status_code == 403


def test_admin_can_manage_roles_and_catalogue():
    with TestClient(app) as client:
        from app.database import SessionLocal
        from app.models import User, UserRole
        from app.security import hash_password
        from sqlalchemy import select
        import uuid
        suffix = uuid.uuid4().hex[:8]
        email = f"phase3-admin-{suffix}@example.edu"
        with SessionLocal() as db:
            existing = db.scalar(select(User).where(User.email == email))
            if existing:
                db.delete(existing)
                db.commit()
            admin = User(full_name="Test Admin", email=email, password_hash=hash_password("test-admin-password-123"), role=UserRole.ADMIN, is_active=True)
            db.add(admin)
            db.commit()
        login = client.post("/api/auth/login", json={"email": email, "password": "test-admin-password-123"})
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert client.get("/api/admin/users", headers=headers).status_code == 200
        category = client.post("/api/admin/categories", headers=headers, json={"name": f"Test Bakery {suffix}", "slug": f"test-bakery-{suffix}", "item_type": "food", "description": "Test category"})
        assert category.status_code == 201, category.text
        product = client.post("/api/admin/products", headers=headers, json={"category_id": category.json()["id"], "name": f"Test Bun {suffix}", "description": "Test item", "item_type": "food", "price": "18.00", "stock_quantity": 12, "is_available": True})
        assert product.status_code == 201, product.text
        assert product.json()["name"] == f"Test Bun {suffix}"
        updated_category = client.patch(f"/api/admin/categories/{category.json()['id']}", headers=headers, json={"description": "Updated by admin"})
        assert updated_category.status_code == 200, updated_category.text
        assert updated_category.json()["description"] == "Updated by admin"


def test_phase4_staff_can_create_update_and_archive_products():
    with TestClient(app) as client:
        import uuid
        from app.database import SessionLocal
        from app.models import User, UserRole
        from app.security import hash_password
        from sqlalchemy import select
        suffix = uuid.uuid4().hex[:8]
        email = f"phase4-staff-{suffix}@example.edu"
        with SessionLocal() as db:
            staff = User(full_name="Catalogue Staff", email=email, password_hash=hash_password("test-staff-password-123"), role=UserRole.STAFF, is_active=True)
            db.add(staff)
            db.commit()
        login = client.post("/api/auth/login", json={"email": email, "password": "test-staff-password-123"})
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        categories = client.get("/api/categories?item_type=food").json()
        category_id = categories[0]["id"]
        created = client.post("/api/admin/products", headers=headers, json={"category_id": category_id, "name": f"Phase Four Snack {suffix}", "description": "CRUD test", "item_type": "food", "price": "22.50", "stock_quantity": 7, "is_available": True})
        assert created.status_code == 201, created.text
        product_id = created.json()["id"]
        assert created.json()["category_name"] == categories[0]["name"]
        updated = client.patch(f"/api/admin/products/{product_id}", headers=headers, json={"price": "24.00", "stock_quantity": 5, "is_available": True})
        assert updated.status_code == 200, updated.text
        assert float(updated.json()["price"]) == 24.0
        assert updated.json()["stock_quantity"] == 5
        archived = client.delete(f"/api/admin/products/{product_id}", headers=headers)
        assert archived.status_code == 200, archived.text
        assert archived.json()["is_available"] is False
        assert archived.json()["stock_quantity"] == 0
        visible = client.get("/api/products", params={"search": f"Phase Four Snack {suffix}"})
        assert visible.status_code == 200
        assert all(item["id"] != product_id for item in visible.json())


def test_phase4_staff_cannot_create_categories_and_product_type_must_match_category():
    with TestClient(app) as client:
        import uuid
        from app.database import SessionLocal
        from app.models import User, UserRole
        from app.security import hash_password
        suffix = uuid.uuid4().hex[:8]
        email = f"phase4-staff-rbac-{suffix}@example.edu"
        with SessionLocal() as db:
            db.add(User(full_name="Staff RBAC", email=email, password_hash=hash_password("test-staff-password-123"), role=UserRole.STAFF, is_active=True))
            db.commit()
        token = client.post("/api/auth/login", json={"email": email, "password": "test-staff-password-123"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        category_response = client.post("/api/admin/categories", headers=headers, json={"name": f"Blocked Category {suffix}", "slug": f"blocked-category-{suffix}", "item_type": "food"})
        assert category_response.status_code == 403
        stationery_category = client.get("/api/categories?item_type=stationery").json()[0]
        mismatch = client.post("/api/admin/products", headers=headers, json={"category_id": stationery_category["id"], "name": f"Mismatched Item {suffix}", "item_type": "food", "price": "10.00", "stock_quantity": 1})
        assert mismatch.status_code == 400


def test_catalogue_searches_descriptions_and_categories_and_supports_paging_sorting():
    with TestClient(app) as client:
        description = client.get('/api/products', params={'search': 'Crispy potato-filled snack'})
        category = client.get('/api/products', params={'search': 'Snacks'})
        page = client.get('/api/products', params={'limit': 2, 'offset': 0, 'sort_by': 'price', 'sort_order': 'asc'})
        assert description.status_code == 200 and any(p['name'] == 'Samosa' for p in description.json())
        assert category.status_code == 200 and page.status_code == 200
        assert len(page.json()) == 2
        assert float(page.json()[0]['price']) <= float(page.json()[1]['price'])
        assert client.get('/api/products', params={'limit': 101}).status_code == 422
        assert client.get('/api/products', params={'sort_by': 'sql'}).status_code == 422


def test_password_change_invalidates_existing_access_tokens():
    with TestClient(app) as client:
        import uuid
        email = f'password-change-{uuid.uuid4().hex[:8]}@example.edu'
        assert client.post('/api/auth/register', json={'full_name': 'Password Test', 'email': email, 'password': 'initial-password-123'}).status_code == 201
        login = client.post('/api/auth/login', json={'email': email, 'password': 'initial-password-123'})
        assert login.status_code == 200
        old_token = login.json()['access_token']
        headers = {'Authorization': f'Bearer {old_token}'}
        bad = client.post('/api/auth/change-password', headers=headers, json={'current_password': 'wrong-password', 'new_password': 'new-password-4567'})
        assert bad.status_code == 400
        changed = client.post('/api/auth/change-password', headers=headers, json={'current_password': 'initial-password-123', 'new_password': 'new-password-4567'})
        assert changed.status_code == 200
        assert client.get('/api/auth/me', headers=headers).status_code == 401
        relogin = client.post('/api/auth/login', json={'email': email, 'password': 'new-password-4567'})
        assert relogin.status_code == 200


def test_product_metadata_and_image_url_validation():
    with TestClient(app) as client:
        import uuid
        from app.database import SessionLocal
        from app.models import User, UserRole
        from app.security import hash_password
        suffix = uuid.uuid4().hex[:8]
        email = f'metadata-staff-{suffix}@example.edu'
        with SessionLocal() as db:
            db.add(User(full_name='Metadata Staff', email=email, password_hash=hash_password('metadata-password-123'), role=UserRole.STAFF, is_active=True))
            db.commit()
        token = client.post('/api/auth/login', json={'email': email, 'password': 'metadata-password-123'}).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        category = client.get('/api/categories', params={'item_type': 'food'}).json()[0]
        bad = client.post('/api/admin/products', headers=headers, json={'category_id': category['id'], 'name': 'Unsafe image', 'item_type': 'food', 'price': '12.00', 'image_url': 'javascript:alert(1)'})
        assert bad.status_code == 422
        good = client.post('/api/admin/products', headers=headers, json={'category_id': category['id'], 'name': f'Metadata Item {suffix}', 'item_type': 'food', 'price': '12.00', 'image_url': '/assets/samosa.jpg', 'dietary_info': 'Vegetarian', 'allergens': 'Gluten'})
        assert good.status_code == 201, good.text
        assert good.json()['dietary_info'] == 'Vegetarian'
        assert good.json()['allergens'] == 'Gluten'


def test_admin_can_list_archive_and_reactivate_categories():
    with TestClient(app) as client:
        import uuid
        from app.database import SessionLocal
        from app.models import User, UserRole
        from app.security import hash_password
        suffix = uuid.uuid4().hex[:8]
        email = f'category-admin-{suffix}@example.edu'
        with SessionLocal() as db:
            db.add(User(full_name='Category Admin', email=email, password_hash=hash_password('category-password-123'), role=UserRole.ADMIN, is_active=True))
            db.commit()
        token = client.post('/api/auth/login', json={'email': email, 'password': 'category-password-123'}).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        created = client.post('/api/admin/categories', headers=headers, json={'name': f'Category {suffix}', 'slug': f'category-{suffix}', 'item_type': 'food'})
        assert created.status_code == 201, created.text
        category_id = created.json()['id']
        assert any(c['id'] == category_id for c in client.get('/api/admin/categories', headers=headers).json())
        duplicate = client.post('/api/admin/categories', headers=headers, json={'name': f' CATEGORY {suffix} ', 'slug': f'category-duplicate-{suffix}', 'item_type': 'food'})
        assert duplicate.status_code == 409
        archived = client.patch(f'/api/admin/categories/{category_id}', headers=headers, json={'is_active': False})
        assert archived.status_code == 200 and archived.json()['is_active'] is False
        restored = client.patch(f'/api/admin/categories/{category_id}', headers=headers, json={'is_active': True, 'slug': f'renamed-{suffix}'})
        assert restored.status_code == 200 and restored.json()['slug'] == f'renamed-{suffix}'


def test_login_abuse_protection_throttles_repeated_failures():
    import uuid
    email = f"rate-limit-{uuid.uuid4().hex}@example.edu"
    with TestClient(app) as client:
        for _ in range(5):
            response = client.post("/api/auth/login", json={"email": email, "password": "wrong-password"})
            assert response.status_code == 401
        throttled = client.post("/api/auth/login", json={"email": email, "password": "wrong-password"})
        assert throttled.status_code == 429
        assert "Retry-After" in throttled.headers


def test_database_rejects_invalid_product_price_and_stock():
    from sqlalchemy.exc import IntegrityError
    from app.database import SessionLocal
    from app.models import Category, Product
    from sqlalchemy import select
    with SessionLocal() as db:
        category = db.scalar(select(Category).where(Category.slug == "snacks"))
        assert category is not None
        invalid = Product(category_id=category.id, name="Invalid constraint test", item_type="food", price=0, stock_quantity=-1, is_available=True)
        db.add(invalid)
        try:
            db.commit()
            assert False, "Database accepted invalid price/stock"
        except IntegrityError:
            db.rollback()


def test_seed_is_idempotent():
    from app.database import SessionLocal
    from app.seed import seed_demo_data
    from app.models import Category, Product
    from sqlalchemy import select, func
    with SessionLocal() as db:
        before_categories = db.scalar(select(func.count()).select_from(Category))
        before_products = db.scalar(select(func.count()).select_from(Product))
        seed_demo_data(db)
        after_categories = db.scalar(select(func.count()).select_from(Category))
        after_products = db.scalar(select(func.count()).select_from(Product))
        assert (after_categories, after_products) == (before_categories, before_products)


def test_product_detail_only_returns_available_catalogue_items():
    with TestClient(app) as client:
        notebook = next(p for p in client.get('/api/products', params={'search': 'Notebook'}).json() if p['name'] == 'Notebook')
        detail = client.get(f"/api/products/{notebook['id']}")
        assert detail.status_code == 200
        assert detail.json()['name'] == 'Notebook'
        assert detail.json()['category_name'] == 'Stationery'


def test_archived_products_are_not_exposed_by_public_catalogue_query():
    with TestClient(app) as client:
        import uuid
        from app.database import SessionLocal
        from app.models import User, UserRole
        from app.security import hash_password
        suffix = uuid.uuid4().hex[:8]
        email = f'archive-visibility-{suffix}@example.edu'
        with SessionLocal() as db:
            user = User(full_name='Visibility Staff', email=email, password_hash=hash_password('test-staff-password-123'), role=UserRole.STAFF, is_active=True)
            db.add(user)
            db.commit()
        token = client.post('/api/auth/login', json={'email': email, 'password': 'test-staff-password-123'}).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        category = client.get('/api/categories?item_type=food').json()[0]
        created = client.post('/api/admin/products', headers=headers, json={
            'category_id': category['id'], 'name': f'Archive Visibility {suffix}', 'item_type': 'food',
            'price': '19.00', 'stock_quantity': 2, 'is_available': True
        })
        assert created.status_code == 201, created.text
        product_id = created.json()['id']
        assert client.delete(f'/api/admin/products/{product_id}', headers=headers).status_code == 200
        assert client.get('/api/products', params={'available_only': 'false'}).status_code == 403
        assert client.get(f'/api/products/{product_id}').status_code == 404
        assert client.get('/api/admin/products').status_code == 401
        managed = client.get('/api/admin/products', headers=headers)
        assert managed.status_code == 200
        archived = next(p for p in managed.json() if p['id'] == product_id)
        assert archived['is_available'] is False


def test_archiving_category_hides_its_products_and_reactivation_restores_them():
    with TestClient(app) as client:
        import uuid
        from app.database import SessionLocal
        from app.models import User, UserRole
        from app.security import hash_password
        suffix = uuid.uuid4().hex[:8]
        email = f'category-toggle-{suffix}@example.edu'
        with SessionLocal() as db:
            user = User(full_name='Category Admin', email=email, password_hash=hash_password('test-admin-password-123'), role=UserRole.ADMIN, is_active=True)
            db.add(user)
            db.commit()
        token = client.post('/api/auth/login', json={'email': email, 'password': 'test-admin-password-123'}).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        created_category = client.post('/api/admin/categories', headers=headers, json={
            'name': f'Test Drinks {suffix}', 'slug': f'test-drinks-{suffix}', 'item_type': 'food'
        })
        assert created_category.status_code == 201, created_category.text
        category_id = created_category.json()['id']
        product = client.post('/api/admin/products', headers=headers, json={
            'category_id': category_id, 'name': f'Test Drink {suffix}', 'item_type': 'food',
            'price': '15.00', 'stock_quantity': 4, 'is_available': True
        })
        assert product.status_code == 201, product.text
        product_id = product.json()['id']
        assert client.patch(f'/api/admin/categories/{category_id}', headers=headers, json={'is_active': False}).status_code == 200
        assert all(p['id'] != product_id for p in client.get('/api/products', params={'search': f'Test Drink {suffix}'}).json())
        assert client.get(f'/api/products/{product_id}').status_code == 404
        assert client.patch(f'/api/admin/categories/{category_id}', headers=headers, json={'is_active': True}).status_code == 200
        assert any(p['id'] == product_id for p in client.get('/api/products', params={'search': f'Test Drink {suffix}'}).json())


def test_management_patch_rejects_null_for_required_fields_cleanly():
    with TestClient(app) as client:
        import uuid
        from app.database import SessionLocal
        from app.models import User, UserRole
        from app.security import hash_password
        suffix = uuid.uuid4().hex[:8]
        email = f'null-patch-{suffix}@example.edu'
        with SessionLocal() as db:
            db.add(User(full_name='Patch Admin', email=email, password_hash=hash_password('test-admin-password-123'), role=UserRole.ADMIN, is_active=True))
            db.commit()
        token = client.post('/api/auth/login', json={'email': email, 'password': 'test-admin-password-123'}).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        category = client.get('/api/categories?item_type=food').json()[0]
        product = client.post('/api/admin/products', headers=headers, json={
            'category_id': category['id'], 'name': f'Null Patch {suffix}', 'item_type': 'food',
            'price': '12.00', 'stock_quantity': 3
        })
        assert product.status_code == 201, product.text
        assert client.patch(f"/api/admin/products/{product.json()['id']}", headers=headers, json={'price': None}).status_code == 422
        assert client.patch(f"/api/admin/categories/{category['id']}", headers=headers, json={'name': None}).status_code == 422


def test_legacy_order_endpoint_cannot_bypass_payment():
    import uuid
    with TestClient(app) as client:
        email = f"legacy-order-{uuid.uuid4().hex[:8]}@example.edu"
        assert client.post('/api/auth/register', json={'full_name': 'Legacy Student', 'email': email, 'password': 'legacy-student-password'}).status_code == 201
        token = client.post('/api/auth/login', json={'email': email, 'password': 'legacy-student-password'}).json()['access_token']
        response = client.post('/api/orders', headers={'Authorization': f'Bearer {token}'}, json={'items': [{'product_id': 1, 'quantity': 1}]})
        assert response.status_code == 410
        assert 'payment verification' in response.json()['detail'].lower() or 'pay and place' in response.json()['detail'].lower()


def test_order_status_transition_rules_reject_skipping_queue_steps():
    import uuid
    from app.database import SessionLocal
    from app.models import User, UserRole, Order, OrderStatus, PaymentStatus
    from app.security import hash_password
    with TestClient(app) as client:
        suffix = uuid.uuid4().hex[:8]
        email = f'queue-admin-{suffix}@example.edu'
        with SessionLocal() as db:
            admin = User(full_name='Queue Admin', email=email, password_hash=hash_password('queue-admin-pass-123'), role=UserRole.ADMIN, is_active=True)
            db.add(admin); db.flush()
            order = Order(user_id=admin.id, token_number=7000 + int(suffix[:3], 16), token_date='2099-01-01', status=OrderStatus.PENDING, payment_status=PaymentStatus.PAID, subtotal='10.00')
            db.add(order); db.commit(); order_id = order.id
        token = client.post('/api/auth/login', json={'email': email, 'password': 'queue-admin-pass-123'}).json()['access_token']
        response = client.patch(f"/api/admin/orders/{order_id}/status", headers={'Authorization': f'Bearer {token}'}, json={'status': 'ready'})
        assert response.status_code == 409
        assert 'Cannot change order' in response.json()['detail']


def test_checkout_quote_requires_student_authentication():
    with TestClient(app) as client:
        response = client.post('/api/orders/quote', json={'items': [{'product_id': 1, 'quantity': 1}]})
        assert response.status_code == 401


def test_checkout_quote_uses_server_prices_and_merges_duplicate_lines():
    from app.database import SessionLocal
    from app.models import User
    from sqlalchemy import select
    import uuid
    with TestClient(app) as client:
        email = f'phase5-quote-{uuid.uuid4().hex[:10]}@example.edu'
        registered = client.post('/api/auth/register', json={'full_name': 'Checkout Student', 'email': email, 'password': 'phase5-secure-password'})
        assert registered.status_code == 201, registered.text
        token = client.post('/api/auth/login', json={'email': email, 'password': 'phase5-secure-password'}).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        products = client.get('/api/products', params={'limit': 1}).json()
        assert products
        product = products[0]
        response = client.post('/api/orders/quote', headers=headers, json={'items': [{'product_id': product['id'], 'quantity': 1}, {'product_id': product['id'], 'quantity': 2}]})
        assert response.status_code == 200, response.text
        quote = response.json()
        assert len(quote['items']) == 1
        assert quote['items'][0]['quantity'] == 3
        assert float(quote['subtotal']) == round(float(product['price']) * 3, 2)
        assert quote['currency'] == 'INR'
        assert quote['stock_reserved'] is False


def test_checkout_quote_rejects_non_student_role():
    from app.database import SessionLocal
    from app.models import User, UserRole
    from app.security import hash_password
    import uuid
    with TestClient(app) as client:
        email = f'phase5-staff-{uuid.uuid4().hex[:10]}@example.edu'
        with SessionLocal() as db:
            db.add(User(full_name='Checkout Staff', email=email, password_hash=hash_password('phase5-staff-password'), role=UserRole.STAFF, is_active=True))
            db.commit()
        token_response = client.post('/api/auth/login', json={'email': email, 'password': 'phase5-staff-password'})
        assert token_response.status_code == 200, token_response.text
        response = client.post('/api/orders/quote', headers={'Authorization': f"Bearer {token_response.json()['access_token']}"}, json={'items': [{'product_id': 1, 'quantity': 1}]})
        assert response.status_code == 403


def test_phase6_payment_order_requires_student_auth_and_provider_keys():
    from app.main import settings
    original_id, original_secret = settings.razorpay_key_id, settings.razorpay_key_secret
    settings.razorpay_key_id = ""
    settings.razorpay_key_secret = ""
    try:
        with TestClient(app) as client:
            assert client.post("/api/payments/create-order", json={"items": [{"product_id": 1, "quantity": 1}]}).status_code == 401
            email = "phase6-payment-config@example.edu"
            from app.database import SessionLocal
            from app.models import User
            from sqlalchemy import select
            with SessionLocal() as db:
                existing = db.scalar(select(User).where(User.email == email))
                if existing:
                    db.delete(existing); db.commit()
            assert client.post("/api/auth/register", json={"full_name": "Payment Student", "email": email, "password": "payment-student-password-123"}).status_code == 201
            token = client.post("/api/auth/login", json={"email": email, "password": "payment-student-password-123"}).json()["access_token"]
            response = client.post("/api/payments/create-order", headers={"Authorization": f"Bearer {token}"}, json={"items": [{"product_id": 1, "quantity": 1}]})
            assert response.status_code == 503
            assert "not configured" in response.json()["detail"]
    finally:
        settings.razorpay_key_id, settings.razorpay_key_secret = original_id, original_secret

def test_phase6_payment_verification_rejects_invalid_signature():
    with TestClient(app) as client:
        email = "phase6-invalid-signature@example.edu"
        from app.database import SessionLocal
        from app.models import User, Order, OrderStatus, PaymentStatus
        from app.security import hash_password
        from app.main import settings
        from sqlalchemy import select
        import uuid
        suffix = uuid.uuid4().hex[:8]
        email = f"phase6-invalid-{suffix}@example.edu"
        with SessionLocal() as db:
            user = User(full_name="Payment Verification", email=email, password_hash=hash_password("payment-verification-password-123"))
            db.add(user); db.flush()
            order = Order(user_id=user.id, token_number=9000 + int(suffix[:3], 16), token_date="2099-01-01", status=OrderStatus.PENDING, payment_status=PaymentStatus.PENDING, subtotal="10.00", gateway_order_id=f"order_test_{suffix}")
            db.add(order); db.commit(); user_id = user.id
        token = client.post("/api/auth/login", json={"email": email, "password": "payment-verification-password-123"}).json()["access_token"]
        old_secret = settings.razorpay_key_secret; settings.razorpay_key_secret = "test_secret_for_signature_check"
        try:
            response = client.post("/api/payments/verify", headers={"Authorization": f"Bearer {token}"}, json={"razorpay_order_id": f"order_test_{suffix}", "razorpay_payment_id": "pay_test_invalid", "razorpay_signature": "not-a-valid-signature"})
            assert response.status_code == 400
            assert response.json()["detail"] == "Payment signature is invalid"
        finally:
            settings.razorpay_key_secret = old_secret


def test_phase7_dashboard_removes_development_and_promo_sections():
    with TestClient(app) as client:
        html = client.get('/').text
        for removed in ['DEVELOPMENT STATUS', 'Check application status', 'Ordering + queue enabled', 'Razorpay · Phase 6', 'BUILT AROUND YOUR DAY', 'Live token queue']:
            assert removed not in html
        assert 'catalogue-grid' in html and 'cart-checkout' in html

def test_phase7_staff_queue_only_shows_paid_orders_and_blocks_unpaid_transitions():
    import uuid
    from app.database import SessionLocal
    from app.models import User, UserRole, Order, OrderStatus, PaymentStatus
    from app.security import hash_password
    with TestClient(app) as client:
        suffix = uuid.uuid4().hex[:10]
        email = f'phase7-staff-{suffix}@example.edu'
        with SessionLocal() as db:
            staff = User(full_name='Phase Seven Staff', email=email, password_hash=hash_password('phase7-staff-password'), role=UserRole.STAFF, is_active=True)
            db.add(staff); db.flush()
            order = Order(user_id=staff.id, token_number=8000 + int(suffix[:3], 16), token_date='2099-01-01', status=OrderStatus.PENDING, payment_status=PaymentStatus.PENDING, subtotal='10.00')
            db.add(order); db.commit(); order_id = order.id
        token = client.post('/api/auth/login', json={'email': email, 'password': 'phase7-staff-password'}).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        queue = client.get('/api/admin/orders', headers=headers)
        assert queue.status_code == 200
        assert all(item['payment_status'] == 'paid' for item in queue.json())
        update = client.patch(f'/api/admin/orders/{order_id}/status', headers=headers, json={'status': 'confirmed'})
        assert update.status_code == 409
        assert 'Only paid orders' in update.json()['detail']


def test_phase8_public_queue_is_privacy_preserving_and_has_daily_metrics():
    with TestClient(app) as client:
        response = client.get('/api/queue/overview')
        assert response.status_code == 200, response.text
        payload = response.json()
        assert {'token_date', 'active_orders', 'preparing_tokens', 'ready_tokens', 'queue', 'estimate_minutes_per_order'} <= set(payload)
        assert payload['estimate_minutes_per_order'] == 5
        for token in payload['queue']:
            assert {'token_number', 'status', 'estimated_wait_minutes', 'created_at'} <= set(token)
            assert 'customer_name' not in token and 'customer_email' not in token


def test_phase8_queue_position_requires_auth_and_protects_order_ownership():
    import uuid
    from app.database import SessionLocal
    from app.models import User, Order, OrderStatus, PaymentStatus
    from app.security import hash_password
    with TestClient(app) as client:
        suffix = uuid.uuid4().hex[:10]
        with SessionLocal() as db:
            owner = User(full_name='Queue Owner', email=f'queue-owner-{suffix}@example.edu', password_hash=hash_password('queue-owner-password-123'))
            stranger = User(full_name='Queue Stranger', email=f'queue-stranger-{suffix}@example.edu', password_hash=hash_password('queue-stranger-password-123'))
            db.add_all([owner, stranger]); db.flush()
            order = Order(user_id=owner.id, token_number=7000 + int(suffix[:3], 16), token_date='2099-01-01', status=OrderStatus.PENDING, payment_status=PaymentStatus.PENDING, subtotal='10.00')
            db.add(order); db.commit(); order_id = order.id
        assert client.get(f'/api/orders/{order_id}/queue-position').status_code == 401
        stranger_token = client.post('/api/auth/login', json={'email': f'queue-stranger-{suffix}@example.edu', 'password': 'queue-stranger-password-123'}).json()['access_token']
        forbidden = client.get(f'/api/orders/{order_id}/queue-position', headers={'Authorization': f'Bearer {stranger_token}'})
        assert forbidden.status_code == 403
        owner_token = client.post('/api/auth/login', json={'email': f'queue-owner-{suffix}@example.edu', 'password': 'queue-owner-password-123'}).json()['access_token']
        own = client.get(f'/api/orders/{order_id}/queue-position', headers={'Authorization': f'Bearer {owner_token}'})
        assert own.status_code == 200
        assert own.json()['queue_position'] is None
        assert 'after payment' in own.json()['message']


def test_phase10_staff_workflow_summary_requires_staff_or_admin():
    with TestClient(app) as client:
        assert client.get('/api/staff/workflow-summary').status_code == 401
        import uuid
        email = f'phase10-student-{uuid.uuid4().hex[:10]}@example.edu'
        assert client.post('/api/auth/register', json={'full_name': 'Phase Ten Student', 'email': email, 'password': 'phase10-student-password'}).status_code == 201
        token = client.post('/api/auth/login', json={'email': email, 'password': 'phase10-student-password'}).json()['access_token']
        response = client.get('/api/staff/workflow-summary', headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 403


def test_phase10_staff_workflow_summary_returns_operational_counts():
    import uuid
    from app.database import SessionLocal
    from app.models import User, UserRole, Order, OrderStatus, PaymentStatus
    from app.security import hash_password
    with TestClient(app) as client:
        suffix = uuid.uuid4().hex[:10]
        email = f'phase10-staff-{suffix}@example.edu'
        base_token = 10000 + int(suffix[:5], 16) * 4
        with SessionLocal() as db:
            staff = User(full_name='Phase Ten Staff', email=email, password_hash=hash_password('phase10-staff-password'), role=UserRole.STAFF, is_active=True)
            db.add(staff); db.flush()
            db.add_all([
                Order(user_id=staff.id, token_number=base_token + 1, token_date='2099-01-01', status=OrderStatus.PENDING, payment_status=PaymentStatus.PAID, subtotal='10.00'),
                Order(user_id=staff.id, token_number=base_token + 2, token_date='2099-01-01', status=OrderStatus.PREPARING, payment_status=PaymentStatus.PAID, subtotal='10.00'),
                Order(user_id=staff.id, token_number=base_token + 3, token_date='2099-01-01', status=OrderStatus.READY, payment_status=PaymentStatus.PAID, subtotal='10.00'),
                Order(user_id=staff.id, token_number=base_token + 4, token_date='2099-01-01', status=OrderStatus.PENDING, payment_status=PaymentStatus.PENDING, subtotal='10.00'),
            ])
            db.commit()
        token = client.post('/api/auth/login', json={'email': email, 'password': 'phase10-staff-password'}).json()['access_token']
        response = client.get('/api/staff/workflow-summary', headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload['kitchen_waiting'] >= 1
        assert payload['kitchen_preparing'] >= 1
        assert payload['ready_for_pickup'] >= 1
        assert 'completed_today' in payload and 'paid_orders_today' in payload


def test_phase11_inventory_receipt_waste_threshold_and_ledger():
    with TestClient(app) as client:
        import uuid
        from app.database import SessionLocal
        from app.models import User, UserRole
        from app.security import hash_password
        suffix = uuid.uuid4().hex[:8]
        email = f'inventory-staff-{suffix}@example.edu'
        with SessionLocal() as db:
            db.add(User(full_name='Inventory Staff', email=email, password_hash=hash_password('inventory-password-123'), role=UserRole.STAFF, is_active=True))
            db.commit()
        token = client.post('/api/auth/login', json={'email': email, 'password': 'inventory-password-123'}).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        products = client.get('/api/admin/products', headers=headers)
        assert products.status_code == 200
        product = next(p for p in products.json() if p['name'] == 'Notebook')
        pid, before = product['id'], product['stock_quantity']
        received = client.post('/api/admin/inventory/adjustments', headers=headers, json={'product_id': pid, 'movement_type': 'receipt', 'quantity': 7, 'reason': 'Weekly supplier delivery'})
        assert received.status_code == 201, received.text
        assert received.json()['stock_quantity'] == before + 7
        wasted = client.post('/api/admin/inventory/adjustments', headers=headers, json={'product_id': pid, 'movement_type': 'waste', 'quantity': 2, 'reason': 'Damaged stock write-off'})
        assert wasted.status_code == 201, wasted.text
        assert wasted.json()['stock_quantity'] == before + 5
        too_much = client.post('/api/admin/inventory/adjustments', headers=headers, json={'product_id': pid, 'movement_type': 'waste', 'quantity': 100000, 'reason': 'Invalid write-off'})
        assert too_much.status_code == 409
        threshold = client.patch(f'/api/admin/inventory/products/{pid}/threshold', headers=headers, json={'low_stock_threshold': before + 5})
        assert threshold.status_code == 200 and threshold.json()['is_low_stock'] is True
        ledger = client.get('/api/admin/inventory/movements', headers=headers, params={'product_id': pid, 'limit': 10})
        assert ledger.status_code == 200
        assert {row['movement_type'] for row in ledger.json()} >= {'receipt', 'waste'}
        summary = client.get('/api/admin/inventory/summary', headers=headers)
        assert summary.status_code == 200
        assert any(row['product_id'] == pid for row in summary.json()['low_stock_items'])
        # Phase 12 audit trail records the stock mutation; only admins can read it.
        admin_email = f'inventory-audit-admin-{uuid.uuid4().hex[:8]}@example.edu'
        with SessionLocal() as db:
            db.add(User(full_name='Inventory Audit Admin', email=admin_email, password_hash=hash_password('inventory-admin-password-123'), role=UserRole.ADMIN, is_active=True))
            db.commit()
        admin_token = client.post('/api/auth/login', json={'email': admin_email, 'password': 'inventory-admin-password-123'}).json()['access_token']
        audit = client.get('/api/admin/audit-events', headers={'Authorization': f'Bearer {admin_token}'}, params={'entity_type': 'product', 'limit': 100})
        assert audit.status_code == 200
        assert any(event['action'] == 'inventory.stock_changed' and event['entity_id'] == str(pid) for event in audit.json())


def test_phase11_inventory_routes_require_staff_or_admin():
    with TestClient(app) as client:
        assert client.get('/api/admin/inventory/summary').status_code == 401
        assert client.get('/api/admin/inventory/movements').status_code == 401
        import uuid
        email = f'inventory-student-{uuid.uuid4().hex[:8]}@example.edu'
        assert client.post('/api/auth/register', json={'full_name': 'Inventory Student', 'email': email, 'password': 'inventory-student-password'}).status_code == 201
        token = client.post('/api/auth/login', json={'email': email, 'password': 'inventory-student-password'}).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        assert client.get('/api/admin/inventory/summary', headers=headers).status_code == 403
        assert client.post('/api/admin/inventory/adjustments', headers=headers, json={'product_id': 1, 'movement_type': 'receipt', 'quantity': 2, 'reason': 'Not authorized'}).status_code == 403


def test_phase12_admin_reports_and_audit_trail_are_role_protected_and_work():
    import uuid
    from app.database import SessionLocal
    from app.models import User, UserRole, AuditEvent
    from app.security import hash_password
    from sqlalchemy import select
    with TestClient(app) as client:
        suffix = uuid.uuid4().hex[:10]
        email = f'phase12-admin-{suffix}@example.edu'
        with SessionLocal() as db:
            db.add(User(full_name='Phase Twelve Admin', email=email, password_hash=hash_password('phase12-admin-password'), role=UserRole.ADMIN, is_active=True))
            db.commit()
        token = client.post('/api/auth/login', json={'email': email, 'password': 'phase12-admin-password'}).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        overview = client.get('/api/admin/reports/overview', headers=headers)
        assert overview.status_code == 200, overview.text
        report = overview.json()
        assert {'paid_revenue', 'paid_orders', 'all_orders', 'average_paid_order_value', 'orders_by_status'} <= report.keys()
        daily = client.get('/api/admin/reports/daily-sales', headers=headers)
        assert daily.status_code == 200 and len(daily.json()) >= 1
        assert {'date', 'orders', 'revenue'} <= daily.json()[0].keys()
        top = client.get('/api/admin/reports/top-products', headers=headers)
        assert top.status_code == 200 and isinstance(top.json(), list)
        bad_range = client.get('/api/admin/reports/overview', headers=headers, params={'start_date': '2026-12-31', 'end_date': '2026-01-01'})
        assert bad_range.status_code == 422
        with SessionLocal() as db:
            db.add(AuditEvent(actor_user_id=None, action='test.audit', entity_type='test', entity_id='phase12', details_json='{"ok":true}'))
            db.commit()
        audit = client.get('/api/admin/audit-events', headers=headers, params={'action': 'test.audit'})
        assert audit.status_code == 200 and audit.json()
        assert audit.json()[0]['details'] == {'ok': True}
        assert client.get('/api/admin/reports/overview').status_code == 401


def test_phase12_student_cannot_read_admin_reports_or_audit():
    import uuid
    with TestClient(app) as client:
        email = f'phase12-student-{uuid.uuid4().hex[:8]}@example.edu'
        registered = client.post('/api/auth/register', json={'full_name': 'Phase Twelve Student', 'email': email, 'password': 'phase12-student-password'})
        assert registered.status_code == 201
        token = client.post('/api/auth/login', json={'email': email, 'password': 'phase12-student-password'}).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        assert client.get('/api/admin/reports/overview', headers=headers).status_code == 403
        assert client.get('/api/admin/reports/daily-sales', headers=headers).status_code == 403
        assert client.get('/api/admin/audit-events', headers=headers).status_code == 403


def test_phase13_notifications_are_user_scoped_and_can_be_marked_read():
    from uuid import uuid4
    from app.database import SessionLocal
    from app.models import Notification, User
    from app.security import hash_password

    suffix = uuid4().hex[:10]
    with TestClient(app) as client:
        email_a = f"notify-a-{suffix}@example.edu"
        email_b = f"notify-b-{suffix}@example.edu"
        for email, name in [(email_a, "Notify Student A"), (email_b, "Notify Student B")]:
            response = client.post("/api/auth/register", json={"full_name": name, "email": email, "password": "notification-test-password-123"})
            assert response.status_code == 201, response.text
        login_a = client.post("/api/auth/login", json={"email": email_a, "password": "notification-test-password-123"})
        login_b = client.post("/api/auth/login", json={"email": email_b, "password": "notification-test-password-123"})
        headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}
        headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}
        with SessionLocal() as db:
            user_a = db.query(User).filter_by(email=email_a).one()
            notification = Notification(user_id=user_a.id, notification_type="order_status", title="Ready for pickup", message="Test notification", entity_type="order", entity_id="123")
            db.add(notification)
            db.commit()
            notification_id = notification.id
        inbox_a = client.get("/api/notifications", headers=headers_a)
        assert inbox_a.status_code == 200
        assert inbox_a.json()["unread_count"] == 1
        assert inbox_a.json()["items"][0]["title"] == "Ready for pickup"
        assert client.get("/api/notifications", headers=headers_b).json()["unread_count"] == 0
        assert client.patch(f"/api/notifications/{notification_id}/read", headers=headers_b).status_code == 404
        marked = client.patch(f"/api/notifications/{notification_id}/read", headers=headers_a)
        assert marked.status_code == 200 and marked.json()["is_read"] is True
        assert client.get("/api/notifications", headers=headers_a).json()["unread_count"] == 0
        assert client.post("/api/notifications/read-all", headers=headers_a).json()["marked_read"] == 0


def test_phase13_notifications_require_authentication():
    with TestClient(app) as client:
        assert client.get("/api/notifications").status_code == 401
        assert client.post("/api/notifications/read-all").status_code == 401


def test_phase14_security_headers_are_present():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "default-src 'self'" in response.headers["content-security-policy"]
        assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


def test_phase14_rejects_oversized_declared_request_body():
    with TestClient(app) as client:
        response = client.post("/api/auth/login", headers={"Content-Length": str(1_048_577), "Content-Type": "application/json"}, content="{}")
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_phase14_invalid_content_length_is_rejected():
    with TestClient(app) as client:
        response = client.post("/api/auth/login", headers={"Content-Length": "invalid", "Content-Type": "application/json"}, content="{}")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_CONTENT_LENGTH"


def test_phase15_request_id_is_returned_and_safe():
    with TestClient(app) as client:
        supplied = client.get('/api/health', headers={'X-Request-ID': 'campus-pilot_123'})
        assert supplied.status_code == 200
        assert supplied.headers['x-request-id'] == 'campus-pilot_123'
        invalid = client.get('/api/health', headers={'X-Request-ID': 'bad id\nforged'})
        assert invalid.status_code == 200
        generated = invalid.headers['x-request-id']
        assert generated and generated != 'bad id\nforged'
        assert all(ch.isalnum() or ch in '-_' for ch in generated)


def test_phase15_info_reports_current_phase():
    with TestClient(app) as client:
        response = client.get('/api/info')
        assert response.status_code == 200
        assert response.json()['version'] == '0.7.0'
        assert response.json()['phase'].startswith('1-16')


def test_phase15_production_configuration_requires_explicit_migration_and_no_demo_seed():
    import pytest
    from pydantic import ValidationError
    from app.config import Settings

    common = {
        'environment': 'production',
        'secret_key': 'a-unique-production-secret-that-is-long-enough-123456',
        'auto_create_tables': False,
        'seed_demo_data': False,
        'public_base_url': 'https://canteen.example.edu',
    }
    assert Settings(_env_file=None, **common).environment == 'production'
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**common, 'auto_create_tables': True})
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**common, 'seed_demo_data': True})
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**common, 'secret_key': 'change-this-development-secret-before-deployment'})


def test_phase16_student_favorites_are_persistent_and_student_scoped():
    with TestClient(app) as client:
        email = "phase16-favorite-student@example.edu"
        registered = client.post("/api/auth/register", json={"full_name": "Favorite Student", "email": email, "password": "correct-horse-123"})
        if registered.status_code in (400, 409) and "already" in registered.text.lower():
            from app.database import SessionLocal
            from app.models import User
            from sqlalchemy import select
            with SessionLocal() as db:
                old = db.scalar(select(User).where(User.email == email))
                if old: db.delete(old); db.commit()
            registered = client.post("/api/auth/register", json={"full_name": "Favorite Student", "email": email, "password": "correct-horse-123"})
        assert registered.status_code == 201, registered.text
        token = client.post("/api/auth/login", json={"email": email, "password": "correct-horse-123"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        catalogue = client.get('/api/products')
        assert catalogue.status_code == 200 and catalogue.json()
        product_id = catalogue.json()[0]['id']
        saved = client.post(f'/api/favorites/{product_id}', headers=headers)
        assert saved.status_code == 201, saved.text
        assert client.post(f'/api/favorites/{product_id}', headers=headers).status_code == 201
        listed = client.get('/api/favorites', headers=headers)
        assert listed.status_code == 200
        assert [p['id'] for p in listed.json()].count(product_id) == 1
        assert client.delete(f'/api/favorites/{product_id}', headers=headers).json()['saved'] is False
        assert all(p['id'] != product_id for p in client.get('/api/favorites', headers=headers).json())

def test_phase16_favorites_require_student_role():
    with TestClient(app) as client:
        assert client.get('/api/favorites').status_code == 401


def test_payment_webhook_delivery_is_idempotent():
    import hashlib
    import hmac
    from app.main import settings
    from app.database import SessionLocal
    from app.models import PaymentWebhookEvent
    from sqlalchemy import select, func

    original_secret = settings.razorpay_webhook_secret
    settings.razorpay_webhook_secret = "phase18-test-webhook-secret"
    body = b'{"event":"payment.authorized","payload":{}}'
    signature = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    try:
        with TestClient(app) as client:
            first = client.post("/api/payments/webhook", content=body, headers={"X-Razorpay-Signature": signature, "X-Razorpay-Event-Id": "evt-phase18-idempotency-test"})
            second = client.post("/api/payments/webhook", content=body, headers={"X-Razorpay-Signature": signature, "X-Razorpay-Event-Id": "evt-phase18-idempotency-test"})
            assert first.status_code == 200, first.text
            assert second.status_code == 200, second.text
            assert second.json().get("duplicate") is True
        with SessionLocal() as db:
            rows = db.scalars(select(PaymentWebhookEvent).where(PaymentWebhookEvent.event_id == "evt-phase18-idempotency-test")).all()
            assert len(rows) == 1
    finally:
        settings.razorpay_webhook_secret = original_secret
