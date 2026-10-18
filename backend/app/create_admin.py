"""Create or promote an administrator account from the command line.
Usage: python -m app.create_admin --email admin@college.edu --name "Canteen Admin"
The password is prompted securely and never echoed.
"""
import argparse
from getpass import getpass
from sqlalchemy import select
from app.database import Base, SessionLocal, engine
from app.models import User, UserRole
from app.security import hash_password

parser = argparse.ArgumentParser(description="Create an ACE Canteen administrator")
parser.add_argument("--email", required=True)
parser.add_argument("--name", required=True)
args = parser.parse_args()
password = getpass("Admin password (minimum 12 characters): ")
if len(password) < 12:
    raise SystemExit("Password must contain at least 12 characters.")
# Never create tables outside Alembic on a real database; only bootstrap SQLite for local development.
if engine.dialect.name == "sqlite":
    Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    email = args.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user:
        user.full_name = args.name.strip()
        user.password_hash = hash_password(password)
        user.role = UserRole.ADMIN
        user.is_active = True
        user.must_change_password = False
        user.token_version += 1
    else:
        user = User(full_name=args.name.strip(), email=email, password_hash=hash_password(password), role=UserRole.ADMIN, is_active=True)
        db.add(user)
    db.commit()
print(f"Administrator account ready: {email}")
