from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # development | production : en production, la configuration est verifiee au demarrage
    ENV: Literal["development", "production"] = "development"

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
    # Version des conditions d'utilisation acceptees a l'inscription (a changer a chaque mise a jour)
    CGU_VERSION: str = "2026-11-01"
    # Adresse du support : en "Repondre a" des emails et dans les messages de securite
    SUPPORT_EMAIL: str = ""

    # Emails : console (le message est ecrit dans les logs), brevo (API HTTPS) ou smtp.
    # L'offre gratuite de Render bloque les ports SMTP : y utiliser brevo.
    MAIL_BACKEND: Literal["console", "brevo", "smtp"] = "console"
    MAIL_FROM: str = "Apply <no-reply@localhost>"
    BREVO_API_KEY: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True

    # --- Plans et quotas mensuels ---
    FREE_GENERATIONS: int = 3
    FREE_ANALYSES: int = 10
    FREE_IMPORTS: int = 3
    PRO_GENERATIONS: int = 50
    PRO_ANALYSES: int = 150
    PRO_IMPORTS: int = 20

    # --- Stripe (cartes bancaires, abonnement mensuel) ---
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    # Optionnel : prix cree dans le tableau de bord Stripe (sinon prix ci-dessous, en centimes)
    STRIPE_PRICE_ID: str = ""
    PRO_STRIPE_PRICES: str = "eur:799,usd:899,gbp:699"
    # TVA/taxes automatiques : necessite d'activer Stripe Tax dans le tableau de bord
    STRIPE_AUTOMATIC_TAX: bool = False

    # --- Flutterwave (MTN Mobile Money, Orange Money...) : pass Pro de N jours ---
    FLUTTERWAVE_SECRET_KEY: str = ""
    FLUTTERWAVE_WEBHOOK_HASH: str = ""
    MOMO_PRICES: str = "XAF:3000,XOF:3000"
    MOMO_DAYS: int = 30

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


    def verifier_production(self) -> list[str]:
        """Erreurs de configuration bloquantes en production (liste vide si tout va bien)."""
        erreurs = []
        if len(self.SECRET_KEY) < 32 or "changez" in self.SECRET_KEY.lower():
            erreurs.append("SECRET_KEY doit etre une valeur aleatoire d'au moins 32 caracteres (openssl rand -hex 32)")
        if not self.FRONTEND_URL.startswith("https://"):
            erreurs.append("FRONTEND_URL doit etre en https:// en production")
        if any(o.startswith("http://") for o in self.cors_origins_list):
            erreurs.append("CORS_ORIGINS ne doit contenir que des origines https:// en production")
        if self.REQUIRE_EMAIL_VERIFICATION and self.MAIL_BACKEND == "console":
            erreurs.append("MAIL_BACKEND=brevo ou smtp est requis : sinon les utilisateurs ne recoivent pas l'email de confirmation")
        if self.MAIL_BACKEND == "brevo" and not self.BREVO_API_KEY:
            erreurs.append("BREVO_API_KEY est requis avec MAIL_BACKEND=brevo")
        if self.MAIL_BACKEND == "smtp" and not self.SMTP_HOST:
            erreurs.append("SMTP_HOST est requis avec MAIL_BACKEND=smtp")
        if self.MAIL_BACKEND != "console" and "@localhost" in self.MAIL_FROM:
            erreurs.append("MAIL_FROM doit etre une adresse d'expedition validee, ex. Apply <adresse@exemple.com>")
        if self.STRIPE_SECRET_KEY and not self.STRIPE_WEBHOOK_SECRET:
            erreurs.append("STRIPE_WEBHOOK_SECRET est requis avec Stripe (renouvellements, resiliations)")
        if self.FLUTTERWAVE_SECRET_KEY and not self.FLUTTERWAVE_WEBHOOK_HASH:
            erreurs.append("FLUTTERWAVE_WEBHOOK_HASH est requis avec Flutterwave")
        return erreurs


settings = Settings()
