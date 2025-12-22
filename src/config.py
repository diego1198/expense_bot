"""
Configuration module for the expense bot.
Loads environment variables and provides centralized settings.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """Application configuration."""
    
    # Base paths
    BASE_DIR = Path(__file__).resolve().parent.parent
    
    # Data directory - use RAILWAY_VOLUME_MOUNT_PATH if available (for persistent storage)
    _volume_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "")
    if _volume_path:
        DATA_DIR = Path(_volume_path)
    else:
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
    
    # Database - always use DATA_DIR for the path (ignore DATABASE_URL env var for SQLite)
    # This ensures the database is always in the correct persistent location
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DATA_DIR.absolute()}/expenses.db"
    
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

    # Income categories
    INCOME_CATEGORIES: dict[str, list[str]] = {
        "💵 Sueldo": ["sueldo", "salario", "pago mensual", "quincena", "remuneración"],
        "💸 Préstamo": ["préstamo", "prestamo", "crédito", "deuda", "abono préstamo"],
        "📈 Inversión": ["inversión", "retorno", "ganancia", "dividendo", "rendimiento", "interés"],
        "💰 Otros ingresos": ["ingreso", "extra", "venta", "regalo", "bono", "premio"]
    }
    
    @classmethod
    def ensure_data_dir(cls) -> None:
        """Create data directory if it doesn't exist."""
        logger.info(f"📂 Ensuring data directory exists: {cls.DATA_DIR}")
        logger.info(f"📂 DATA_DIR absolute path: {cls.DATA_DIR.absolute()}")
        try:
            cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"✅ Data directory ready: {cls.DATA_DIR}")
            logger.info(f"✅ Directory exists: {cls.DATA_DIR.exists()}")
            logger.info(f"✅ Is writable: {os.access(cls.DATA_DIR, os.W_OK)}")
        except Exception as e:
            logger.error(f"❌ Failed to create data directory: {e}")
            raise
    
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
