"""
Email invoice parser using GPT to extract expense data from emails.
"""

import json
import io
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

import pdfplumber
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


def extract_text_from_pdf(pdf_data: bytes) -> str:
    """Extract text content from a PDF file."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
            text_parts = []
            for page in pdf.pages[:5]:  # Limit to first 5 pages
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n".join(text_parts)[:4000]  # Limit total size
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        return ""


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
        
        system_prompt = f"""Eres un asistente que extrae información de gastos de correos electrónicos.
Analiza el correo y el contenido del PDF adjunto (si existe) para extraer la información del gasto.

Tipos de correos que puedes recibir:
1. FACTURAS ELECTRÓNICAS (SRI Ecuador) - El monto está en el PDF adjunto
2. NOTIFICACIONES DE TARJETA DE CRÉDITO (Diners, Visa, Mastercard, Blu) - Busca "Valor" o monto en el correo
3. NOTIFICACIONES DE TRANSFERENCIA (Deuna, bancos) - Busca "Monto" o "Pagaste $X"
4. RECIBOS DE COMPRA - Confirmaciones de pedidos

Categorías disponibles: {categories_list}

Responde SOLO con JSON válido:
{{
    "amount": número (monto del gasto - busca "Valor", "Monto", "Total", "$X"),
    "currency": "USD" (en Ecuador siempre es USD),
    "merchant": "nombre del comercio/establecimiento/beneficiario",
    "description": "descripción breve del gasto",
    "category": "una de las categorías disponibles",
    "date": "YYYY-MM-DD" (fecha del gasto),
    "confidence": número entre 0 y 1,
    "is_invoice": boolean (true si es un gasto válido)
}}

IMPORTANTE: 
- En notificaciones de tarjeta, el comercio está en "Establecimiento"
- En Deuna, el comercio está en "Nombre del beneficiario"  
- El monto puede tener formato "76,04" (coma) o "76.04" (punto)
- Si no puedes extraer el monto, usa 0

        # Extract PDF content if available
        pdf_content = ""
        if email.attachments:
            for attachment in email.attachments:
                if attachment.filename.lower().endswith('.pdf'):
                    pdf_text = extract_text_from_pdf(attachment.data)
                    if pdf_text:
                        pdf_content = f"\n\n--- CONTENIDO DEL PDF ({attachment.filename}) ---\n{pdf_text}"
                        break  # Use first PDF found

        user_content = f"""
Asunto: {email.subject}
De: {email.sender}

Contenido del correo:
{email.body[:2000]}
{pdf_content}
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
