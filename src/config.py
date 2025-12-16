"""
Configuration module for the expense bot.
Loads environment variables and provides centralized settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration."""
    
    # Base paths
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data"
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ALLOWED_USER_IDS: list[int] = [
        int(uid.strip()) 
        for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") 
        if uid.strip()
    ]
    
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GPT_MODEL: str = "gpt-4o-mini"
    WHISPER_MODEL: str = "whisper-1"
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        f"sqlite+aiosqlite:///{DATA_DIR}/expenses.db"
    )
    
    # Locale settings
    DEFAULT_CURRENCY: str = os.getenv("DEFAULT_CURRENCY", "MXN")
    TIMEZONE: str = os.getenv("TIMEZONE", "America/Mexico_City")
    
    # Expense categories
    CATEGORIES: dict[str, list[str]] = {
        "🍔 Alimentación": ["comida", "restaurante", "supermercado", "mercado", "lunch", "desayuno", "cena", "café", "cafetería"],
        "🚗 Transporte": ["uber", "didi", "taxi", "gasolina", "gas", "estacionamiento", "peaje", "metro", "camión", "bus"],
        "🏠 Hogar": ["renta", "alquiler", "luz", "agua", "gas", "internet", "teléfono", "mantenimiento"],
        "🛒 Compras": ["amazon", "mercado libre", "tienda", "ropa", "electrónica", "walmart", "costco"],
        "💊 Salud": ["doctor", "médico", "farmacia", "medicinas", "hospital", "dentista", "consulta"],
        "🎬 Entretenimiento": ["netflix", "spotify", "cine", "concierto", "videojuegos", "streaming"],
        "📚 Educación": ["curso", "libro", "escuela", "universidad", "capacitación", "udemy"],
        "💼 Trabajo": ["oficina", "equipo", "herramientas", "software", "dominio", "hosting"],
        "🎁 Otros": []
    }
    
    @classmethod
    def ensure_data_dir(cls) -> None:
        """Create data directory if it doesn't exist."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration. Returns list of missing configs."""
        missing = []
        if not cls.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cls.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        return missing


config = Config()
