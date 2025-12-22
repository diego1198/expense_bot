"""
Repository pattern for database operations.
Provides CRUD operations for all models.
"""

import json
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import select, func, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import User, Category, Expense, PendingConfirmation
from src.config import config


class UserRepository:
    """Repository for User operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Get user by Telegram ID."""
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()
    
    async def create(
        self, 
        telegram_id: int, 
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> User:
        """Create a new user."""
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            default_currency=config.DEFAULT_CURRENCY
        )
        self.session.add(user)
        await self.session.flush()
        return user
    
    async def get_or_create(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> tuple[User, bool]:
        """Get existing user or create new one. Returns (user, created)."""
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            return user, False
        user = await self.create(telegram_id, username, first_name, last_name)
        return user, True

    async def update_email_credentials(
        self,
        telegram_id: int,
        email_address: str,
        app_password: str
    ) -> Optional[User]:
        """Update user's email credentials for IMAP access."""
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.email_address = email_address
            user.email_app_password = app_password
            await self.session.flush()
        return user
    
    async def clear_email_credentials(self, telegram_id: int) -> bool:
        """Remove user's email credentials."""
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.email_address = None
            user.email_app_password = None
            user.email_auto_check = False
            await self.session.flush()
            return True
        return False
    
    async def set_email_auto_check(self, telegram_id: int, enabled: bool) -> bool:
        """Enable or disable automatic email checking."""
        user = await self.get_by_telegram_id(telegram_id)
        if user and user.email_address:
            user.email_auto_check = enabled
            await self.session.flush()
            return True
        return False
    
    async def set_email_check_interval(self, telegram_id: int, minutes: int) -> bool:
        """Set the email check interval in minutes."""
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.email_check_interval = minutes
            await self.session.flush()
            return True
        return False
    
    async def update_email_last_checked(self, user_id: int) -> None:
        """Update the last checked timestamp for a user."""
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.email_last_checked = datetime.utcnow()
            await self.session.flush()
    
    async def get_users_with_auto_check(self) -> Sequence[User]:
        """Get all users with automatic email checking enabled."""
        result = await self.session.execute(
            select(User).where(
                and_(
                    User.email_auto_check == True,
                    User.email_address.isnot(None),
                    User.email_app_password.isnot(None),
                    User.is_active == True
                )
            )
        )
        return result.scalars().all()


class CategoryRepository:
    """Repository for Category operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_all(self) -> Sequence[Category]:
        """Get all active categories."""
        result = await self.session.execute(
            select(Category).where(Category.is_active == True).order_by(Category.name)
        )
        return result.scalars().all()
    
    async def get_by_id(self, category_id: int) -> Optional[Category]:
        """Get category by ID."""
        result = await self.session.execute(
            select(Category).where(Category.id == category_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_name(self, name: str) -> Optional[Category]:
        """Get category by name."""
        result = await self.session.execute(
            select(Category).where(Category.name == name)
        )
        return result.scalar_one_or_none()
    
    async def create(
        self, 
        name: str, 
        emoji: str = "💰",
        description: Optional[str] = None,
        keywords: Optional[list[str]] = None
    ) -> Category:
        """Create a new category."""
        category = Category(
            name=name,
            emoji=emoji,
            description=description,
            keywords=json.dumps(keywords) if keywords else None
        )
        self.session.add(category)
        await self.session.flush()
        return category
    
    async def initialize_default_categories(self) -> None:
        """Initialize default categories from config."""
        for cat_name, keywords in config.CATEGORIES.items():
            # Extract emoji and name
            parts = cat_name.split(" ", 1)
            emoji = parts[0] if len(parts) > 1 else "💰"
            name = parts[1] if len(parts) > 1 else cat_name
            
            existing = await self.get_by_name(name)
            if not existing:
                await self.create(name, emoji, keywords=keywords)


class ExpenseRepository:
    """Repository for Expense operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        user_id: int,
        amount: float,
        description: str,
        category_id: Optional[int] = None,
        currency: str = "MXN",
        merchant: Optional[str] = None,
        source: str = "telegram_text",
        expense_date: Optional[datetime] = None,
        original_message: Optional[str] = None,
        is_confirmed: bool = False
    ) -> Expense:
        """Create a new expense."""
        expense = Expense(
            user_id=user_id,
            category_id=category_id,
            amount=amount,
            currency=currency,
            description=description,
            merchant=merchant,
            source=source,
            expense_date=expense_date or datetime.utcnow(),
            original_message=original_message,
            is_confirmed=is_confirmed,
            is_pending=not is_confirmed
        )
        self.session.add(expense)
        await self.session.flush()
        return expense
    
    async def get_by_id(self, expense_id: int) -> Optional[Expense]:
        """Get expense by ID."""
        result = await self.session.execute(
            select(Expense).where(Expense.id == expense_id)
        )
        return result.scalar_one_or_none()
    
    async def confirm(self, expense_id: int) -> Optional[Expense]:
        """Confirm an expense."""
        expense = await self.get_by_id(expense_id)
        if expense:
            expense.is_confirmed = True
            expense.is_pending = False
            await self.session.flush()
        return expense
    
    async def confirm_with_payment(self, expense_id: int, payment_method: str) -> Optional[Expense]:
        """Confirm an expense and set payment method."""
        expense = await self.get_by_id(expense_id)
        if expense:
            expense.is_confirmed = True
            expense.is_pending = False
            expense.payment_method = payment_method
            await self.session.flush()
        return expense
    
    async def delete(self, expense_id: int) -> bool:
        """Delete an expense."""
        expense = await self.get_by_id(expense_id)
        if expense:
            await self.session.delete(expense)
            return True
        return False
    
    async def get_user_expenses(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        category_id: Optional[int] = None,
        confirmed_only: bool = True,
        limit: Optional[int] = None
    ) -> Sequence[Expense]:
        """Get expenses for a user with optional filters."""
        query = select(Expense).options(selectinload(Expense.category)).where(Expense.user_id == user_id)
        
        if confirmed_only:
            query = query.where(Expense.is_confirmed == True)
        
        if start_date:
            query = query.where(Expense.expense_date >= start_date)
        
        if end_date:
            query = query.where(Expense.expense_date <= end_date)
        
        if category_id:
            query = query.where(Expense.category_id == category_id)
        
        query = query.order_by(Expense.expense_date.desc())
        
        if limit:
            query = query.limit(limit)
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_monthly_summary(
        self, 
        user_id: int, 
        year: int, 
        month: int
    ) -> dict:
        """Get monthly summary by category, split by expenses and incomes."""
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)

        # Expenses
        exp_result = await self.session.execute(
            select(
                Category.name,
                Category.emoji,
                func.sum(Expense.amount).label("total"),
                func.count(Expense.id).label("count")
            )
            .join(Category, Expense.category_id == Category.id, isouter=True)
            .where(
                and_(
                    Expense.user_id == user_id,
                    Expense.is_confirmed == True,
                    Expense.expense_date >= start_date,
                    Expense.expense_date < end_date,
                    Expense.is_income == False
                )
            )
            .group_by(Category.id)
        )
        exp_rows = exp_result.all()

        # Incomes
        inc_result = await self.session.execute(
            select(
                Category.name,
                Category.emoji,
                func.sum(Expense.amount).label("total"),
                func.count(Expense.id).label("count")
            )
            .join(Category, Expense.category_id == Category.id, isouter=True)
            .where(
                and_(
                    Expense.user_id == user_id,
                    Expense.is_confirmed == True,
                    Expense.expense_date >= start_date,
                    Expense.expense_date < end_date,
                    Expense.is_income == True
                )
            )
            .group_by(Category.id)
        )
        inc_rows = inc_result.all()

        return {
            "year": year,
            "month": month,
            "expenses": [
                {
                    "name": row.name or "Sin categoría",
                    "emoji": row.emoji or "💰",
                    "total": float(row.total or 0),
                    "count": row.count
                }
                for row in exp_rows
            ],
            "incomes": [
                {
                    "name": row.name or "Sin categoría",
                    "emoji": row.emoji or "💰",
                    "total": float(row.total or 0),
                    "count": row.count
                }
                for row in inc_rows
            ],
            "total_expenses": sum(float(row.total or 0) for row in exp_rows),
            "total_incomes": sum(float(row.total or 0) for row in inc_rows)
        }
    
    async def get_yearly_summary(self, user_id: int, year: int) -> dict:
        """Get yearly summary by month, split by expenses and incomes."""
        # Expenses
        exp_result = await self.session.execute(
            select(
                extract("month", Expense.expense_date).label("month"),
                func.sum(Expense.amount).label("total"),
                func.count(Expense.id).label("count")
            )
            .where(
                and_(
                    Expense.user_id == user_id,
                    Expense.is_confirmed == True,
                    extract("year", Expense.expense_date) == year,
                    Expense.is_income == False
                )
            )
            .group_by(extract("month", Expense.expense_date))
            .order_by(extract("month", Expense.expense_date))
        )
        exp_rows = exp_result.all()

        # Incomes
        inc_result = await self.session.execute(
            select(
                extract("month", Expense.expense_date).label("month"),
                func.sum(Expense.amount).label("total"),
                func.count(Expense.id).label("count")
            )
            .where(
                and_(
                    Expense.user_id == user_id,
                    Expense.is_confirmed == True,
                    extract("year", Expense.expense_date) == year,
                    Expense.is_income == True
                )
            )
            .group_by(extract("month", Expense.expense_date))
            .order_by(extract("month", Expense.expense_date))
        )
        inc_rows = inc_result.all()

        exp_months = {int(row.month): {"total": float(row.total), "count": row.count} for row in exp_rows}
        inc_months = {int(row.month): {"total": float(row.total), "count": row.count} for row in inc_rows}

        return {
            "year": year,
            "expenses": [
                {
                    "month": m,
                    "total": exp_months.get(m, {}).get("total", 0),
                    "count": exp_months.get(m, {}).get("count", 0)
                }
                for m in range(1, 13)
            ],
            "incomes": [
                {
                    "month": m,
                    "total": inc_months.get(m, {}).get("total", 0),
                    "count": inc_months.get(m, {}).get("count", 0)
                }
                for m in range(1, 13)
            ],
            "total_expenses": sum(float(row.total or 0) for row in exp_rows),
            "total_incomes": sum(float(row.total or 0) for row in inc_rows)
        }


class PendingConfirmationRepository:
    """Repository for PendingConfirmation operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        user_id: int,
        expense_id: int,
        message_id: int,
        expires_in_hours: int = 24
    ) -> PendingConfirmation:
        """Create a pending confirmation."""
        pending = PendingConfirmation(
            user_id=user_id,
            expense_id=expense_id,
            message_id=message_id,
            expires_at=datetime.utcnow() + timedelta(hours=expires_in_hours)
        )
        self.session.add(pending)
        await self.session.flush()
        return pending
    
    async def get_by_expense_id(self, expense_id: int) -> Optional[PendingConfirmation]:
        """Get pending confirmation by expense ID."""
        result = await self.session.execute(
            select(PendingConfirmation).where(PendingConfirmation.expense_id == expense_id)
        )
        return result.scalar_one_or_none()
    
    async def delete(self, confirmation_id: int) -> bool:
        """Delete a pending confirmation."""
        result = await self.session.execute(
            select(PendingConfirmation).where(PendingConfirmation.id == confirmation_id)
        )
        pending = result.scalar_one_or_none()
        if pending:
            await self.session.delete(pending)
            return True
        return False
    
    async def delete_by_expense_id(self, expense_id: int) -> bool:
        """Delete pending confirmation by expense ID."""
        pending = await self.get_by_expense_id(expense_id)
        if pending:
            await self.session.delete(pending)
            return True
        return False
