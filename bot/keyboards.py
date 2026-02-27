from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_keyboard():
    """Main menu keyboard"""
    keyboard = [
        [KeyboardButton(text="🎮 Play Bingo")],
        [KeyboardButton(text="💰 Balance"), KeyboardButton(text="📜 Rules")],
        [KeyboardButton(text="➕ Deposit"), KeyboardButton(text="➖ Withdraw")],
        [KeyboardButton(text="🆘 Support")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_main_menu_keyboard():
    """Admin main menu keyboard"""
    keyboard = [
        [KeyboardButton(text="📊 Dashboard")],
        [KeyboardButton(text="💰 Deposits"), KeyboardButton(text="🏧 Withdrawals")],
        [KeyboardButton(text="👛 Wallet Management"), KeyboardButton(text="🎮 Game Management")],
        [KeyboardButton(text="👤 User Management"), KeyboardButton(text="📜 Transaction Logs")],
        [KeyboardButton(text="⚙️ Settings"), KeyboardButton(text="🔍 Search")],
        [KeyboardButton(text="🏠 User Menu")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def card_selection_keyboard(available_cards, page=0, cards_per_page=50):
    """Generate inline keyboard for card selection (1-400) with pagination"""
    # Calculate pagination
    start_idx = page * cards_per_page
    end_idx = start_idx + cards_per_page
    page_cards = available_cards[start_idx:end_idx]
    
    buttons = []
    
    # Create rows of 10 cards each
    for i in range(0, len(page_cards), 10):
        row = []
        for card_num in page_cards[i:i+10]:
            row.append(InlineKeyboardButton(
                text=str(card_num),
                callback_data=f"select_card:{card_num}"
            ))
        buttons.append(row)
    
    # Add navigation buttons
    nav_row = []
    
    # Previous page button
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            text="⬅️ Previous",
            callback_data=f"cards_page:{page-1}"
        ))
    
    # Page indicator
    total_pages = (len(available_cards) + cards_per_page - 1) // cards_per_page
    nav_row.append(InlineKeyboardButton(
        text=f"📄 {page+1}/{total_pages}",
        callback_data="page_info"
    ))
    
    # Next page button
    if end_idx < len(available_cards):
        nav_row.append(InlineKeyboardButton(
            text="Next ➡️",
            callback_data=f"cards_page:{page+1}"
        ))
    
    if nav_row:
        buttons.append(nav_row)
    
    # Add back button
    buttons.append([InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def bingo_button_keyboard():
    """BINGO button for players"""
    keyboard = [[InlineKeyboardButton(text="🎯 BINGO!", callback_data="claim_bingo")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def deposit_keyboard():
    """Deposit options keyboard"""
    keyboard = [
        [InlineKeyboardButton(text="📤 Submit Deposit Proof", callback_data="submit_deposit")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def withdrawal_keyboard():
    """Withdrawal options keyboard"""
    keyboard = [
        [InlineKeyboardButton(text="💸 Request Withdrawal", callback_data="request_withdrawal")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def payment_method_keyboard():
    """Payment method selection keyboard for withdrawal"""
    keyboard = [
        [InlineKeyboardButton(text="🏦 CBE (Commercial Bank of Ethiopia)", callback_data="payment_method:cbe")],
        [InlineKeyboardButton(text="📱 Telebirr", callback_data="payment_method:telebirr")],
        [InlineKeyboardButton(text="🔙 Cancel", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def wallet_balance_type_keyboard():
    """Inline options for wallet balance type selection."""
    keyboard = [
        [
            InlineKeyboardButton(text="Main", callback_data="wallet_balance:main"),
            InlineKeyboardButton(text="Bonus", callback_data="wallet_balance:bonus"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def wallet_direction_keyboard():
    """Inline options for wallet adjustment direction."""
    keyboard = [
        [
            InlineKeyboardButton(text="Add", callback_data="wallet_direction:add"),
            InlineKeyboardButton(
                text="Subtract", callback_data="wallet_direction:subtract"
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
