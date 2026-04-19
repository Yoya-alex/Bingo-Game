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


@router.message(F.text == "🎮 Play Bingo")
async def play_bingo(message: Message):
    """Send web app link to play bingo"""
    user = await get_user_with_wallet(message.from_user.id)
    admin_user = await is_admin(message.from_user.id)
    show_direct_link = bool(admin_user or getattr(settings, 'DEBUG', False))
    
    if not user:
        await message.answer("❌ Please start the bot first with /start")
        return
    
    wallet = user.wallet
    
    # Check balance
    if wallet.total_balance < settings.CARD_PRICE:
        await message.answer(
            f"❌ <b>Insufficient Balance!</b>\n\n"
            f"You need at least {settings.CARD_PRICE} Birr to play.\n"
            f"Your balance: {wallet.total_balance} Birr\n\n"
            f"Please deposit to continue.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Generate web app URL
    access_token = create_user_access_token(user.telegram_id)
    web_url = build_react_url("/", telegram_id=user.telegram_id, token=access_token)
    
    # Use WebApp button on HTTPS. On HTTP, use URL button only when Telegram accepts it.
    is_https = web_url.startswith("https://")
    can_use_button_url = can_use_telegram_button_url(web_url)
    
    if is_https:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="▶️ Play",
                web_app=WebAppInfo(url=web_url)
            )
        ]])
        game_text = (
            f"<b>🎮 BINGO GAME</b>\n\n"
            f"💰 Your Balance: {wallet.total_balance} Birr\n"
            f"💵 Card Price: {settings.CARD_PRICE} Birr\n\n"
            f"Tap the button below to open the game!"
        )
        if show_direct_link:
            game_text += f"\n\n<b>🔗 Direct Link:</b>\n<code>{web_url}</code>"
        await message.answer(game_text, reply_markup=keyboard)
    else:
        keyboard = None
        if can_use_button_url:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="▶️ Play",
                    url=web_url,
                )
            ]])
        game_text = (
            f"<b>🎮 BINGO GAME</b>\n\n"
            f"💰 Your Balance: {wallet.total_balance} Birr\n"
            f"💵 Card Price: {settings.CARD_PRICE} Birr\n\n"
            f"Tap the Play button below to open the game."
        )
        if show_direct_link:
            game_text += (
                f"\n\n<b>📋 Direct Link:</b>\n"
                f"<code>{web_url}</code>\n\n"
                f"<i>💡 Long press the URL above to copy it</i>"
            )
        if not can_use_button_url:
            if show_direct_link:
                game_text += "\n\n<i>⚠ Telegram may reject localhost URL buttons in development; use the direct link above.</i>"
            else:
                game_text += "\n\n<i>⚠ Play button is unavailable with the current development URL. Please contact the admin.</i>"
        await message.answer(game_text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("cards_page:"))
async def change_cards_page(callback: CallbackQuery):
    """Handle card page navigation"""
    try:
        page = int(callback.data.split(":")[1])
        user = await get_user_with_wallet(callback.from_user.id)
        
        if not user:
            await callback.answer("❌ Please start the bot first!", show_alert=True)
            return
        
        wallet = user.wallet
        
        # Get active game
        game = await get_or_create_active_game()
        
        if game.state != 'waiting':
            await callback.answer("❌ Game already started!", show_alert=True)
            return
        
        # Get available cards
        cards = await get_game_cards(game)
        taken_cards = [card.card_number for card in cards]
        available_cards = [i for i in range(1, 401) if i not in taken_cards]
        
        if not available_cards:
            await callback.answer("❌ No cards available!", show_alert=True)
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
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)


@router.callback_query(F.data == "page_info")
async def page_info(callback: CallbackQuery):
    """Handle page info button click"""
    await callback.answer("Use Next/Previous buttons to browse cards", show_alert=False)


@router.callback_query(F.data.startswith("select_card:"))
async def select_card(callback: CallbackQuery):
    """Handle card selection"""
    try:
        card_number = int(callback.data.split(":")[1])
        user = await get_user_with_wallet(callback.from_user.id)
        
        if not user:
            await callback.answer("❌ Please start the bot first!", show_alert=True)
            return
        
        wallet = user.wallet
        
        # Get active game
        game = await get_or_create_active_game()
        
        if game.state != 'waiting':
            await callback.answer("❌ Game already started!", show_alert=True)
            return
        
        # Check if card is available
        is_available = await check_card_available(game, card_number)
        if not is_available:
            await callback.answer("❌ Card already taken!", show_alert=True)
            return
        
        # Check if user already has a card
        existing_card = await get_user_card_in_game(game, user)
        if existing_card:
            await callback.answer("❌ You already have a card!", show_alert=True)
            return
        
        # Check balance
        if wallet.total_balance < settings.CARD_PRICE:
            await callback.answer("❌ Insufficient balance!", show_alert=True)
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
        
        await callback.answer("✅ Card selected!", show_alert=True)
        await show_waiting_screen(callback.message, game, card)
        
    except Exception as e:
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)


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
    
    waiting_text = (
        f"<b>🎮 GAME #{game.id} - WAITING</b>\n\n"
        f"✅ Your Card: #{user_card.card_number}\n"
        f"👥 Players: {len(cards)}/400\n"
        f"⏱ Status: Waiting for more players...\n\n"
        f"<pre>{grid_text}</pre>\n"
        f"<i>Game will start automatically when ready.\n"
        f"(Auto-start feature coming soon!)</i>"
    )
    
    await message.answer(waiting_text, reply_markup=main_menu_keyboard())


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
    
    playing_text = (
        f"<b>🎮 GAME #{game.id} - PLAYING</b>\n\n"
        f"<pre>{grid_text}</pre>\n"
        f"<i>Number calling feature coming soon!\n"
        f"Full game automation in development.</i>"
    )
    
    await message.answer(playing_text, reply_markup=bingo_button_keyboard())


@router.callback_query(F.data == "claim_bingo")
async def claim_bingo(callback: CallbackQuery):
    """Handle BINGO claim"""
    try:
        user = await get_user_with_wallet(callback.from_user.id)
        if not user:
            await callback.answer("❌ User not found!", show_alert=True)
            return
        
        # Get user's active card
        game = await sync_to_async(Game.objects.filter(state__in=['waiting', 'playing']).first)()
        if not game:
            await callback.answer("❌ No active game!", show_alert=True)
            return
        
        user_card = await get_user_card_in_game(game, user)
        if not user_card:
            await callback.answer("❌ You don't have a card in this game!", show_alert=True)
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
                f"🎉 BINGO! You won {prize} Birr!\n"
                f"Pattern: {pattern}",
                show_alert=True
            )
            
            # Show win message
            await callback.message.answer(
                f"<b>🏆 CONGRATULATIONS! 🏆</b>\n\n"
                f"You won Game #{game.id}!\n"
                f"Pattern: {pattern}\n"
                f"Prize: {prize} Birr\n\n"
                f"💰 Your new balance: {user.wallet.total_balance} Birr",
                reply_markup=main_menu_keyboard()
            )
        else:
            await callback.answer(
                "❌ Not a valid BINGO yet!\n"
                "Keep playing and wait for more numbers.",
                show_alert=True
            )
    
    except Exception as e:
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)
