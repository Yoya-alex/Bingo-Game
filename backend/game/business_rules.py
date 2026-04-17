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
