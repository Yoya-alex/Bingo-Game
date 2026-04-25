from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from django.conf import settings
from django.utils import timezone
from asgiref.sync import sync_to_async
from decimal import Decimal

from users.models import User
from game.models import Game, BingoCard
from wallet.models import Transaction
from bot.keyboards import main_menu_keyboard, card_selection_keyboard, bingo_button_keyboard
from bot.utils.admin_helpers import is_admin
from bot.utils.game_logic import check_bingo_win
from bot.utils.i18n import is_menu_text, normalize_language, tr
from bot.utils.url_helpers import build_react_url, can_use_telegram_button_url
from game.security import create_user_access_token

router = Router()


@sync_to_async
def get_user_with_wallet(telegram_id):
    try:
        user = User.objects.select_related('wallet').get(telegram_id=telegram_id)
        return user
    except User.DoesNotExist:
        return None


@sync_to_async
def get_or_create_active_game():
    """Get active game or create new one"""
    game = Game.objects.filter(state__in=['waiting', 'playing']).first()
    if not game:
        game = Game.objects.create(state='waiting')
    return game


@sync_to_async
def get_game_cards(game):
    """Get all cards for a game"""
    return list(game.cards.select_related('user').all())


@sync_to_async
def get_user_card_in_game(game, user):
    """Check if user has a card in this game"""
    try:
        return game.cards.get(user=user)
    except BingoCard.DoesNotExist:
        return None


@sync_to_async
def check_card_available(game, card_number):
    """Check if card number is available"""
    return not game.cards.filter(card_number=card_number).exists()


@sync_to_async
def create_bingo_card(game, user, card_number):
    """Create a bingo card"""
    return BingoCard.objects.create(
        game=game,
        user=user,
        card_number=card_number
    )


@sync_to_async
def update_wallet_balance(wallet, amount):
    """Deduct amount from wallet"""
    remaining = Decimal(str(amount))

    main_to_use = min(wallet.main_balance, remaining)
    wallet.main_balance -= main_to_use
    remaining -= main_to_use

    if remaining > 0:
        bonus_to_use = min(wallet.bonus_balance, remaining)
        wallet.bonus_balance -= bonus_to_use
        remaining -= bonus_to_use

    if remaining > 0:
        winnings_to_use = min(wallet.winnings_balance, remaining)
        wallet.winnings_balance -= winnings_to_use
        remaining -= winnings_to_use

    if remaining > 0:
        raise ValueError("Insufficient balance to deduct card price")

    if wallet.main_balance < 0 or wallet.bonus_balance < 0 or wallet.winnings_balance < 0:
        raise ValueError("Wallet balance underflow detected")
    wallet.save()
    return wallet


@sync_to_async
def create_game_transaction(user, amount, description):
    """Create game entry transaction"""
    return Transaction.objects.create(
        user=user,
        transaction_type='game_entry',
        amount=amount,
        status='approved',
        description=description
    )


@sync_to_async
def get_game_with_cards(game_id):
    """Get game with all its cards"""
    try:
        return Game.objects.prefetch_related('cards__user').get(id=game_id)
    except Game.DoesNotExist:
        return None


@sync_to_async
def mark_winner_and_distribute_prize(game, user_card):
    """Mark winner and distribute prize"""
    # Auto-transition to playing if still waiting
    if game.state == 'waiting' and game.cards.count() >= settings.GAME_MIN_PLAYERS:
        game.state = 'playing'
        game.started_at = timezone.now()
    
    # Calculate prize
    total_cards = game.cards.count()
    prize = total_cards * settings.CARD_PRICE
    
    # Update game
    game.prize_amount = prize
    game.winner = user_card.user
    game.state = 'finished'
    game.finished_at = timezone.now()
    game.save()
    
    # Mark card as winner
    user_card.is_winner = True
    user_card.save()
    
    # Credit prize to user's main balance
    wallet = user_card.user.wallet
    wallet.main_balance += prize
    wallet.save()
    
    # Log transaction
    Transaction.objects.create(
        user=user_card.user,
        transaction_type='game_win',
        amount=prize,
        status='approved',
        description=f'Won Game #{game.id}'
    )
    
    return prize


@router.message(lambda message: is_menu_text(message.text, 'menu_play'))
async def play_bingo(message: Message):
    """Send web app link to play bingo"""
    user = await get_user_with_wallet(message.from_user.id)
    admin_user = await is_admin(message.from_user.id)
    show_direct_link = bool(admin_user or getattr(settings, 'DEBUG', False))
    
    if not user:
        await message.answer(tr('en', 'please_start'))
        return
    
    wallet = user.wallet
    language = normalize_language(user.language)
    
    # Check balance
    if wallet.total_balance < settings.CARD_PRICE:
        await message.answer(
            tr(
                language,
                'game_insufficient_balance',
                card_price=settings.CARD_PRICE,
                total_balance=wallet.total_balance,
            ),
            reply_markup=main_menu_keyboard(language)
        )
        return
    
    # Generate web app URL
    access_token = create_user_access_token(user.telegram_id)
    web_url = build_react_url("/", telegram_id=user.telegram_id, token=access_token, lang=language)
    
    # Use WebApp button on HTTPS. On HTTP, use URL button only when Telegram accepts it.
    is_https = web_url.startswith("https://")
    can_use_button_url = can_use_telegram_button_url(web_url)
    
    if is_https:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=tr(language, 'btn_play_now'),
                web_app=WebAppInfo(url=web_url)
            )
        ]])
        game_text = (
            f"{tr(language, 'game_card_title')}\n\n"
            f"{tr(language, 'game_balance_line', total_balance=wallet.total_balance)}\n"
            f"{tr(language, 'game_card_price_line', card_price=settings.CARD_PRICE)}\n\n"
            f"{tr(language, 'game_open_hint')}"
        )
        if show_direct_link:
            game_text += f"\n\n{tr(language, 'game_direct_link', web_url=web_url)}"
        await message.answer(game_text, reply_markup=keyboard)
    else:
        keyboard = None
        if can_use_button_url:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=tr(language, 'btn_play_now'),
                    url=web_url,
                )
            ]])
        game_text = (
            f"{tr(language, 'game_card_title')}\n\n"
            f"{tr(language, 'game_balance_line', total_balance=wallet.total_balance)}\n"
            f"{tr(language, 'game_card_price_line', card_price=settings.CARD_PRICE)}\n\n"
            f"{tr(language, 'game_open_hint_http')}"
        )
        if show_direct_link:
            game_text += f"\n\n{tr(language, 'game_direct_link_copy', web_url=web_url)}"
        if not can_use_button_url:
            if show_direct_link:
                game_text += f"\n\n{tr(language, 'game_localhost_warn_admin')}"
            else:
                game_text += f"\n\n{tr(language, 'game_localhost_warn_user')}"
        await message.answer(game_text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("cards_page:"))
async def change_cards_page(callback: CallbackQuery):
    """Handle card page navigation"""
    try:
        page = int(callback.data.split(":")[1])
        user = await get_user_with_wallet(callback.from_user.id)
        language = normalize_language(getattr(user, 'language', None))
        
        if not user:
            await callback.answer(tr('en', 'cb_start_first'), show_alert=True)
            return
        
        wallet = user.wallet
        
        # Get active game
        game = await get_or_create_active_game()
        
        if game.state != 'waiting':
            await callback.answer(tr(language, 'cb_game_started'), show_alert=True)
            return
        
        # Get available cards
        cards = await get_game_cards(game)
        taken_cards = [card.card_number for card in cards]
        available_cards = [i for i in range(1, 401) if i not in taken_cards]
        
        if not available_cards:
            await callback.answer(tr(language, 'cb_no_cards'), show_alert=True)
            return
        
        game_text = (
            f"<b>🎮 BINGO GAME #{game.id}</b>\n\n"
            f"⏱ Status: WAITING\n"
            f"👥 Players: {len(cards)}/400\n"
            f"💰 Card Price: {settings.CARD_PRICE} Birr\n"
            f"💵 Your Balance: {wallet.total_balance} Birr\n\n"
            f"📋 Available Cards: {len(available_cards)}/400\n\n"
            f"Select your card number (1-400):\n"
            f"<i>Use Next/Previous to browse all cards</i>"
        )
        
        # Show cards with pagination
        keyboard = card_selection_keyboard(available_cards, page=page)
        
        await callback.message.edit_text(game_text, reply_markup=keyboard)
        await callback.answer()
        
    except Exception as e:
        await callback.answer(tr('en', 'cb_error', error=str(e)), show_alert=True)


@router.callback_query(F.data == "page_info")
async def page_info(callback: CallbackQuery):
    """Handle page info button click"""
    user = await get_user_with_wallet(callback.from_user.id)
    language = normalize_language(getattr(user, 'language', None))
    await callback.answer(tr(language, 'cb_page_info'), show_alert=False)


@router.callback_query(F.data.startswith("select_card:"))
async def select_card(callback: CallbackQuery):
    """Handle card selection"""
    try:
        card_number = int(callback.data.split(":")[1])
        user = await get_user_with_wallet(callback.from_user.id)
        language = normalize_language(getattr(user, 'language', None))
        
        if not user:
            await callback.answer(tr('en', 'cb_start_first'), show_alert=True)
            return
        
        wallet = user.wallet
        
        # Get active game
        game = await get_or_create_active_game()
        
        if game.state != 'waiting':
            await callback.answer(tr(language, 'cb_game_started'), show_alert=True)
            return
        
        # Check if card is available
        is_available = await check_card_available(game, card_number)
        if not is_available:
            await callback.answer(tr(language, 'cb_card_taken'), show_alert=True)
            return
        
        # Check if user already has a card
        existing_card = await get_user_card_in_game(game, user)
        if existing_card:
            await callback.answer(tr(language, 'cb_already_have_card'), show_alert=True)
            return
        
        # Check balance
        if wallet.total_balance < settings.CARD_PRICE:
            await callback.answer(tr(language, 'cb_insufficient_balance'), show_alert=True)
            return
        
        # Deduct balance
        await update_wallet_balance(wallet, settings.CARD_PRICE)
        
        # Log transaction
        await create_game_transaction(
            user, 
            settings.CARD_PRICE, 
            f'Game #{game.id} - Card #{card_number}'
        )
        
        # Create card
        card = await create_bingo_card(game, user, card_number)
        
        await callback.answer(tr(language, 'cb_card_selected'), show_alert=True)
        await show_waiting_screen(callback.message, game, card)
        
    except Exception as e:
        await callback.answer(tr('en', 'cb_error', error=str(e)), show_alert=True)


async def show_waiting_screen(message: Message, game, user_card):
    """Show waiting screen with user's grid"""
    grid = user_card.get_grid()
    
    # Format grid
    grid_text = "YOUR BINGO CARD:\n\n"
    grid_text += "  B   I   N   G   O\n"
    for row in grid:
        row_text = ""
        for num in row:
            if num is None:
                row_text += " 🆓 "
            else:
                row_text += f"{num:3d}"
        grid_text += row_text + "\n"
    
    cards = await get_game_cards(game)
    
    user = await get_user_with_wallet(message.chat.id)
    language = normalize_language(getattr(user, 'language', None))
    waiting_text = tr(
        language,
        'game_waiting_text',
        game_id=game.id,
        card_number=user_card.card_number,
        players=len(cards),
        grid_text=grid_text,
    )
    
    await message.answer(waiting_text, reply_markup=main_menu_keyboard(language))


async def show_playing_screen(message: Message, game, user_card):
    """Show playing screen (simplified for now)"""
    grid = user_card.get_grid()
    
    # Format grid
    grid_text = "YOUR BINGO CARD:\n\n"
    grid_text += "  B   I   N   G   O\n"
    for row in grid:
        row_text = ""
        for num in row:
            if num is None:
                row_text += " 🆓 "
            else:
                row_text += f"{num:3d}"
        grid_text += row_text + "\n"
    
    user = await get_user_with_wallet(message.chat.id)
    language = normalize_language(getattr(user, 'language', None))
    playing_text = tr(language, 'game_playing_text', game_id=game.id, grid_text=grid_text)
    
    await message.answer(playing_text, reply_markup=bingo_button_keyboard())


@router.callback_query(F.data == "claim_bingo")
async def claim_bingo(callback: CallbackQuery):
    """Handle BINGO claim"""
    try:
        user = await get_user_with_wallet(callback.from_user.id)
        if not user:
            await callback.answer(tr('en', 'cb_user_not_found'), show_alert=True)
            return
        language = normalize_language(user.language)
        
        # Get user's active card
        game = await sync_to_async(Game.objects.filter(state__in=['waiting', 'playing']).first)()
        if not game:
            await callback.answer(tr(language, 'cb_no_active_game'), show_alert=True)
            return
        
        user_card = await get_user_card_in_game(game, user)
        if not user_card:
            await callback.answer(tr(language, 'cb_no_card_in_game'), show_alert=True)
            return
        
        # Validate BINGO
        grid = user_card.get_grid()
        called_numbers = game.get_called_numbers()
        is_winner, pattern = check_bingo_win(grid, called_numbers)
        
        if is_winner:
            # Process win
            prize = await mark_winner_and_distribute_prize(game, user_card)

            # Refresh wallet to reflect credited prize before displaying balance.
            await sync_to_async(user.wallet.refresh_from_db)()
            
            await callback.answer(
                tr(language, 'cb_bingo_win_alert', prize=prize, pattern=pattern),
                show_alert=True
            )
            
            # Show win message
            await callback.message.answer(
                tr(
                    language,
                    'game_win_message',
                    game_id=game.id,
                    pattern=pattern,
                    prize=prize,
                    total_balance=user.wallet.total_balance,
                ),
                reply_markup=main_menu_keyboard(normalize_language(user.language))
            )
        else:
            await callback.answer(
                tr(language, 'cb_bingo_invalid'),
                show_alert=True
            )
    
    except Exception as e:
        await callback.answer(tr('en', 'cb_error', error=str(e)), show_alert=True)
