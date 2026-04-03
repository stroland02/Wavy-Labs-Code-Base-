from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url:          str = "sqlite:///./dev.db"
    license_hmac_secret:   str = "CHANGE_ME_IN_PRODUCTION"
    stripe_secret_key:              str = ""
    stripe_webhook_secret:          str = ""
    # Pro — both billing intervals
    stripe_pro_monthly_price_id:    str = ""
    stripe_pro_annual_price_id:     str = ""
    # Studio — both billing intervals
    stripe_studio_monthly_price_id: str = ""
    stripe_studio_annual_price_id:  str = ""
    resend_api_key:                 str = ""
    email_from:                     str = "licenses@wavylab.net"

    @property
    def pro_price_ids(self) -> set[str]:
        return {p for p in (self.stripe_pro_monthly_price_id,
                            self.stripe_pro_annual_price_id) if p}

    @property
    def studio_price_ids(self) -> set[str]:
        return {p for p in (self.stripe_studio_monthly_price_id,
                            self.stripe_studio_annual_price_id) if p}
    app_env:               str = "development"
    app_host:              str = "0.0.0.0"
    app_port:              int = 8000
    allowed_origins:       str = "http://localhost:3000"

    # ── Supabase (account-based auth) ──────────────────────────────────────
    # Set these via environment variables or .env file to enable account login.
    # supabase_anon_key   = public anon key (safe to expose)
    # supabase_service_key = service_role key (keep secret — server-side only)
    supabase_url:         str = ""
    supabase_anon_key:    str = ""
    supabase_service_key: str = ""

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
