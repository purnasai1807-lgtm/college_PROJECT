"""Environment-based application settings."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

class Settings(BaseSettings):
    app_name: str = "ACE Canteen"
    app_version: str = "0.6.0"
    environment: str = "development"
    log_level: str = "INFO"
    # SQLite gives a zero-configuration local experience. Set DATABASE_URL to PostgreSQL in deployment.
    database_url: str = "sqlite:///./backend/ace_canteen.db"
    auto_create_tables: bool = True
    seed_demo_data: bool = True
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
    smtp_use_ssl: bool = False  # True for implicit TLS (port 465); otherwise STARTTLS is used
    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    @model_validator(mode="after")
    def validate_security_settings(self):
        if self.access_token_minutes < 1 or self.access_token_minutes > 10080:
            raise ValueError("ACCESS_TOKEN_MINUTES must be between 1 and 10080")
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
