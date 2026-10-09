from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # Chaine de fournisseurs d'IA essayes dans l'ordre (le premier configure et disponible repond)
    # Valeurs : gemini, groq, openrouter, mistral, ollama, anthropic
    LLM_PROVIDERS: str = "gemini,groq,openrouter,mistral"
    # Ancien reglage a un seul fournisseur, utilise si LLM_PROVIDERS est vide
    LLM_PROVIDER: str = ""
    # Vide = le SDK Anthropic cherche les identifiants dans l'environnement
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-opus-5-5"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"
    # Modeles essayes dans l'ordre si le principal est surcharge ou indisponible
    GEMINI_FALLBACK_MODELS: str = "gemini-3.1-flash-lite,gemini-3.8-flash"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "google/gemma-4-31b-it:free"
    OPENROUTER_FALLBACK_MODELS: str = "nvidia/nemotron-3-super-120b-a12b:free"
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral-small-latest"
    # Modele local (https://ollama.com), sans cle ni quota ; necessite une machine assez puissante
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:8b"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Comptes : liens envoyes par email, connexion Google
    FRONTEND_URL: str = "http://localhost:5173"
    REQUIRE_EMAIL_VERIFICATION: bool = True
    GOOGLE_CLIENT_ID: str = ""

    # Emails : console (le message est ecrit dans les logs) ou smtp
    MAIL_BACKEND: Literal["console", "smtp"] = "console"
    MAIL_FROM: str = "CVGen <no-reply@localhost>"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True

    @property
    def llm_provider_chain(self) -> list[str]:
        brut = self.LLM_PROVIDERS or self.LLM_PROVIDER or "gemini"
        return [p.strip().lower() for p in brut.split(",") if p.strip()]

    @property
    def openrouter_fallback_list(self) -> list[str]:
        return [m.strip() for m in self.OPENROUTER_FALLBACK_MODELS.split(",") if m.strip()]

    @property
    def gemini_fallback_list(self) -> list[str]:
        return [m.strip() for m in self.GEMINI_FALLBACK_MODELS.split(",") if m.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
