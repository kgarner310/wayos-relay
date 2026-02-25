from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "sqlite:///serviceinbox.db"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_verify_signature: bool = False  # Set True in production

    # IMAP (inbound email)
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    imap_folder: str = "INBOX"
    imap_poll_interval_seconds: int = 30

    # SMTP (outbound email)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "ABC Insurance Agency"
    smtp_from_email: str = ""

    # App
    app_title: str = "ServiceInbox Lite"
    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    secret_key: str = "change-me-in-production"

    # Digest
    digest_schedule: str = "08:00,12:00,16:00"  # comma-separated HH:MM (local time)
    digest_recipients: str = ""  # comma-separated emails to receive digests
    digest_timezone: str = "America/New_York"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @property
    def imap_configured(self) -> bool:
        return bool(self.imap_host and self.imap_user and self.imap_password)

    @property
    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token)


settings = Settings()
