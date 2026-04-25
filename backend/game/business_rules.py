from decimal import Decimal

from game.models import BusinessRuleSettings


def get_business_rules():
    return BusinessRuleSettings.get_active()


def get_derash_multiplier():
    rules = get_business_rules()
    return (rules.derash_percentage / Decimal('100')).quantize(Decimal('0.0001'))


def get_system_multiplier():
    rules = get_business_rules()
    return (rules.system_percentage / Decimal('100')).quantize(Decimal('0.0001'))


def get_countdown_seconds():
    rules = get_business_rules()
    return int(rules.countdown_seconds)


def get_winner_announcement_seconds():
    rules = get_business_rules()
    return int(getattr(rules, 'winner_announcement_seconds', 3) or 3)


def get_rejoin_start_delay_minutes():
    rules = get_business_rules()
    return int(getattr(rules, 'rejoin_start_delay_minutes', 0) or 0)
