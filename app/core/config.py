from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # Fournisseur du modele de langage : anthropic | gemini | groq
    LLM_PROVIDER: Literal["anthropic", "gemini", "groq"] = "anthropic"
    # Vide = le SDK Anthropic cherche les identifiants dans l'environnement
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-opus-5-5"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"
    # Modeles essayes dans l'ordre si le principal est surcharge ou indisponible
    GEMINI_FALLBACK_MODELS: str = "gemini-3.1-flash-lite,gemini-3.8-flash"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def gemini_fallback_list(self) -> list[str]:
        return [m.strip() for m in self.GEMINI_FALLBACK_MODELS.split(",") if m.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
