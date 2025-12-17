"""
Expense parser service using OpenAI GPT-4o-mini.
Extracts structured expense data from natural language text.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

import pytz
from openai import AsyncOpenAI

from src.config import config


def get_local_now() -> datetime:
    """Get current datetime in user's configured timezone."""
    tz = pytz.timezone(config.TIMEZONE)
    return datetime.now(tz).replace(tzinfo=None)  # Remove tzinfo for SQLite compatibility


@dataclass
class ParsedExpense:
    """Structured expense data extracted from text."""
    amount: float
    currency: str
    description: str
    category: str
    merchant: Optional[str] = None
    date: Optional[datetime] = None
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "amount": self.amount,
            "currency": self.currency,
            "description": self.description,
            "category": self.category,
            "merchant": self.merchant,
            "date": self.date.isoformat() if self.date else None,
            "confidence": self.confidence,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question
        }


class ExpenseParser:
    """
    Parse expense information from natural language using GPT-4o-mini.
    Uses a hybrid approach: simple regex for common patterns, GPT for complex cases.
    """
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.GPT_MODEL
        
        # Build category list for prompt
        self.categories = list(config.CATEGORIES.keys())
        self.category_names = [cat.split(" ", 1)[1] if " " in cat else cat for cat in self.categories]
    
    async def parse(self, text: str, user_timezone: str = "America/Mexico_City") -> ParsedExpense:
        """
        Parse expense from natural language text.
        
        Args:
            text: Natural language expense description
            user_timezone: User's timezone for date parsing
        
        Returns:
            ParsedExpense with extracted data
        """
        # Try simple regex first for common patterns (saves API calls)
        simple_result = self._try_simple_parse(text)
        if simple_result:
            return simple_result
        
        # Use GPT for complex parsing
        return await self._gpt_parse(text, user_timezone)
    
    def _try_simple_parse(self, text: str) -> Optional[ParsedExpense]:
        """
        Try to parse expense with simple regex patterns.
        Returns None if pattern is too complex for regex.
        """
        text_lower = text.lower().strip()
        
        # Common patterns:
        # "gasté 100 en uber" / "100 en uber" / "$100 uber"
        patterns = [
            # "gasté/pagué/compré 100 en descripción"
            r"(?:gast[eé]|pagu[eé]|compr[eé])\s+\$?\s*(\d+(?:[.,]\d{1,2})?)\s*(?:pesos|mxn|usd)?\s+(?:en|de)\s+(.+)",
            # "100 en descripción"
            r"^\$?\s*(\d+(?:[.,]\d{1,2})?)\s*(?:pesos|mxn|usd)?\s+(?:en|de)\s+(.+)",
            # "$100 descripción" (sin "en")
            r"^\$\s*(\d+(?:[.,]\d{1,2})?)\s+(.+)",
            # "100 descripción" o "100.50 descripción" (número + texto)
            r"^(\d+(?:[.,]\d{1,2})?)\s+([a-záéíóúñü].+)$",
            # "descripción 100" o "descripción 100.50" (texto + número al final)
            r"^([a-záéíóúñü][a-záéíóúñü\s]+?)\s+(\d+(?:[.,]\d{1,2})?)$",
        ]
        
        for pattern in patterns:
            match = re.match(pattern, text_lower, re.IGNORECASE)
            if match:
                # Check if this is the last pattern (description first, then amount)
                if pattern == r"^([a-záéíóúñü][a-záéíóúñü\s]+?)\s+(\d+(?:[.,]\d{1,2})?)$":
                    description = match.group(1).strip()
                    amount_str = match.group(2).replace(",", ".")
                else:
                    amount_str = match.group(1).replace(",", ".")
                    description = match.group(2).strip()
                
                try:
                    amount = float(amount_str)
                except ValueError:
                    continue
                
                # Try to match category from keywords
                category = self._match_category(description)
                
                # Extract merchant if recognizable
                merchant = self._extract_merchant(description)
                
                return ParsedExpense(
                    amount=amount,
                    currency=config.DEFAULT_CURRENCY,
                    description=description.capitalize(),
                    category=category,
                    merchant=merchant,
                    date=get_local_now(),
                    confidence=0.7 if category != "Otros" else 0.5
                )
        
        return None
    
    def _match_category(self, text: str) -> str:
        """Match category based on keywords."""
        text_lower = text.lower()
        
        for cat_full, keywords in config.CATEGORIES.items():
            cat_name = cat_full.split(" ", 1)[1] if " " in cat_full else cat_full
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    return cat_name
        
        return "Otros"
    
    def _extract_merchant(self, text: str) -> Optional[str]:
        """Extract merchant name from common vendors."""
        text_lower = text.lower()
        
        known_merchants = [
            "uber", "didi", "rappi", "amazon", "mercado libre", "walmart",
            "costco", "oxxo", "netflix", "spotify", "steam", "apple",
            "google", "microsoft", "starbucks", "mcdonalds", "burger king"
        ]
        
        for merchant in known_merchants:
            if merchant in text_lower:
                return merchant.title()
        
        return None
    
    async def _gpt_parse(self, text: str, user_timezone: str) -> ParsedExpense:
        """Use GPT-4o-mini to parse complex expense descriptions."""
        
        today = get_local_now().strftime("%Y-%m-%d")
        categories_list = ", ".join(self.category_names)
        
        system_prompt = f"""Eres un asistente que extrae información de gastos de texto en español.
Hoy es {today}. La zona horaria del usuario es {user_timezone}.

Categorías disponibles: {categories_list}

Extrae la siguiente información del texto del usuario y responde SOLO con JSON válido:
{{
    "amount": número (monto del gasto, sin símbolos de moneda),
    "currency": "MXN" o "USD" (asume {config.DEFAULT_CURRENCY} si no se especifica),
    "description": "descripción breve del gasto",
    "category": "una de las categorías disponibles",
    "merchant": "nombre del comercio si se menciona, o null",
    "date": "YYYY-MM-DD" (fecha del gasto, usa hoy si dice "hoy", ayer si dice "ayer", etc.),
    "confidence": número entre 0 y 1 indicando tu confianza en la extracción,
    "needs_clarification": boolean si necesitas más información,
    "clarification_question": "pregunta al usuario si needs_clarification es true, o null"
}}

Si no puedes extraer un monto, usa 0 y marca needs_clarification como true.
Si el texto no parece ser un gasto, responde con needs_clarification: true."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Parse date if provided
            expense_date = None
            if result.get("date"):
                try:
                    expense_date = datetime.fromisoformat(result["date"])
                except ValueError:
                    expense_date = get_local_now()
            
            return ParsedExpense(
                amount=float(result.get("amount", 0)),
                currency=result.get("currency", config.DEFAULT_CURRENCY),
                description=result.get("description", text[:100]),
                category=result.get("category", "Otros"),
                merchant=result.get("merchant"),
                date=expense_date or get_local_now(),
                confidence=float(result.get("confidence", 0.5)),
                needs_clarification=result.get("needs_clarification", False),
                clarification_question=result.get("clarification_question")
            )
            
        except Exception as e:
            # Fallback if GPT fails
            return ParsedExpense(
                amount=0,
                currency=config.DEFAULT_CURRENCY,
                description=text[:100],
                category="Otros",
                date=get_local_now(),
                confidence=0.0,
                needs_clarification=True,
                clarification_question=f"No pude procesar tu mensaje. ¿Podrías indicar el monto y descripción del gasto? (Error: {str(e)[:50]})"
            )


# Singleton instance
expense_parser = ExpenseParser()
