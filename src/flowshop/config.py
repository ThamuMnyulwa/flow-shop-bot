"""Settings from environment configuration (E4). Business values staff can change live in the database."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FLOWSHOP_", extra="ignore")

    env: str = "local"  # local, staging, production
    database_url: str = "postgresql+psycopg://localhost/flowshop"
    secret_key: str = "dev-only-change-me"
    base_url: str = "http://localhost:8000"

    # Channel: "simulator" until go-live, then "whatsapp".
    channel: str = "simulator"
    wa_phone_id: str = ""
    wa_token: str = ""
    wa_app_secret: str = ""
    wa_verify_token: str = ""
    wa_business_number: str = "27000000000"  # used for wa.me links

    # Templates used outside the 24-hour window (L2).
    wa_template_order_update: str = "order_update"
    wa_template_payment_reminder: str = "payment_reminder"
    wa_template_language: str = "en"

    # Scheduled work (E12).
    jobs_token: str = "dev-jobs-token"

    # Time travel for testing expiry and dispatch dates (E8). Never on in production.
    allow_time_travel: bool = False

    # Storage for product images and proof-of-payment files.
    storage_backend: str = "local"  # local or s3
    storage_dir: str = "var/storage"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = ""

    # Website origins allowed to call the public API (W1).
    cors_origins: str = "http://localhost:8888"

    # Staff alerts (A5). Alerts always appear in the admin page; email is optional.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_from: str = ""
    alert_email_to: str = ""

    # Error alerts (O1).
    sentry_dsn: str = ""

    # AI assistant (phase 5). Off unless a key is set and enabled.
    ai_enabled: bool = False
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-4-5-20251001"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
