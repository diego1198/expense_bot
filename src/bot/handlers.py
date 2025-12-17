"""
Telegram bot handlers for expense tracking.
"""

import logging
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from src.config import config
from src.database.connection import get_session, init_db
from src.database.repository import (
    UserRepository, 
    CategoryRepository, 
    ExpenseRepository,
    PendingConfirmationRepository
)
from src.services.expense_parser import expense_parser, ParsedExpense
from src.services.voice_transcriber import voice_transcriber
from src.services.gmail_service import GmailIMAPService
from src.services.email_parser import email_invoice_parser

logger = logging.getLogger(__name__)


def is_user_allowed(user_id: int) -> bool:
    """Check if user is allowed to use the bot."""
    if not config.ALLOWED_USER_IDS:
        return True  # Allow all if no restriction set
    return user_id in config.ALLOWED_USER_IDS


def get_main_menu_keyboard():
    """Create main menu keyboard with buttons."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Mis gastos del mes", callback_data="menu_misgastos"),
            InlineKeyboardButton("📅 Este año", callback_data="menu_anual"),
        ],
        [
            InlineKeyboardButton("📋 Últimos gastos", callback_data="menu_ultimos"),
            InlineKeyboardButton("📂 Tipos de gasto", callback_data="menu_tipos"),
        ],
        [
            InlineKeyboardButton("🗑️ Quitar un gasto", callback_data="menu_quitar"),
            InlineKeyboardButton("🧹 Borrar todo", callback_data="menu_borrar_todo"),
        ],
        [
            InlineKeyboardButton("📧 Configurar email", callback_data="menu_email"),
        ],
        [
            InlineKeyboardButton("❓ Ayuda", callback_data="menu_ayuda"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_email_menu_keyboard():
    """Create email submenu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🔗 Conectar Gmail", callback_data="email_conectar"),
        ],
        [
            InlineKeyboardButton("🔍 Buscar facturas", callback_data="email_buscar"),
            InlineKeyboardButton("🤖 Auto-búsqueda", callback_data="email_auto"),
        ],
        [
            InlineKeyboardButton("⏱️ Cambiar frecuencia", callback_data="email_frecuencia"),
            InlineKeyboardButton("❌ Desconectar", callback_data="email_desconectar"),
        ],
        [
            InlineKeyboardButton("⬅️ Volver al menú", callback_data="menu_principal"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def ensure_user_setup(session, user) -> tuple:
    """
    Ensure user exists and categories are initialized.
    Returns (db_user, is_new_user)
    """
    user_repo = UserRepository(session)
    category_repo = CategoryRepository(session)
    
    db_user = await user_repo.get_by_telegram_id(user.id)
    is_new = False
    
    if not db_user:
        db_user, _ = await user_repo.get_or_create(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=getattr(user, 'last_name', None)
        )
        # Initialize categories for new users
        await category_repo.initialize_default_categories()
        is_new = True
    
    return db_user, is_new


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ No tienes permiso para usar este bot.")
        return
    
    user = update.effective_user
    
    # Create or get user in database
    async with get_session() as session:
        await ensure_user_setup(session, user)
    
    welcome_message = f"""👋 ¡Hola {user.first_name}! Soy tu asistente de gastos.

💡 <b>¿Cómo usarme?</b>
Solo escríbeme lo que gastaste:
  • "Gasté 150 en uber"
  • "500 pesos en super"  
  • "$200 café"

También puedes enviarme un <b>audio</b> 🎤

👇 <b>O usa los botones:</b>"""
    
    await update.message.reply_text(
        welcome_message, 
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard()
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /menu command - show main menu."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    await update.message.reply_text(
        "📋 <b>¿Qué quieres hacer?</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    help_text = """📖 <b>Ayuda</b>

<b>💬 Cómo registrar gastos:</b>
Solo escríbeme qué compraste:
• "Gasté 300 en gasolina"
• "uber 150"
• "Netflix 199"

O envíame un <b>audio</b> contándome 🎤

<b>📊 Ver mis gastos:</b>
/misgastos - Cuánto llevo este mes
/este_ano - Cuánto llevo este año
/ultimos - Mis últimos 10 gastos
/tipos - Ver tipos de gastos

<b>✏️ Editar:</b>
/quitar - Eliminar un gasto
/borrar_todo - Empezar de cero

<b>📧 Facturas por email:</b>
/conectar_email - Conectar mi Gmail
/buscar_facturas - Revisar correo ahora
/auto_facturas - Revisar automáticamente
/cada_cuanto - Cambiar frecuencia
/desconectar_email - Quitar email

Después de cada gasto te pregunto si está bien.
Toca ✅ para guardar o ❌ para cancelar."""
    await update.message.reply_text(help_text, parse_mode="HTML")
    await update.message.reply_text(
        "📋 <b>¿Qué quieres hacer?</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard()
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command - Show system diagnostics."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    import os
    from pathlib import Path
    
    # Get environment info
    railway_volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "")
    data_dir = config.DATA_DIR
    db_url = config.DATABASE_URL
    
    # Check if running on Railway
    is_railway = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_SERVICE_NAME"))
    
    # Check if data directory exists and is writable
    data_dir_exists = data_dir.exists() if isinstance(data_dir, Path) else Path(data_dir).exists()
    data_dir_path = Path(data_dir)
    
    # Check for database file
    db_file = data_dir_path / "expenses.db"
    db_exists = db_file.exists()
    db_size = db_file.stat().st_size if db_exists else 0
    
    # Count expenses
    expense_count = 0
    try:
        async with get_session() as session:
            expense_repo = ExpenseRepository(session)
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_telegram_id(update.effective_user.id)
            if db_user:
                expenses = await expense_repo.get_user_expenses(db_user.id)
                expense_count = len(expenses)
    except Exception as e:
        expense_count = f"Error: {e}"
    
    status_text = f"""🔧 <b>Estado del Sistema</b>

<b>📍 Entorno:</b>
• Railway: {'✅ Sí' if is_railway else '❌ No (local)'}
• RAILWAY_VOLUME_MOUNT_PATH: {railway_volume or '❌ No configurado'}

<b>💾 Base de datos:</b>
• DATA_DIR: <code>{data_dir}</code>
• Directorio existe: {'✅' if data_dir_exists else '❌'}
• Archivo DB existe: {'✅' if db_exists else '❌'}
• Tamaño DB: {db_size / 1024:.1f} KB
• Tus gastos: {expense_count}

<b>🔗 DATABASE_URL:</b>
<code>{db_url[:50]}...</code>

"""
    
    if not railway_volume and is_railway:
        status_text += """⚠️ <b>PROBLEMA DETECTADO:</b>
No tienes configurado el volumen. Los datos se perderán en cada deploy.

<b>Para solucionarlo:</b>
1. Ve a Railway → tu servicio
2. Settings → Volumes
3. Add Volume: mount path = <code>/data</code>
4. Variables → Add: <code>RAILWAY_VOLUME_MOUNT_PATH=/data</code>
5. Redeploy"""
    elif railway_volume and not db_exists:
        status_text += """⚠️ <b>PROBLEMA DETECTADO:</b>
El volumen está configurado pero no hay archivo de base de datos.
Esto puede ser normal si es la primera vez."""
    elif db_exists and expense_count == 0:
        status_text += """ℹ️ Base de datos vacía. Registra tu primer gasto."""
    else:
        status_text += """✅ Todo parece estar bien."""
    
    await update.message.reply_text(status_text, parse_mode="HTML")
    await update.message.reply_text(
        "📋 <b>¿Qué quieres hacer?</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard()
    )


async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /categories command."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    async with get_session() as session:
        category_repo = CategoryRepository(session)
        categories = await category_repo.get_all()
    
    if not categories:
        await update.message.reply_text("No hay categorías configuradas.")
        return
    
    categories_text = "📂 <b>Categorías disponibles:</b>\n\n"
    for cat in categories:
        categories_text += f"{cat.emoji} {cat.name}\n"
    
    await update.message.reply_text(categories_text, parse_mode="HTML")
    await update.message.reply_text(
        "📋 <b>¿Qué más quieres hacer?</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard()
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command - monthly statistics."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    user = update.effective_user
    now = datetime.now()
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        expense_repo = ExpenseRepository(session)
        
        db_user = await user_repo.get_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Primero usa /start para registrarte.")
            return
        
        summary = await expense_repo.get_monthly_summary(db_user.id, now.year, now.month)
    
    months_es = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                 "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    
    stats_text = f"📊 <b>Estadísticas de {months_es[now.month]} {now.year}</b>\n\n"
    
    if not summary["categories"]:
        stats_text += "<i>No hay gastos registrados este mes.</i>"
    else:
        for cat in sorted(summary["categories"], key=lambda x: x["total"], reverse=True):
            stats_text += f"{cat['emoji']} {cat['name']}: ${cat['total']:,.2f} ({cat['count']} gastos)\n"
        
        stats_text += f"\n💰 <b>Total: ${summary['total']:,.2f}</b>"
    
    await update.message.reply_text(stats_text, parse_mode="HTML")
    await update.message.reply_text(
        "📋 <b>¿Qué más quieres hacer?</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard()
    )


async def stats_year_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats_year command - yearly statistics."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    user = update.effective_user
    now = datetime.now()
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        expense_repo = ExpenseRepository(session)
        
        db_user = await user_repo.get_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Primero usa /start para registrarte.")
            return
        
        summary = await expense_repo.get_yearly_summary(db_user.id, now.year)
    
    months_es = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
                 "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    
    stats_text = f"📈 <b>Estadísticas de {now.year}</b>\n\n"
    
    has_data = any(m["total"] > 0 for m in summary["months"])
    
    if not has_data:
        stats_text += "<i>No hay gastos registrados este año.</i>"
    else:
        for month_data in summary["months"]:
            if month_data["total"] > 0:
                month_name = months_es[month_data["month"]]
                stats_text += f"📅 {month_name}: ${month_data['total']:,.2f} ({month_data['count']} gastos)\n"
        
        stats_text += f"\n💰 <b>Total anual: ${summary['total']:,.2f}</b>"
    
    await update.message.reply_text(stats_text, parse_mode="HTML")
    await update.message.reply_text(
        "📋 <b>¿Qué más quieres hacer?</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard()
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /history command - last 10 expenses."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    user = update.effective_user
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        expense_repo = ExpenseRepository(session)
        
        db_user = await user_repo.get_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Primero usa /start para registrarte.")
            return
        
        expenses = await expense_repo.get_user_expenses(db_user.id)
        expenses = list(expenses)[:10]  # Get last 10
    
    if not expenses:
        await update.message.reply_text("📋 No tienes gastos registrados aún.")
        return
    
    history_text = "📋 <b>Últimos gastos:</b>\n\n"
    
    for idx, expense in enumerate(expenses, 1):
        date_str = expense.expense_date.strftime("%d/%m")
        history_text += f"{idx}. {date_str} - ${expense.amount:,.2f} - {expense.description[:30]}\n"
    
    history_text += "\n<i>Usa /quitar [número] para eliminar un gasto</i>"
    
    await update.message.reply_text(history_text, parse_mode="HTML")
    await update.message.reply_text(
        "📋 <b>¿Qué más quieres hacer?</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard()
    )


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete command - delete an expense by number from history."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    user = update.effective_user
    
    # Check if number was provided
    if not context.args:
        await update.message.reply_text(
            "❓ Usa: /delete [número]\n\n"
            "Primero usa /history para ver los números de tus gastos."
        )
        return
    
    try:
        expense_num = int(context.args[0])
        if expense_num < 1:
            raise ValueError("Número inválido")
    except ValueError:
        await update.message.reply_text("❌ Por favor indica un número válido. Ejemplo: /delete 1")
        return
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        expense_repo = ExpenseRepository(session)
        
        db_user = await user_repo.get_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("Primero usa /start para registrarte.")
            return
        
        expenses = await expense_repo.get_user_expenses(db_user.id)
        expenses = list(expenses)[:10]
        
        if expense_num > len(expenses):
            await update.message.reply_text(f"❌ Solo tienes {len(expenses)} gastos en el historial.")
            return
        
        expense_to_delete = expenses[expense_num - 1]
        description = expense_to_delete.description[:30]
        amount = expense_to_delete.amount
        
        await expense_repo.delete(expense_to_delete.id)
    
    await update.message.reply_text(
        f"🗑️ Gasto eliminado:\n${amount:,.2f} - {description}"
    )
    await update.message.reply_text(
        "📋 <b>¿Qué más quieres hacer?</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard()
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /clear command - show confirmation to clear all expenses."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Sí, borrar todo", callback_data="clear_confirm"),
            InlineKeyboardButton("❌ Cancelar", callback_data="clear_cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚠️ <b>¿Estás seguro de borrar TODOS tus gastos?</b>\n\n"
        "Esta acción no se puede deshacer.",
        parse_mode="HTML",
        reply_markup=reply_markup
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages - parse and register expenses."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    user = update.effective_user
    text = update.message.text.strip()
    
    if not text:
        return
    
    # Check if user is new BEFORE parsing (to show welcome first)
    async with get_session() as session:
        db_user, is_new = await ensure_user_setup(session, user)
    
    if is_new:
        # Show full welcome for new users
        welcome_msg = f"""👋 <b>¡Hola {user.first_name}!</b>

Soy tu asistente personal de gastos 💰

<b>¿Qué puedo hacer?</b>
📝 Registrar tus gastos diarios
📊 Mostrarte estadísticas del mes/año
📧 Detectar facturas de tu email
🎤 Entender mensajes de voz

<b>¿Cómo usarme?</b>
Solo escríbeme lo que gastaste:
• "café 50"
• "uber 150"
• "supermercado 800"

O envíame un <b>audio</b> contándome 🎤

👇 <b>Usa el menú para ver opciones:</b>"""
        
        await update.message.reply_text(
            welcome_msg,
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
        return  # Don't process first message as expense, let them explore first
    
    # Parse the expense
    await update.message.reply_chat_action("typing")
    parsed = await expense_parser.parse(text)
    
    # Check if clarification is needed
    if parsed.needs_clarification:
        await update.message.reply_text(
            f"🤔 {parsed.clarification_question or 'No pude entender el gasto. ¿Podrías reformularlo?'}"
        )
        return
    
    if parsed.amount <= 0:
        await update.message.reply_text(
            "❓ No pude detectar el monto del gasto. Por favor, incluye la cantidad.\n"
            "Ejemplo: 'Gasté 150 en uber'"
        )
        return
    
    # Save to database (pending confirmation)
    async with get_session() as session:
        category_repo = CategoryRepository(session)
        expense_repo = ExpenseRepository(session)
        pending_repo = PendingConfirmationRepository(session)
        
        # Get user (already exists at this point)
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(user.id)
        
        # Find category
        category = await category_repo.get_by_name(parsed.category)
        category_id = category.id if category else None
        category_display = f"{category.emoji} {category.name}" if category else f"💰 {parsed.category}"
        
        # Create expense (pending)
        expense = await expense_repo.create(
            user_id=db_user.id,
            amount=parsed.amount,
            description=parsed.description,
            category_id=category_id,
            currency=parsed.currency,
            merchant=parsed.merchant,
            source="telegram_text",
            expense_date=parsed.date,
            original_message=text,
            is_confirmed=False
        )
        
        # Create confirmation message
        date_str = parsed.date.strftime("%d/%m/%Y") if parsed.date else "Hoy"
        
        confirmation_text = f"""📝 <b>Nuevo gasto detectado:</b>

💵 Monto: <b>${parsed.amount:,.2f} {parsed.currency}</b>
📂 Categoría: {category_display}
📋 Descripción: {parsed.description}
🏪 Comercio: {parsed.merchant or "No especificado"}
📅 Fecha: {date_str}

💳 <b>¿Cómo pagaste?</b>"""
        
        # Inline keyboard for payment method selection
        keyboard = [
            [
                InlineKeyboardButton("💵 Efectivo", callback_data=f"pay_efectivo_{expense.id}"),
                InlineKeyboardButton("💳 Tarjeta", callback_data=f"pay_tarjeta_{expense.id}"),
            ],
            [
                InlineKeyboardButton("🏦 Transferencia", callback_data=f"pay_transferencia_{expense.id}"),
            ],
            [
                InlineKeyboardButton("✏️ Editar categoría", callback_data=f"edit_cat_{expense.id}"),
                InlineKeyboardButton("❌ Cancelar", callback_data=f"cancel_{expense.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        sent_message = await update.message.reply_text(
            confirmation_text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        
        # Save pending confirmation
        await pending_repo.create(
            user_id=db_user.id,
            expense_id=expense.id,
            message_id=sent_message.message_id
        )


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages - transcribe and parse as expense."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    user = update.effective_user
    voice = update.message.voice
    
    # Check if user is new BEFORE processing
    async with get_session() as session:
        db_user, is_new = await ensure_user_setup(session, user)
    
    if is_new:
        # Show full welcome for new users
        welcome_msg = f"""👋 <b>¡Hola {user.first_name}!</b>

Soy tu asistente personal de gastos 💰

<b>¿Qué puedo hacer?</b>
📝 Registrar tus gastos diarios
📊 Mostrarte estadísticas del mes/año
📧 Detectar facturas de tu email
🎤 Entender mensajes de voz

<b>¿Cómo usarme?</b>
Solo escríbeme o dime lo que gastaste:
• "café 50"
• "uber 150"
• "supermercado 800"

👇 <b>Usa el menú para ver opciones:</b>"""
        
        await update.message.reply_text(
            welcome_msg,
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
        return  # Let them explore first
    
    await update.message.reply_text("🎤 Procesando mensaje de voz...")
    
    try:
        # Transcribe voice message
        transcription = await voice_transcriber.transcribe_telegram_voice(
            context.bot,
            voice.file_id
        )
        
        if not transcription:
            await update.message.reply_text("❌ No pude transcribir el mensaje de voz. Intenta de nuevo.")
            return
        
        await update.message.reply_text(f"📝 Escuché: <i>{transcription}</i>", parse_mode="HTML")
        
        # Parse the transcription as expense
        parsed = await expense_parser.parse(transcription)
        
        if parsed.needs_clarification or parsed.amount <= 0:
            await update.message.reply_text(
                f"🤔 {parsed.clarification_question or 'No pude entender el gasto del mensaje de voz.'}\n"
                "Intenta decir algo como: 'Gasté cien pesos en uber'"
            )
            return
        
        # Save to database (same logic as text)
        async with get_session() as session:
            category_repo = CategoryRepository(session)
            expense_repo = ExpenseRepository(session)
            pending_repo = PendingConfirmationRepository(session)
            
            # Get user (already exists at this point)
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_telegram_id(user.id)
            
            category = await category_repo.get_by_name(parsed.category)
            category_id = category.id if category else None
            category_display = f"{category.emoji} {category.name}" if category else f"💰 {parsed.category}"
            
            expense = await expense_repo.create(
                user_id=db_user.id,
                amount=parsed.amount,
                description=parsed.description,
                category_id=category_id,
                currency=parsed.currency,
                merchant=parsed.merchant,
                source="telegram_voice",
                expense_date=parsed.date,
                original_message=transcription,
                is_confirmed=False
            )
            
            date_str = parsed.date.strftime("%d/%m/%Y") if parsed.date else "Hoy"
            
            confirmation_text = f"""🎤 <b>Gasto desde mensaje de voz:</b>

💵 Monto: <b>${parsed.amount:,.2f} {parsed.currency}</b>
📂 Categoría: {category_display}
📋 Descripción: {parsed.description}
🏪 Comercio: {parsed.merchant or "No especificado"}
📅 Fecha: {date_str}

💳 <b>¿Cómo pagaste?</b>"""
            
            keyboard = [
                [
                    InlineKeyboardButton("💵 Efectivo", callback_data=f"pay_efectivo_{expense.id}"),
                    InlineKeyboardButton("💳 Tarjeta", callback_data=f"pay_tarjeta_{expense.id}"),
                ],
                [
                    InlineKeyboardButton("🏦 Transferencia", callback_data=f"pay_transferencia_{expense.id}"),
                ],
                [
                    InlineKeyboardButton("✏️ Editar categoría", callback_data=f"edit_cat_{expense.id}"),
                    InlineKeyboardButton("❌ Cancelar", callback_data=f"cancel_{expense.id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            sent_message = await update.message.reply_text(
                confirmation_text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            
            await pending_repo.create(
                user_id=db_user.id,
                expense_id=expense.id,
                message_id=sent_message.message_id
            )
    
    except Exception as e:
        logger.error(f"Error processing voice message: {e}")
        await update.message.reply_text(
            "❌ Hubo un error procesando el mensaje de voz. Por favor, intenta de nuevo."
        )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard callbacks."""
    query = update.callback_query
    await query.answer()
    
    if not is_user_allowed(query.from_user.id):
        return
    
    data = query.data
    
    # Confirm expense
    if data.startswith("confirm_"):
        expense_id = int(data.split("_")[1])
        
        async with get_session() as session:
            expense_repo = ExpenseRepository(session)
            pending_repo = PendingConfirmationRepository(session)
            
            expense = await expense_repo.confirm(expense_id)
            await pending_repo.delete_by_expense_id(expense_id)
        
        if expense:
            await query.edit_message_text(
                f"✅ <b>Gasto registrado correctamente</b>\n\n"
                f"💵 ${expense.amount:,.2f} - {expense.description}",
                parse_mode="HTML"
            )
            # Show menu after confirmation
            await query.message.reply_text(
                "📋 <b>¿Qué más quieres hacer?</b>",
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await query.edit_message_text("❌ No se encontró el gasto.")
    
    # Cancel expense
    elif data.startswith("cancel_"):
        expense_id = int(data.split("_")[1])
        
        async with get_session() as session:
            expense_repo = ExpenseRepository(session)
            pending_repo = PendingConfirmationRepository(session)
            
            await expense_repo.delete(expense_id)
            await pending_repo.delete_by_expense_id(expense_id)
        
        await query.edit_message_text("❌ Gasto cancelado.")
        # Show menu after cancellation
        await query.message.reply_text(
            "📋 <b>¿Qué quieres hacer?</b>",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
    
    # Payment method selection (confirms and saves payment method)
    elif data.startswith("pay_"):
        parts = data.split("_")
        payment_method = parts[1]  # efectivo, tarjeta, transferencia
        expense_id = int(parts[2])
        
        payment_icons = {
            "efectivo": "💵",
            "tarjeta": "💳",
            "transferencia": "🏦"
        }
        payment_display = {
            "efectivo": "Efectivo",
            "tarjeta": "Tarjeta",
            "transferencia": "Transferencia"
        }
        
        async with get_session() as session:
            expense_repo = ExpenseRepository(session)
            pending_repo = PendingConfirmationRepository(session)
            
            expense = await expense_repo.confirm_with_payment(expense_id, payment_method)
            await pending_repo.delete_by_expense_id(expense_id)
        
        if expense:
            icon = payment_icons.get(payment_method, "💰")
            method_name = payment_display.get(payment_method, payment_method)
            await query.edit_message_text(
                f"✅ <b>Gasto registrado</b>\n\n"
                f"💵 ${expense.amount:,.2f} - {expense.description}\n"
                f"{icon} Pagado con: <b>{method_name}</b>",
                parse_mode="HTML"
            )
            # Show menu after confirmation
            await query.message.reply_text(
                "📋 <b>¿Qué más quieres hacer?</b>",
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await query.edit_message_text("❌ No se encontró el gasto.")
    
    # Edit category
    elif data.startswith("edit_cat_"):
        expense_id = int(data.split("_")[2])
        
        async with get_session() as session:
            category_repo = CategoryRepository(session)
            categories = await category_repo.get_all()
        
        keyboard = []
        for cat in categories:
            keyboard.append([
                InlineKeyboardButton(
                    f"{cat.emoji} {cat.name}",
                    callback_data=f"setcat_{expense_id}_{cat.id}"
                )
            ])
        keyboard.append([
            InlineKeyboardButton("🔙 Volver", callback_data=f"back_{expense_id}")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📂 Selecciona la categoría correcta:",
            reply_markup=reply_markup
        )
    
    # Set category
    elif data.startswith("setcat_"):
        parts = data.split("_")
        expense_id = int(parts[1])
        category_id = int(parts[2])
        
        async with get_session() as session:
            expense_repo = ExpenseRepository(session)
            category_repo = CategoryRepository(session)
            
            expense = await expense_repo.get_by_id(expense_id)
            category = await category_repo.get_by_id(category_id)
            
            if expense and category:
                expense.category_id = category_id
                await session.flush()
                
                category_display = f"{category.emoji} {category.name}"
                date_str = expense.expense_date.strftime("%d/%m/%Y")
                
                confirmation_text = f"""📝 <b>Gasto actualizado:</b>

💵 Monto: <b>${expense.amount:,.2f} {expense.currency}</b>
📂 Categoría: {category_display}
📋 Descripción: {expense.description}
📅 Fecha: {date_str}

¿Es correcto?"""
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Confirmar", callback_data=f"confirm_{expense.id}"),
                        InlineKeyboardButton("❌ Cancelar", callback_data=f"cancel_{expense.id}")
                    ],
                    [
                        InlineKeyboardButton("✏️ Editar categoría", callback_data=f"edit_cat_{expense.id}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    confirmation_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
    
    # Clear all expenses confirmation
    elif data == "clear_confirm":
        async with get_session() as session:
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)
            
            db_user = await user_repo.get_by_telegram_id(query.from_user.id)
            if db_user:
                expenses = await expense_repo.get_user_expenses(db_user.id, confirmed_only=False)
                count = 0
                for expense in expenses:
                    await expense_repo.delete(expense.id)
                    count += 1
        
        await query.edit_message_text(f"🗑️ Se eliminaron {count} gastos.")
        await query.message.reply_text(
            "📋 <b>¿Qué quieres hacer ahora?</b>",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
    
    elif data == "clear_cancel":
        await query.edit_message_text("✅ Operación cancelada. Tus gastos están seguros.")
        await query.message.reply_text(
            "📋 <b>¿Qué quieres hacer?</b>",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
    
    # Email invoice confirmation (legacy - keep for backwards compatibility)
    elif data.startswith("email_confirm_"):
        expense_id = int(data.split("_")[2])
        
        async with get_session() as session:
            expense_repo = ExpenseRepository(session)
            expense = await expense_repo.confirm(expense_id)
        
        if expense:
            await query.edit_message_text(
                f"✅ <b>Gasto de email registrado</b>\n\n"
                f"💵 ${expense.amount:,.2f} - {expense.description}",
                parse_mode="HTML"
            )
            await query.message.reply_text(
                "📋 <b>¿Qué más quieres hacer?</b>",
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await query.edit_message_text("❌ No se encontró el gasto.")
    
    # Email payment method selection
    elif data.startswith("emailpay_"):
        parts = data.split("_")
        payment_method = parts[1]  # efectivo, tarjeta, transferencia
        expense_id = int(parts[2])
        
        payment_icons = {
            "efectivo": "💵",
            "tarjeta": "💳",
            "transferencia": "🏦"
        }
        payment_display = {
            "efectivo": "Efectivo",
            "tarjeta": "Tarjeta",
            "transferencia": "Transferencia"
        }
        
        async with get_session() as session:
            expense_repo = ExpenseRepository(session)
            expense = await expense_repo.confirm_with_payment(expense_id, payment_method)
        
        if expense:
            icon = payment_icons.get(payment_method, "💰")
            method_name = payment_display.get(payment_method, payment_method)
            await query.edit_message_text(
                f"✅ <b>Gasto de email registrado</b>\n\n"
                f"💵 ${expense.amount:,.2f} - {expense.description}\n"
                f"{icon} Pagado con: <b>{method_name}</b>",
                parse_mode="HTML"
            )
            await query.message.reply_text(
                "📋 <b>¿Qué más quieres hacer?</b>",
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await query.edit_message_text("❌ No se encontró el gasto.")
    
    elif data.startswith("email_cancel_"):
        expense_id = int(data.split("_")[2])
        
        async with get_session() as session:
            expense_repo = ExpenseRepository(session)
            await expense_repo.delete(expense_id)
        
        await query.edit_message_text("❌ Gasto de email descartado.")
        await query.message.reply_text(
            "📋 <b>¿Qué quieres hacer?</b>",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
    
    # ========== MENU BUTTONS ==========
    
    # Main menu
    elif data == "menu_principal":
        await query.edit_message_text(
            "📋 <b>¿Qué quieres hacer?</b>",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
    
    # Stats this month
    elif data == "menu_misgastos":
        user = query.from_user
        now = datetime.now()
        async with get_session() as session:
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)
            
            db_user = await user_repo.get_by_telegram_id(user.id)
            if not db_user:
                await query.edit_message_text("❌ Usuario no encontrado.")
                return
            
            stats = await expense_repo.get_monthly_summary(db_user.id, now.year, now.month)
        
        if not stats['total']:
            text = "📊 <b>Este mes</b>\n\nNo tienes gastos registrados este mes."
        else:
            text = f"📊 <b>Gastos de este mes</b>\n\n"
            text += f"💰 Total: <b>${stats['total']:,.2f}</b>\n\n"
            
            if stats['categories']:
                text += "<b>Por categoría:</b>\n"
                for cat in stats['categories']:
                    text += f"  {cat['emoji']} {cat['name']}: ${cat['total']:,.2f}\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="menu_principal")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Stats this year
    elif data == "menu_anual":
        user = query.from_user
        now = datetime.now()
        async with get_session() as session:
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)
            
            db_user = await user_repo.get_by_telegram_id(user.id)
            if not db_user:
                await query.edit_message_text("❌ Usuario no encontrado.")
                return
            
            stats = await expense_repo.get_yearly_summary(db_user.id, now.year)
        
        if not stats['total']:
            text = "📅 <b>Este año</b>\n\nNo tienes gastos registrados este año."
        else:
            text = f"📅 <b>Gastos de este año</b>\n\n"
            text += f"💰 Total: <b>${stats['total']:,.2f}</b>\n"
            
            # Calculate average
            months_with_expenses = [m for m in stats['months'] if m['total'] > 0]
            if months_with_expenses:
                avg = stats['total'] / len(months_with_expenses)
                text += f"📊 Promedio mensual: ${avg:,.2f}\n\n"
            
            text += "<b>Por mes:</b>\n"
            month_names = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 
                          'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
            for m in stats['months']:
                if m['total'] > 0:
                    text += f"  • {month_names[m['month']-1]}: ${m['total']:,.2f}\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="menu_principal")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # History
    elif data == "menu_ultimos":
        user = query.from_user
        async with get_session() as session:
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)
            
            db_user = await user_repo.get_by_telegram_id(user.id)
            if not db_user:
                await query.edit_message_text("❌ Usuario no encontrado.")
                return
            
            expenses = await expense_repo.get_user_expenses(db_user.id, limit=10)
        
        if not expenses:
            text = "📋 No tienes gastos registrados."
        else:
            payment_icons = {"efectivo": "💵", "tarjeta": "💳", "transferencia": "🏦"}
            text = "📋 <b>Tus últimos gastos:</b>\n\n"
            for i, exp in enumerate(expenses, 1):
                date_str = exp.expense_date.strftime("%d/%m")
                cat_emoji = "💰"
                if exp.category:
                    cat_emoji = exp.category.emoji
                pay_icon = payment_icons.get(exp.payment_method, "") if exp.payment_method else ""
                text += f"{i}. {cat_emoji} ${exp.amount:,.2f} - {exp.description[:20]} {pay_icon} ({date_str})\n"
            
            text += "\n💡 Para eliminar, usa /quitar [número]"
        
        keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="menu_principal")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Categories
    elif data == "menu_tipos":
        async with get_session() as session:
            category_repo = CategoryRepository(session)
            categories = await category_repo.get_all()
        
        if not categories:
            text = "No hay tipos de gasto configurados."
        else:
            text = "📂 <b>Tipos de gasto:</b>\n\n"
            for cat in categories:
                text += f"{cat.emoji} {cat.name}\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="menu_principal")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Delete expense prompt
    elif data == "menu_quitar":
        user = query.from_user
        async with get_session() as session:
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)
            
            db_user = await user_repo.get_by_telegram_id(user.id)
            if db_user:
                expenses = await expense_repo.get_user_expenses(db_user.id, limit=10)
        
        if not expenses:
            text = "📋 No tienes gastos para eliminar."
            keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="menu_principal")]]
        else:
            text = "🗑️ <b>¿Cuál quieres eliminar?</b>\n\n"
            keyboard = []
            for i, exp in enumerate(expenses[:8], 1):
                text += f"{i}. ${exp.amount:,.2f} - {exp.description[:20]}\n"
                keyboard.append([
                    InlineKeyboardButton(
                        f"❌ {i}. ${exp.amount:,.0f} - {exp.description[:15]}",
                        callback_data=f"del_exp_{exp.id}"
                    )
                ])
            keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="menu_principal")])
        
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Delete specific expense
    elif data.startswith("del_exp_"):
        expense_id = int(data.split("_")[2])
        
        async with get_session() as session:
            expense_repo = ExpenseRepository(session)
            expense = await expense_repo.get_by_id(expense_id)
            if expense:
                desc = expense.description
                amount = expense.amount
                await expense_repo.delete(expense_id)
                text = f"✅ Eliminado: ${amount:,.2f} - {desc}"
            else:
                text = "❌ No se encontró el gasto."
        
        keyboard = [[InlineKeyboardButton("⬅️ Volver al menú", callback_data="menu_principal")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Clear all confirmation
    elif data == "menu_borrar_todo":
        text = "⚠️ <b>¿Estás seguro?</b>\n\nEsto eliminará TODOS tus gastos registrados."
        keyboard = [
            [
                InlineKeyboardButton("🗑️ Sí, borrar todo", callback_data="clear_confirm"),
                InlineKeyboardButton("❌ No, cancelar", callback_data="menu_principal")
            ]
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Email submenu
    elif data == "menu_email":
        user = query.from_user
        async with get_session() as session:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_telegram_id(user.id)
            
            if db_user and db_user.email_address:
                status = "✅ Conectado"
                email_display = db_user.email_address[:20] + "..."
                auto_status = "🟢 Activada" if db_user.email_auto_check else "⚪ Desactivada"
                interval = db_user.email_check_interval or 30
                
                text = f"📧 <b>Configuración de Email</b>\n\n"
                text += f"📬 {email_display}\n"
                text += f"🤖 Auto-búsqueda: {auto_status}\n"
                text += f"⏱️ Frecuencia: cada {interval} min"
            else:
                text = "📧 <b>Detectar facturas por email</b>\n\n"
                text += "Conecta tu Gmail para detectar automáticamente facturas y recibos."
        
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_email_menu_keyboard())
    
    # Email: connect
    elif data == "email_conectar":
        text = """🔗 <b>Conectar Gmail</b>

Escribe este comando con tus datos:
<code>/conectar_email tu@gmail.com tu_clave</code>

⚠️ Necesitas una "contraseña de aplicación":
1. Ve a myaccount.google.com/security
2. Activa verificación en 2 pasos
3. Crea una "Contraseña de aplicación"
4. Copia los 16 caracteres"""
        
        keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="menu_email")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Email: search now
    elif data == "email_buscar":
        user = query.from_user
        async with get_session() as session:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_telegram_id(user.id)
            
            if not db_user or not db_user.email_address:
                text = "❌ Primero conecta tu email."
                keyboard = [[InlineKeyboardButton("🔗 Conectar", callback_data="email_conectar")]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
                return
        
        await query.edit_message_text("📧 Buscando facturas en tu correo...")
        
        # Call check emails with chat_id instead of using update.message
        await _check_emails_for_user(context, query.message.chat_id, user.id)
    
    # Email: toggle auto
    elif data == "email_auto":
        user = query.from_user
        async with get_session() as session:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_telegram_id(user.id)
            
            if not db_user or not db_user.email_address:
                text = "❌ Primero conecta tu email."
                keyboard = [[InlineKeyboardButton("🔗 Conectar", callback_data="email_conectar")]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
                return
            
            new_state = not db_user.email_auto_check
            await user_repo.set_email_auto_check(user.id, new_state)
            interval = db_user.email_check_interval or 30
        
        if new_state:
            text = f"✅ <b>Auto-búsqueda ACTIVADA</b>\n\nRevisaré tu correo cada {interval} minutos."
        else:
            text = "⏸️ <b>Auto-búsqueda DESACTIVADA</b>"
        
        keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="menu_email")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Email: frequency
    elif data == "email_frecuencia":
        keyboard = [
            [
                InlineKeyboardButton("5 min", callback_data="freq_5"),
                InlineKeyboardButton("15 min", callback_data="freq_15"),
                InlineKeyboardButton("30 min", callback_data="freq_30"),
            ],
            [
                InlineKeyboardButton("1 hora", callback_data="freq_60"),
                InlineKeyboardButton("2 horas", callback_data="freq_120"),
                InlineKeyboardButton("6 horas", callback_data="freq_360"),
            ],
            [InlineKeyboardButton("⬅️ Volver", callback_data="menu_email")]
        ]
        await query.edit_message_text(
            "⏱️ <b>¿Cada cuánto reviso tu correo?</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # Set frequency
    elif data.startswith("freq_"):
        minutes = int(data.split("_")[1])
        user = query.from_user
        
        async with get_session() as session:
            user_repo = UserRepository(session)
            await user_repo.set_email_check_interval(user.id, minutes)
        
        if minutes >= 60:
            display = f"{minutes // 60} hora{'s' if minutes > 60 else ''}"
        else:
            display = f"{minutes} minutos"
        
        text = f"✅ Listo! Revisaré cada <b>{display}</b>"
        keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="menu_email")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Email: disconnect
    elif data == "email_desconectar":
        user = query.from_user
        async with get_session() as session:
            user_repo = UserRepository(session)
            await user_repo.clear_email_credentials(user.id)
        
        text = "✅ Email desconectado."
        keyboard = [[InlineKeyboardButton("⬅️ Volver al menú", callback_data="menu_principal")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Help
    elif data == "menu_ayuda":
        text = """❓ <b>Ayuda</b>

<b>Registrar gastos:</b>
Solo escríbeme qué compraste:
• "Gasté 300 en gasolina"
• "uber 150"
• "Netflix 199"

O envíame un audio 🎤

<b>Tip:</b> Usa /menu para ver los botones en cualquier momento."""
        
        keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="menu_principal")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def _check_emails_for_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, telegram_id: int) -> None:
    """Check emails for a user and send results to chat. Used by both command and button."""
    
    # Get user's email credentials
    async with get_session() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(telegram_id)
        
        if not db_user or not db_user.email_address or not db_user.email_app_password:
            await context.bot.send_message(
                chat_id=chat_id,
                text="📧 <b>Aún no conectaste tu email</b>\n\n"
                     "Para buscar facturas, primero conecta tu Gmail:\n"
                     "<code>/conectar_email tu@gmail.com tu_clave</code>",
                parse_mode="HTML"
            )
            return
        
        email_address = db_user.email_address
        app_password = db_user.email_app_password
    
    try:
        # Create IMAP service for this user
        imap_service = GmailIMAPService(email_address, app_password)
        
        if not imap_service.connect():
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ <b>Error de conexión</b>\n\n"
                     "No se pudo conectar a Gmail. Verifica que tus credenciales sean correctas.",
                parse_mode="HTML"
            )
            return
        
        # Get unread invoices
        invoices = imap_service.get_unread_invoices()
        
        if not invoices:
            await context.bot.send_message(
                chat_id=chat_id,
                text="📭 No se encontraron facturas nuevas.",
                reply_markup=get_main_menu_keyboard()
            )
            imap_service.disconnect()
            return
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📬 Encontré {len(invoices)} posibles facturas. Procesando..."
        )
        
        # Process each invoice
        async with get_session() as session:
            user_repo = UserRepository(session)
            category_repo = CategoryRepository(session)
            expense_repo = ExpenseRepository(session)
            
            db_user = await user_repo.get_by_telegram_id(telegram_id)
            
            processed = 0
            for email_msg in invoices:
                # Parse invoice with GPT
                parsed = await email_invoice_parser.parse_invoice_email(email_msg)
                
                if not parsed or parsed.amount <= 0:
                    continue
                
                # Find category
                category = await category_repo.get_by_name(parsed.category)
                category_id = category.id if category else None
                category_display = f"{category.emoji} {category.name}" if category else f"💰 {parsed.category}"
                
                # Create expense (pending)
                expense = await expense_repo.create(
                    user_id=db_user.id,
                    amount=parsed.amount,
                    description=parsed.description,
                    category_id=category_id,
                    currency=parsed.currency,
                    merchant=parsed.merchant,
                    source="email",
                    expense_date=parsed.date,
                    original_message=f"Email: {parsed.original_subject}",
                    is_confirmed=False
                )
                
                date_str = parsed.date.strftime("%d/%m/%Y")
                
                confirmation_text = f"""📧 <b>Factura detectada en email:</b>

💵 Monto: <b>${parsed.amount:,.2f} {parsed.currency}</b>
📂 Categoría: {category_display}
🏪 Comercio: {parsed.merchant}
📋 Descripción: {parsed.description}
📅 Fecha: {date_str}
📨 Asunto: {parsed.original_subject[:50]}...

💳 <b>¿Cómo pagaste?</b>"""
                
                keyboard = [
                    [
                        InlineKeyboardButton("💵 Efectivo", callback_data=f"emailpay_efectivo_{expense.id}"),
                        InlineKeyboardButton("💳 Tarjeta", callback_data=f"emailpay_tarjeta_{expense.id}"),
                    ],
                    [
                        InlineKeyboardButton("🏦 Transferencia", callback_data=f"emailpay_transferencia_{expense.id}"),
                    ],
                    [
                        InlineKeyboardButton("❌ Descartar", callback_data=f"email_cancel_{expense.id}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=confirmation_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
                
                # Mark email as read
                imap_service.mark_as_read(email_msg.email_id)
                processed += 1
        
        imap_service.disconnect()
        
        if processed == 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text="📭 No se encontraron facturas válidas para procesar.",
                reply_markup=get_main_menu_keyboard()
            )
    
    except Exception as e:
        logger.error(f"Error checking emails: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Error al revisar correos: {str(e)[:100]}"
        )


async def check_emails_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /buscar_facturas command - check for invoice emails via IMAP."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    user = update.effective_user
    await update.message.reply_text("📧 Conectando a tu correo...")
    await _check_emails_for_user(context, update.effective_chat.id, user.id)


async def setup_email_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /conectar_email command - configure Gmail IMAP access."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    user = update.effective_user
    args = context.args
    
    if not args or len(args) < 2:
        await update.message.reply_text(
            "📧 <b>Conectar mi Gmail</b>\n\n"
            "<b>Escribe:</b>\n"
            "<code>/conectar_email tu@gmail.com tu_clave</code>\n\n"
            "⚠️ <b>Importante:</b>\n"
            "Necesitas una <b>contraseña de aplicación</b> (no tu contraseña normal)\n\n"
            "📖 <b>Cómo obtenerla:</b>\n"
            "1. Entra a myaccount.google.com/security\n"
            "2. Activa la verificación en 2 pasos\n"
            "3. Busca 'Contraseñas de aplicaciones'\n"
            "4. Crea una nueva y copia los 16 caracteres",
            parse_mode="HTML"
        )
        return
    
    email_address = args[0]
    app_password = args[1]
    
    # Validate email format
    if "@" not in email_address or "." not in email_address:
        await update.message.reply_text("❌ El formato del email no es válido.")
        return
    
    # Test connection
    await update.message.reply_text("🔄 Probando conexión...")
    
    imap_service = GmailIMAPService(email_address, app_password)
    
    if imap_service.connect():
        imap_service.disconnect()
        
        # Save credentials
        async with get_session() as session:
            user_repo = UserRepository(session)
            await user_repo.update_email_credentials(
                telegram_id=user.id,
                email_address=email_address,
                app_password=app_password
            )
        
        # Delete the message with credentials for security
        try:
            await update.message.delete()
        except:
            pass
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ <b>¡Email conectado!</b>\n\n"
                 f"📧 {email_address}\n\n"
                 "🔒 Tu mensaje con la contraseña fue borrado por seguridad.",
            parse_mode="HTML"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="📋 <b>¿Qué quieres hacer ahora?</b>",
            parse_mode="HTML",
            reply_markup=get_email_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ <b>Error de conexión</b>\n\n"
            "No se pudo conectar. Verifica:\n"
            "• El email es correcto\n"
            "• Usaste una contraseña de aplicación (16 caracteres)\n"
            "• IMAP está habilitado en Gmail",
            parse_mode="HTML"
        )


async def remove_email_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /desconectar_email command - remove email configuration."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    user = update.effective_user
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        success = await user_repo.clear_email_credentials(user.id)
    
    if success:
        await update.message.reply_text(
            "✅ Configuración de email eliminada.\n"
            "Ya no se buscarán facturas en tu correo."
        )
        await update.message.reply_text(
            "📋 <b>¿Qué quieres hacer?</b>",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await update.message.reply_text("📭 No tenías un email configurado.")
        await update.message.reply_text(
            "📋 <b>¿Qué quieres hacer?</b>",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )


async def toggle_auto_email_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /auto_email command - toggle automatic email checking."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    user = update.effective_user
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(user.id)
        
        if not db_user or not db_user.email_address:
            await update.message.reply_text(
                "📧 Primero conecta tu email con /conectar_email"
            )
            return
        
        # Toggle the setting
        new_state = not db_user.email_auto_check
        await user_repo.set_email_auto_check(user.id, new_state)
        
        interval = db_user.email_check_interval or 30
        
        if new_state:
            await update.message.reply_text(
                f"✅ <b>Búsqueda automática ACTIVADA</b>\n\n"
                f"📧 Revisaré tu correo cada <b>{interval} minutos</b>\n"
                f"y te avisaré cuando encuentre facturas.",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                "⏸️ <b>Búsqueda automática DESACTIVADA</b>\n\n"
                "Ya no revisaré tu correo solo.\n"
                "Usa /buscar_facturas cuando quieras buscar.",
                parse_mode="HTML"
            )
        
        # Show menu after toggle
        await update.message.reply_text(
            "📋 <b>¿Qué más quieres hacer?</b>",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )


async def auto_check_emails_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Background job to automatically check emails for all users with auto-check enabled."""
    logger.info("Running automatic email check job...")
    
    from datetime import timedelta
    now = datetime.utcnow()
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        category_repo = CategoryRepository(session)
        expense_repo = ExpenseRepository(session)
        
        users = await user_repo.get_users_with_auto_check()
        
        for db_user in users:
            try:
                # Check if enough time has passed since last check for this user
                if db_user.email_last_checked:
                    time_since_last = now - db_user.email_last_checked
                    interval_needed = timedelta(minutes=db_user.email_check_interval)
                    
                    if time_since_last < interval_needed:
                        # Not time to check yet for this user
                        continue
                
                # Create IMAP service for this user
                imap_service = GmailIMAPService(
                    db_user.email_address, 
                    db_user.email_app_password
                )
                
                if not imap_service.connect():
                    logger.warning(f"Failed to connect to email for user {db_user.telegram_id}")
                    continue
                
                # Update last checked time
                await user_repo.update_email_last_checked(db_user.id)
                
                # Get unread invoices
                invoices = imap_service.get_unread_invoices(limit=10)
                
                if not invoices:
                    imap_service.disconnect()
                    continue
                
                # Process each invoice
                for email_msg in invoices:
                    try:
                        # Parse invoice with GPT
                        parsed = await email_invoice_parser.parse_invoice_email(email_msg)
                        
                        if not parsed or parsed.amount <= 0:
                            continue
                        
                        # Find category
                        category = await category_repo.get_by_name(parsed.category)
                        category_id = category.id if category else None
                        category_display = f"{category.emoji} {category.name}" if category else f"💰 {parsed.category}"
                        
                        # Create expense (pending)
                        expense = await expense_repo.create(
                            user_id=db_user.id,
                            amount=parsed.amount,
                            description=parsed.description,
                            category_id=category_id,
                            currency=parsed.currency,
                            merchant=parsed.merchant,
                            source="email",
                            expense_date=parsed.date,
                            original_message=f"Email: {parsed.original_subject}",
                            is_confirmed=False
                        )
                        
                        date_str = parsed.date.strftime("%d/%m/%Y")
                        
                        confirmation_text = f"""📧 <b>Nueva factura detectada:</b>

💵 Monto: <b>${parsed.amount:,.2f} {parsed.currency}</b>
📂 Categoría: {category_display}
🏪 Comercio: {parsed.merchant}
📋 Descripción: {parsed.description}
📅 Fecha: {date_str}

💳 <b>¿Cómo pagaste?</b>"""
                        
                        keyboard = [
                            [
                                InlineKeyboardButton("💵 Efectivo", callback_data=f"emailpay_efectivo_{expense.id}"),
                                InlineKeyboardButton("💳 Tarjeta", callback_data=f"emailpay_tarjeta_{expense.id}"),
                            ],
                            [
                                InlineKeyboardButton("🏦 Transferencia", callback_data=f"emailpay_transferencia_{expense.id}"),
                            ],
                            [
                                InlineKeyboardButton("❌ Descartar", callback_data=f"email_cancel_{expense.id}")
                            ]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        # Send notification to user
                        await context.bot.send_message(
                            chat_id=db_user.telegram_id,
                            text=confirmation_text,
                            parse_mode="HTML",
                            reply_markup=reply_markup
                        )
                        
                        # Mark email as read
                        imap_service.mark_as_read(email_msg.email_id)
                        
                    except Exception as e:
                        logger.error(f"Error processing email for user {db_user.telegram_id}: {e}")
                        continue
                
                imap_service.disconnect()
                
            except Exception as e:
                logger.error(f"Error in auto-check for user {db_user.telegram_id}: {e}")
                continue
    
    logger.info("Automatic email check job completed.")


# Job runs every 5 minutes, but each user has their own interval
EMAIL_JOB_INTERVAL_MINUTES = 5


async def set_email_interval_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /email_interval command - set email check frequency."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    user = update.effective_user
    args = context.args
    
    # Get current user settings
    async with get_session() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(user.id)
        
        if not db_user or not db_user.email_address:
            await update.message.reply_text(
                "📧 Primero conecta tu email con /conectar_email"
            )
            return
        
        current_interval = db_user.email_check_interval or 30
    
    if not args:
        await update.message.reply_text(
            f"⏱️ <b>¿Cada cuánto reviso tu correo?</b>\n\n"
            f"Ahora: cada <b>{current_interval} minutos</b>\n\n"
            f"<b>Para cambiar, escribe:</b>\n"
            f"<code>/cada_cuanto 15</code> - Cada 15 min\n"
            f"<code>/cada_cuanto 30</code> - Cada 30 min\n"
            f"<code>/cada_cuanto 60</code> - Cada hora\n\n"
            f"💡 Mínimo 5 min, máximo 24 horas",
            parse_mode="HTML"
        )
        return
    
    try:
        minutes = int(args[0])
        
        if minutes < 5:
            await update.message.reply_text("⚠️ El intervalo mínimo es 5 minutos.")
            return
        
        if minutes > 1440:
            await update.message.reply_text("⚠️ El intervalo máximo es 1440 minutos (24 horas).")
            return
        
        async with get_session() as session:
            user_repo = UserRepository(session)
            await user_repo.set_email_check_interval(user.id, minutes)
        
        # Format display
        if minutes >= 60:
            hours = minutes // 60
            mins = minutes % 60
            if mins:
                display = f"{hours}h {mins}min"
            else:
                display = f"{hours} hora{'s' if hours > 1 else ''}"
        else:
            display = f"{minutes} minutos"
        
        await update.message.reply_text(
            f"✅ <b>Intervalo actualizado</b>\n\n"
            f"⏱️ Revisaré tu correo cada <b>{display}</b>",
            parse_mode="HTML"
        )
        await update.message.reply_text(
            "📋 <b>¿Qué más quieres hacer?</b>",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ Escribe un número válido.\n"
            "Ejemplo: <code>/cada_cuanto 30</code>",
            parse_mode="HTML"
        )
        await update.message.reply_text(
            "📋 <b>¿Qué quieres hacer?</b>",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )


def create_application() -> Application:
    """Create and configure the Telegram bot application."""
    
    # Validate config
    missing = config.validate()
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
    
    # Create application
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers - Super intuitive Spanish commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("ayuda", help_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # Ver gastos
    application.add_handler(CommandHandler("misgastos", stats_command))
    application.add_handler(CommandHandler("este_ano", stats_year_command))
    application.add_handler(CommandHandler("ultimos", history_command))
    application.add_handler(CommandHandler("tipos", categories_command))
    
    # Editar
    application.add_handler(CommandHandler("quitar", delete_command))
    application.add_handler(CommandHandler("borrar_todo", clear_command))
    
    # Email
    application.add_handler(CommandHandler("conectar_email", setup_email_command))
    application.add_handler(CommandHandler("desconectar_email", remove_email_command))
    application.add_handler(CommandHandler("auto_facturas", toggle_auto_email_command))
    application.add_handler(CommandHandler("cada_cuanto", set_email_interval_command))
    application.add_handler(CommandHandler("buscar_facturas", check_emails_command))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    
    # Callback query handler
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Schedule automatic email checking job (runs every 5 min, respects user intervals)
    job_queue = application.job_queue
    job_queue.run_repeating(
        auto_check_emails_job,
        interval=EMAIL_JOB_INTERVAL_MINUTES * 60,  # Convert to seconds
        first=60  # Start after 1 minute
    )
    
    return application
