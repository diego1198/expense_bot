"""
Email invoice parser using GPT to extract expense data from emails.
"""

import json
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from openai import AsyncOpenAI

from src.config import config
from src.services.gmail_service import EmailMessage


@dataclass
class ParsedInvoice:
    """Parsed invoice data from email."""
    amount: float
    currency: str
    merchant: str
    description: str
    date: datetime
    category: str
    confidence: float
    email_id: str
    original_subject: str


class EmailInvoiceParser:
    """Parse invoice emails using GPT."""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.GPT_MODEL
        
        # Build category list
        self.category_names = [
            cat.split(" ", 1)[1] if " " in cat else cat 
            for cat in config.CATEGORIES.keys()
        ]
    
    async def parse_invoice_email(self, email: EmailMessage) -> Optional[ParsedInvoice]:
        """
        Parse an invoice email to extract expense data.
        
        Args:
            email: EmailMessage object with email data
        
        Returns:
            ParsedInvoice if successful, None otherwise
        """
        categories_list = ", ".join(self.category_names)
        
        system_prompt = f"""Eres un asistente que extrae información de gastos de correos electrónicos de facturas y recibos.
Analiza el correo y extrae la información del gasto.

Categorías disponibles: {categories_list}

Responde SOLO con JSON válido:
{{
    "amount": número (monto total del gasto/factura),
    "currency": "USD" o "MXN" (detecta la moneda del correo),
    "merchant": "nombre del comercio o empresa",
    "description": "descripción breve del gasto",
    "category": "una de las categorías disponibles",
    "date": "YYYY-MM-DD" (fecha de la factura/recibo),
    "confidence": número entre 0 y 1,
    "is_invoice": boolean (true si es una factura/recibo, false si no lo es)
}}

Si el correo NO es una factura o recibo de compra, responde con is_invoice: false.
Si no puedes extraer el monto, usa 0."""

        user_content = f"""
Asunto: {email.subject}
De: {email.sender}

Contenido:
{email.body[:3000]}
"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Check if it's actually an invoice
            if not result.get("is_invoice", True):
                return None
            
            # Check if we got a valid amount
            amount = float(result.get("amount", 0))
            if amount <= 0:
                return None
            
            # Parse date
            try:
                invoice_date = datetime.fromisoformat(result.get("date", ""))
            except:
                invoice_date = email.date or datetime.now()
            
            return ParsedInvoice(
                amount=amount,
                currency=result.get("currency", config.DEFAULT_CURRENCY),
                merchant=result.get("merchant", "Desconocido"),
                description=result.get("description", email.subject[:100]),
                date=invoice_date,
                category=result.get("category", "Otros"),
                confidence=float(result.get("confidence", 0.5)),
                email_id=email.email_id,
                original_subject=email.subject
            )
        
        except Exception as e:
            print(f"Error parsing invoice email: {e}")
            return None


# Singleton instance
email_invoice_parser = EmailInvoiceParser()
