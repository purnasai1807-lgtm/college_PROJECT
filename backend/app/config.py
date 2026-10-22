"""Environment-based application settings."""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from sqlalchemy.engine import make_url

class Settings(BaseSettings):
    app_name: str = "ACE Canteen"
    app_version: str = "0.7.0"
    environment: str = "development"
    log_level: str = "INFO"
    # SQLite gives a zero-configuration local experience. Set DATABASE_URL to PostgreSQL in deployment.
    database_url: str = "sqlite:///./backend/ace_canteen.db"
    auto_create_tables: bool = True
    seed_demo_data: bool = False
    secret_key: str = "change-this-development-secret-before-deployment"
    access_token_minutes: int = 720
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    payment_currency: str = "INR"
    # Public base URL used in emailed links (no trailing slash), e.g. https://canteen.example.edu
    public_base_url: str = "http://127.0.0.1:8000"
    password_reset_minutes: int = 30
    # SMTP is optional. Without it, password-reset emails are only logged in development.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_ssl: bool = False
    email_order_ready: bool = True  # email the student when their order is ready (needs SMTP in production)
    # Canteen hours (24h HH:MM, in CANTEEN_TIMEZONE). Leave both empty for "always open, no pickup slots".
    canteen_open_time: str = ""
    canteen_close_time: str = ""
    canteen_timezone: str = "Asia/Kolkata"
    canteen_open_days: str = "0,1,2,3,4,5"  # Monday=0 ... Sunday=6
    pickup_slot_minutes: int = 15
    pickup_slot_capacity: int = 10  # max orders per pickup slot
    pickup_min_lead_minutes: int = 10
    # Optional shared store for login/reset throttling so several app workers share the same counters.
    redis_url: str = ""  # True for implicit TLS (port 465); otherwise STARTTLS is used
    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    @model_validator(mode="after")
    def resolve_relative_sqlite_path(self):
        """Resolve local SQLite paths from the repository root, not the shell cwd."""
        url = make_url(self.database_url)
        if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
            database_path = Path(url.database)
            if not database_path.is_absolute():
                project_root = Path(__file__).resolve().parents[2]
                database_path = (project_root / database_path).resolve()
                self.database_url = url.set(database=str(database_path)).render_as_string(hide_password=False)
        return self

    @model_validator(mode="after")
    def validate_security_settings(self):
        if self.access_token_minutes < 1 or self.access_token_minutes > 10080:
            raise ValueError("ACCESS_TOKEN_MINUTES must be between 1 and 10080")
        if bool(self.canteen_open_time) != bool(self.canteen_close_time):
            raise ValueError("Set both CANTEEN_OPEN_TIME and CANTEEN_CLOSE_TIME, or neither")
        if self.canteen_open_time:
            from datetime import time as _t
            from zoneinfo import ZoneInfo
            try:
                o = _t.fromisoformat(self.canteen_open_time); c = _t.fromisoformat(self.canteen_close_time)
                ZoneInfo(self.canteen_timezone)
                days = {int(x) for x in self.canteen_open_days.split(",") if x.strip()}
            except Exception:
                raise ValueError("Canteen hours must be HH:MM, CANTEEN_TIMEZONE a valid zone, CANTEEN_OPEN_DAYS like 0,1,2,3,4,5")
            if o >= c or not days or any(d < 0 or d > 6 for d in days):
                raise ValueError("CANTEEN_OPEN_TIME must be before CANTEEN_CLOSE_TIME and open days must be 0-6")
        if not 5 <= self.pickup_slot_minutes <= 120 or self.pickup_slot_capacity < 1 or not 0 <= self.pickup_min_lead_minutes <= 240:
            raise ValueError("Invalid pickup slot settings")
        if self.password_reset_minutes < 5 or self.password_reset_minutes > 120:
            raise ValueError("PASSWORD_RESET_MINUTES must be between 5 and 120")
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        if self.environment.lower() in {"production", "prod"}:
            if self.secret_key == "change-this-development-secret-before-deployment":
                raise ValueError("Set a unique SECRET_KEY before running in production")
            if not self.auto_create_tables:
                # Production schemas must be changed deliberately through Alembic migrations.
                pass
            else:
                raise ValueError("AUTO_CREATE_TABLES must be false in production; run Alembic migrations explicitly")
            if self.seed_demo_data:
                raise ValueError("SEED_DEMO_DATA must be false in production")
            if not self.public_base_url.startswith("https://"):
                raise ValueError("PUBLIC_BASE_URL must be an https:// URL in production")
        return self

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
