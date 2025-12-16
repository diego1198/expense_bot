"""
Analytics and statistics module for expense tracking.
Generates reports and charts.
"""

import io
from datetime import datetime, timedelta
from typing import Optional

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import pandas as pd

from src.database.connection import get_session
from src.database.repository import ExpenseRepository, UserRepository


class ExpenseAnalytics:
    """Generate expense analytics and charts."""
    
    MONTHS_ES = [
        "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]
    
    MONTHS_SHORT = [
        "", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
        "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"
    ]
    
    async def get_monthly_chart(
        self, 
        telegram_id: int, 
        year: int, 
        month: int
    ) -> Optional[io.BytesIO]:
        """
        Generate a pie chart for monthly expenses by category.
        
        Returns:
            BytesIO buffer with PNG image, or None if no data
        """
        async with get_session() as session:
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)
            
            user = await user_repo.get_by_telegram_id(telegram_id)
            if not user:
                return None
            
            summary = await expense_repo.get_monthly_summary(user.id, year, month)
        
        if not summary["categories"] or summary["total"] == 0:
            return None
        
        # Prepare data
        labels = []
        sizes = []
        colors = plt.cm.Set3.colors
        
        for cat in summary["categories"]:
            if cat["total"] > 0:
                labels.append(f"{cat['emoji']} {cat['name']}")
                sizes.append(cat["total"])
        
        # Create pie chart
        fig, ax = plt.subplots(figsize=(10, 8))
        
        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=labels,
            autopct=lambda pct: f'${pct/100*sum(sizes):,.0f}\n({pct:.1f}%)',
            colors=colors[:len(sizes)],
            startangle=90,
            pctdistance=0.75
        )
        
        # Style
        plt.setp(autotexts, size=9, weight="bold")
        ax.set_title(
            f"Gastos de {self.MONTHS_ES[month]} {year}\nTotal: ${summary['total']:,.2f}",
            fontsize=14,
            fontweight="bold",
            pad=20
        )
        
        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        plt.close(fig)
        
        return buf
    
    async def get_yearly_chart(
        self, 
        telegram_id: int, 
        year: int
    ) -> Optional[io.BytesIO]:
        """
        Generate a bar chart for yearly expenses by month.
        
        Returns:
            BytesIO buffer with PNG image, or None if no data
        """
        async with get_session() as session:
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)
            
            user = await user_repo.get_by_telegram_id(telegram_id)
            if not user:
                return None
            
            summary = await expense_repo.get_yearly_summary(user.id, year)
        
        if summary["total"] == 0:
            return None
        
        # Prepare data
        months = [self.MONTHS_SHORT[m["month"]] for m in summary["months"]]
        totals = [m["total"] for m in summary["months"]]
        
        # Create bar chart
        fig, ax = plt.subplots(figsize=(12, 6))
        
        bars = ax.bar(months, totals, color='steelblue', edgecolor='navy', alpha=0.8)
        
        # Add value labels on bars
        for bar, total in zip(bars, totals):
            if total > 0:
                height = bar.get_height()
                ax.annotate(
                    f'${total:,.0f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center',
                    va='bottom',
                    fontsize=9,
                    fontweight='bold'
                )
        
        # Style
        ax.set_xlabel('Mes', fontsize=12)
        ax.set_ylabel('Gasto ($)', fontsize=12)
        ax.set_title(
            f"Gastos por Mes - {year}\nTotal: ${summary['total']:,.2f}",
            fontsize=14,
            fontweight="bold",
            pad=15
        )
        ax.grid(axis='y', alpha=0.3)
        
        # Format y-axis
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
        
        plt.tight_layout()
        
        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        plt.close(fig)
        
        return buf
    
    async def get_comparison_chart(
        self, 
        telegram_id: int,
        year: int,
        month1: int,
        month2: int
    ) -> Optional[io.BytesIO]:
        """
        Generate a comparison chart between two months.
        
        Returns:
            BytesIO buffer with PNG image, or None if no data
        """
        async with get_session() as session:
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)
            
            user = await user_repo.get_by_telegram_id(telegram_id)
            if not user:
                return None
            
            summary1 = await expense_repo.get_monthly_summary(user.id, year, month1)
            summary2 = await expense_repo.get_monthly_summary(user.id, year, month2)
        
        if summary1["total"] == 0 and summary2["total"] == 0:
            return None
        
        # Get all categories from both months
        all_categories = set()
        for cat in summary1["categories"]:
            all_categories.add(cat["name"])
        for cat in summary2["categories"]:
            all_categories.add(cat["name"])
        
        # Prepare data
        categories = list(all_categories)
        
        def get_total_for_category(summary, cat_name):
            for cat in summary["categories"]:
                if cat["name"] == cat_name:
                    return cat["total"]
            return 0
        
        totals1 = [get_total_for_category(summary1, cat) for cat in categories]
        totals2 = [get_total_for_category(summary2, cat) for cat in categories]
        
        # Create grouped bar chart
        fig, ax = plt.subplots(figsize=(12, 6))
        
        x = range(len(categories))
        width = 0.35
        
        bars1 = ax.bar([i - width/2 for i in x], totals1, width, 
                       label=self.MONTHS_ES[month1], color='steelblue', alpha=0.8)
        bars2 = ax.bar([i + width/2 for i in x], totals2, width,
                       label=self.MONTHS_ES[month2], color='coral', alpha=0.8)
        
        # Style
        ax.set_xlabel('Categoría', fontsize=12)
        ax.set_ylabel('Gasto ($)', fontsize=12)
        ax.set_title(
            f"Comparación: {self.MONTHS_ES[month1]} vs {self.MONTHS_ES[month2]} {year}",
            fontsize=14,
            fontweight="bold",
            pad=15
        )
        ax.set_xticks(x)
        ax.set_xticklabels(categories, rotation=45, ha='right')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
        
        plt.tight_layout()
        
        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        plt.close(fig)
        
        return buf
    
    async def export_to_csv(
        self,
        telegram_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Optional[io.BytesIO]:
        """
        Export expenses to CSV format.
        
        Returns:
            BytesIO buffer with CSV data, or None if no data
        """
        async with get_session() as session:
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)
            
            user = await user_repo.get_by_telegram_id(telegram_id)
            if not user:
                return None
            
            expenses = await expense_repo.get_user_expenses(
                user.id,
                start_date=start_date,
                end_date=end_date
            )
        
        if not expenses:
            return None
        
        # Convert to DataFrame
        data = []
        for exp in expenses:
            data.append({
                "Fecha": exp.expense_date.strftime("%Y-%m-%d"),
                "Monto": exp.amount,
                "Moneda": exp.currency,
                "Descripción": exp.description,
                "Categoría": exp.category.name if exp.category else "Sin categoría",
                "Comercio": exp.merchant or "",
                "Fuente": exp.source
            })
        
        df = pd.DataFrame(data)
        
        # Save to buffer
        buf = io.BytesIO()
        df.to_csv(buf, index=False, encoding='utf-8')
        buf.seek(0)
        
        return buf


# Singleton instance
expense_analytics = ExpenseAnalytics()
