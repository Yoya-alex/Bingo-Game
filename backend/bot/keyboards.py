from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from bot.utils.i18n import tr


def main_menu_keyboard(language='en'):
    """Main menu keyboard"""
    keyboard = [
        [KeyboardButton(text=tr(language, 'menu_play'))],
        [KeyboardButton(text=tr(language, 'menu_balance')), KeyboardButton(text=tr(language, 'menu_rules'))],
        [KeyboardButton(text=tr(language, 'menu_deposit')), KeyboardButton(text=tr(language, 'menu_withdraw'))],
        [KeyboardButton(text=tr(language, 'menu_invites')), KeyboardButton(text=tr(language, 'menu_language'))],
        [KeyboardButton(text=tr(language, 'menu_support'))]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_main_menu_keyboard(language='en'):
    """Admin main menu keyboard"""
    keyboard = [
        [KeyboardButton(text=tr(language, 'admin_menu_dashboard'))],
        [KeyboardButton(text=tr(language, 'admin_menu_deposits')), KeyboardButton(text=tr(language, 'admin_menu_withdrawals'))],
        [KeyboardButton(text=tr(language, 'admin_menu_system_balance'))],
        [KeyboardButton(text=tr(language, 'admin_menu_engagement'))],
        [KeyboardButton(text=tr(language, 'admin_menu_wallet')), KeyboardButton(text=tr(language, 'admin_menu_game'))],
        [KeyboardButton(text=tr(language, 'admin_menu_users')), KeyboardButton(text=tr(language, 'admin_menu_transactions'))],
        [KeyboardButton(text=tr(language, 'admin_menu_announcement'))],
        [KeyboardButton(text=tr(language, 'admin_menu_settings')), KeyboardButton(text=tr(language, 'admin_menu_search'))],
        [KeyboardButton(text=tr(language, 'menu_user')), KeyboardButton(text=tr(language, 'menu_language'))],
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


def system_balance_action_keyboard():
    """Inline actions for system balance management."""
    keyboard = [
        [
            InlineKeyboardButton(text="💸 Cash In", callback_data="sysbal:cash_in"),
            InlineKeyboardButton(text="💵 Cash Out", callback_data="sysbal:cash_out"),
        ],
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="sysbal:refresh")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def engagement_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(text="🎟 Promo Codes", callback_data="eng:promo:list"),
            InlineKeyboardButton(text="➕ Create Promo", callback_data="eng:promo:create"),
        ],
        [
            InlineKeyboardButton(text="🎉 Live Events", callback_data="eng:event:list"),
            InlineKeyboardButton(text="➕ Create Event", callback_data="eng:event:create"),
        ],
        [
            InlineKeyboardButton(text="🎯 Missions", callback_data="eng:mission:list"),
            InlineKeyboardButton(text="🏆 Seasons", callback_data="eng:season:list"),
        ],
        [
            InlineKeyboardButton(text="🛡 Reward Policy", callback_data="eng:policy:show"),
            InlineKeyboardButton(text="⚙ Update Policy", callback_data="eng:policy:set"),
        ],
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="eng:refresh")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def engagement_promo_tier_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(text="Common", callback_data="eng:promo:tier:common"),
            InlineKeyboardButton(text="Rare", callback_data="eng:promo:tier:rare"),
            InlineKeyboardButton(text="Legendary", callback_data="eng:promo:tier:legendary"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def engagement_balance_target_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(text="Bonus", callback_data="eng:promo:balance:bonus"),
            InlineKeyboardButton(text="Main", callback_data="eng:promo:balance:main"),
            InlineKeyboardButton(text="Winnings", callback_data="eng:promo:balance:winnings"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def engagement_frontend_visibility_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(text="Show In Frontend", callback_data="eng:promo:frontend:show"),
            InlineKeyboardButton(text="Hide From Frontend", callback_data="eng:promo:frontend:hide"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def engagement_event_type_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(text="Happy Hour", callback_data="eng:event:type:happy_hour"),
            InlineKeyboardButton(text="Flash Promo", callback_data="eng:event:type:flash_promo"),
        ],
        [InlineKeyboardButton(text="Double Reward", callback_data="eng:event:type:double_reward")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
