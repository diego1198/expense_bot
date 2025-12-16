"""
Database models for the expense tracking bot.
Uses SQLAlchemy 2.0 async with SQLite.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, 
    Float, 
    Boolean, 
    DateTime, 
    ForeignKey, 
    Text,
    Integer
)
from sqlalchemy.orm import (
    DeclarativeBase, 
    Mapped, 
    mapped_column, 
    relationship
)


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class User(Base):
    """User model to store Telegram user information."""
    
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_currency: Mapped[str] = mapped_column(String(10), default="MXN")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    expenses: Mapped[list["Expense"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"


class Category(Base):
    """Expense categories."""
    
    __tablename__ = "categories"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    emoji: Mapped[str] = mapped_column(String(10), default="💰")
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list of keywords
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    expenses: Mapped[list["Expense"]] = relationship(back_populates="category")
    
    def __repr__(self) -> str:
        return f"<Category(id={self.id}, name={self.name})>"


class Expense(Base):
    """Main expense model."""
    
    __tablename__ = "expenses"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="MXN")
    description: Mapped[str] = mapped_column(String(500))
    merchant: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Source of the expense record
    source: Mapped[str] = mapped_column(String(50), default="telegram_text")  # telegram_text, telegram_voice, email
    
    # Confirmation status
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pending: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Timestamps
    expense_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Original message for reference
    original_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="expenses")
    category: Mapped[Optional["Category"]] = relationship(back_populates="expenses")
    
    def __repr__(self) -> str:
        return f"<Expense(id={self.id}, amount={self.amount}, description={self.description[:30]})>"
    
    @property
    def formatted_amount(self) -> str:
        """Return formatted amount with currency."""
        return f"${self.amount:,.2f} {self.currency}"


class PendingConfirmation(Base):
    """Store pending expense confirmations for callback handling."""
    
    __tablename__ = "pending_confirmations"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id"), index=True)
    message_id: Mapped[int] = mapped_column(Integer)  # Telegram message ID for editing
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    
    def __repr__(self) -> str:
        return f"<PendingConfirmation(id={self.id}, expense_id={self.expense_id})>"
