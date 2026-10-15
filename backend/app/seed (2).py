"""Idempotent sample data for local development."""
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Category, Product, InventoryMovement, InventoryMovementType

DEMO = [
    ("Snacks", "snacks", "food", "Quick bites between classes.", [("Samosa", "Crispy potato-filled snack", "12.00", 80), ("Veg Puff", "Flaky vegetable puff", "20.00", 50), ("Sandwich", "Fresh vegetable sandwich", "35.00", 30)]),
    ("Drinks", "drinks", "food", "Refreshments for your break.", [("Tea", "Hot campus tea", "10.00", 100), ("Coffee", "Hot coffee", "15.00", 80), ("Lime Juice", "Fresh lime drink", "25.00", 35)]),
    ("Stationery", "stationery", "stationery", "Everyday study essentials.", [("Blue Pen", "Blue ballpoint pen", "10.00", 200), ("Notebook", "Single-line notebook", "45.00", 70), ("Pencil", "HB graphite pencil", "5.00", 150)]),
]

def seed_demo_data(db: Session) -> None:
    for name, slug, item_type, description, products in DEMO:
        category = db.scalar(select(Category).where(Category.slug == slug))
        if category is None:
            category = Category(name=name, slug=slug, item_type=item_type, description=description, is_active=True)
            db.add(category)
            db.flush()
        for product_name, product_description, price, stock in products:
            existing = db.scalar(select(Product).where(Product.name == product_name, Product.category_id == category.id))
            if existing is None:
                product = Product(category_id=category.id, name=product_name, description=product_description, item_type=item_type, price=Decimal(price), stock_quantity=stock, is_available=True)
                db.add(product)
                db.flush()
                if stock > 0:
                    db.add(InventoryMovement(product_id=product.id, movement_type=InventoryMovementType.INITIAL, quantity_delta=stock, quantity_before=0, quantity_after=stock, reason="Initial demo stock balance"))
    db.commit()
