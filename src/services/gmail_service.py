"""
Gmail IMAP service for monitoring invoice emails.
Uses App Password authentication - no OAuth required.
"""

import imaplib
import email
from email.header import decode_header
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass
import re

import pytz

from src.config import config


def get_local_now() -> datetime:
    """Get current datetime in user's configured timezone."""
    tz = pytz.timezone(config.TIMEZONE)
    return datetime.now(tz).replace(tzinfo=None)  # Remove tzinfo for SQLite compatibility


@dataclass
class EmailMessage:
    """Email message data."""
    email_id: str
    subject: str
    sender: str
    date: datetime
    body: str


class GmailIMAPService:
    """Service for connecting to Gmail via IMAP."""
    
    IMAP_SERVER = "imap.gmail.com"
    IMAP_PORT = 993
    
    # Keywords to identify invoice/receipt emails
    INVOICE_KEYWORDS = [
        "factura", "invoice", "recibo", "receipt", "payment",
        "orden", "order", "compra", "purchase", "confirmación",
        "confirmation", "cargo", "charge", "pago", "paid",
        "suscripción", "subscription", "renovación", "renewal"
    ]
    
    def __init__(self, email_address: str, app_password: str):
        """
        Initialize IMAP connection.
        
        Args:
            email_address: Gmail address
            app_password: Google App Password (NOT regular password)
        """
        self.email_address = email_address
        self.app_password = app_password
        self.connection: Optional[imaplib.IMAP4_SSL] = None
    
    def connect(self) -> bool:
        """Connect to Gmail IMAP server."""
        try:
            self.connection = imaplib.IMAP4_SSL(self.IMAP_SERVER, self.IMAP_PORT)
            self.connection.login(self.email_address, self.app_password)
            return True
        except imaplib.IMAP4.error as e:
            print(f"IMAP login failed: {e}")
            return False
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from IMAP server."""
        if self.connection:
            try:
                self.connection.logout()
            except:
                pass
            self.connection = None
    
    def _decode_header_value(self, value: str) -> str:
        """Decode email header value."""
        if not value:
            return ""
        
        decoded_parts = decode_header(value)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or 'utf-8', errors='ignore'))
            else:
                result.append(part)
        return ' '.join(result)
    
    def _get_email_body(self, msg) -> str:
        """Extract email body from message."""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            body = payload.decode(charset, errors='ignore')
                            break
                    except:
                        continue
                elif content_type == "text/html" and not body:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            body = payload.decode(charset, errors='ignore')
                    except:
                        continue
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='ignore')
            except:
                body = str(msg.get_payload())
        
        # Clean HTML tags if present
        body = re.sub(r'<[^>]+>', ' ', body)
        body = re.sub(r'\s+', ' ', body).strip()
        
        return body[:3000]  # Limit size
    
    def _is_invoice_email(self, subject: str, sender: str) -> bool:
        """Check if email is likely an invoice/receipt."""
        text = f"{subject} {sender}".lower()
        
        for keyword in self.INVOICE_KEYWORDS:
            if keyword in text:
                return True
        
        return False
    
    def get_unread_emails(self, folder: str = "INBOX", limit: int = 20) -> List[EmailMessage]:
        """
        Get unread emails from folder.
        
        Args:
            folder: Email folder to check
            limit: Maximum emails to fetch
        
        Returns:
            List of EmailMessage objects
        """
        if not self.connection:
            if not self.connect():
                return []
        
        emails = []
        
        try:
            self.connection.select(folder)
            
            # Search for unread emails
            status, messages = self.connection.search(None, 'UNSEEN')
            
            if status != 'OK':
                return []
            
            email_ids = messages[0].split()
            
            # Get latest emails (up to limit)
            for email_id in email_ids[-limit:]:
                try:
                    status, msg_data = self.connection.fetch(email_id, '(RFC822)')
                    
                    if status != 'OK':
                        continue
                    
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    
                    subject = self._decode_header_value(msg.get('Subject', ''))
                    sender = self._decode_header_value(msg.get('From', ''))
                    date_str = msg.get('Date', '')
                    
                    # Parse date
                    try:
                        date = get_local_now()  # Use local timezone
                    except:
                        date = get_local_now()
                    
                    body = self._get_email_body(msg)
                    
                    emails.append(EmailMessage(
                        email_id=email_id.decode() if isinstance(email_id, bytes) else str(email_id),
                        subject=subject,
                        sender=sender,
                        date=date,
                        body=body
                    ))
                
                except Exception as e:
                    print(f"Error processing email {email_id}: {e}")
                    continue
        
        except Exception as e:
            print(f"Error fetching emails: {e}")
        
        return emails
    
    def get_unread_invoices(self, limit: int = 20) -> List[EmailMessage]:
        """Get unread emails that look like invoices."""
        all_emails = self.get_unread_emails(limit=limit)
        
        invoices = [
            email for email in all_emails
            if self._is_invoice_email(email.subject, email.sender)
        ]
        
        return invoices
    
    def mark_as_read(self, email_id: str) -> bool:
        """Mark an email as read."""
        if not self.connection:
            return False
        
        try:
            email_id_bytes = email_id.encode() if isinstance(email_id, str) else email_id
            self.connection.store(email_id_bytes, '+FLAGS', '\\Seen')
            return True
        except Exception as e:
            print(f"Error marking as read: {e}")
            return False


def create_imap_service(email_address: str, app_password: str) -> GmailIMAPService:
    """Factory function to create IMAP service."""
    return GmailIMAPService(email_address, app_password)
