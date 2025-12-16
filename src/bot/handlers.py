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

logger = logging.getLogger(__name__)


def is_user_allowed(user_id: int) -> bool:
    """Check if user is allowed to use the bot."""
    if not config.ALLOWED_USER_IDS:
        return True  # Allow all if no restriction set
    return user_id in config.ALLOWED_USER_IDS


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ No tienes permiso para usar este bot.")
        return
    
    user = update.effective_user
    
    # Create or get user in database
    async with get_session() as session:
        user_repo = UserRepository(session)
        category_repo = CategoryRepository(session)
        
        db_user, created = await user_repo.get_or_create(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        # Initialize default categories if needed
        await category_repo.initialize_default_categories()
    
    welcome_message = f"""👋 ¡Hola {user.first_name}! Soy tu bot de gastos personales.

💡 <b>¿Cómo usarme?</b>
• Envíame un mensaje de texto con tu gasto, por ejemplo:
  - "Gasté 150 en uber"
  - "500 pesos en supermercado"
  - "$200 café starbucks"

• También puedes enviarme un <b>mensaje de voz</b> 🎤

📊 <b>Comandos disponibles:</b>
/stats - Ver estadísticas del mes actual
/stats_year - Ver estadísticas del año
/categories - Ver categorías disponibles
/history - Ver últimos gastos
/help - Ver esta ayuda

¡Empecemos a registrar tus gastos! 💰"""
    await update.message.reply_text(welcome_message, parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    if not is_user_allowed(update.effective_user.id):
        return
    
    help_text = """📖 <b>Ayuda - Bot de Gastos</b>

<b>Registrar gastos:</b>
Simplemente envía un mensaje describiendo tu gasto:
• "Gasté 300 en gasolina"
• "uber 150"
• "Netflix 199 pesos"

También puedes enviar un <b>mensaje de voz</b> 🎤

<b>Comandos:</b>
/start - Iniciar el bot
/stats - Estadísticas del mes
/stats_year - Estadísticas del año
/categories - Ver categorías
/history - Últimos 10 gastos
/cancel - Cancelar operación actual
/help - Esta ayuda

<b>Confirmación:</b>
Después de cada gasto, te preguntaré si es correcto.
Presiona ✅ para confirmar o ❌ para cancelar."""
    await update.message.reply_text(help_text, parse_mode="HTML")


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
    
    history_text += "\n<i>Usa /delete [número] para eliminar un gasto</i>"
    
    await update.message.reply_text(history_text, parse_mode="HTML")


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
        user_repo = UserRepository(session)
        category_repo = CategoryRepository(session)
        expense_repo = ExpenseRepository(session)
        pending_repo = PendingConfirmationRepository(session)
        
        db_user = await user_repo.get_by_telegram_id(user.id)
        if not db_user:
            db_user, _ = await user_repo.get_or_create(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name
            )
        
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

¿Es correcto?"""
        
        # Inline keyboard for confirmation
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
            user_repo = UserRepository(session)
            category_repo = CategoryRepository(session)
            expense_repo = ExpenseRepository(session)
            pending_repo = PendingConfirmationRepository(session)
            
            db_user = await user_repo.get_by_telegram_id(user.id)
            if not db_user:
                db_user, _ = await user_repo.get_or_create(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name
                )
            
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
    
    elif data == "clear_cancel":
        await query.edit_message_text("✅ Operación cancelada. Tus gastos están seguros.")


def create_application() -> Application:
    """Create and configure the Telegram bot application."""
    
    # Validate config
    missing = config.validate()
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
    
    # Create application
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("stats_year", stats_year_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("clear", clear_command))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    
    # Callback query handler
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    return application
