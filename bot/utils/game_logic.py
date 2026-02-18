import hashlib
import random
from django.conf import settings


CARD_VERSION = "bingo_v1"
_CARD_LAYOUT_CACHE = {}


def _seed_from_text(seed_text):
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return int(digest, 16)


def _layout_signature(grid):
    return tuple(tuple(row) for row in grid)


def _column_ranges(max_number):
    max_number = max(5, int(max_number))
    step = max_number // 5
    ranges = []
    start = 1
    for col in range(5):
        end = max_number if col == 4 else start + step - 1
        ranges.append((start, end))
        start = end + 1
    return ranges


def _build_grid_for_seed(seed_text, max_number):
    rng = random.Random(_seed_from_text(seed_text))
    columns = []

    for start, end in _column_ranges(max_number):
        pool = list(range(start, end + 1))
        rng.shuffle(pool)
        columns.append(pool[:5])

    grid = [[columns[col][row] for col in range(5)] for row in range(5)]
    grid[2][2] = None
    return grid


def _build_layout_cache(card_count, max_number):
    cache = {}
    seen = set()

    for number in range(1, card_count + 1):
        attempt = 0
        while True:
            if attempt == 0:
                seed_text = f"{CARD_VERSION}_{number}"
            else:
                seed_text = f"{CARD_VERSION}_{number}_retry_{attempt}"

            grid = _build_grid_for_seed(seed_text, max_number)
            signature = _layout_signature(grid)

            if signature not in seen:
                seen.add(signature)
                cache[number] = grid
                break

            attempt += 1

    return cache


def generate_bingo_card(card_number):
    """Deterministically generate a 5x5 standard Bingo card for a card number."""
    normalized = int(card_number)
    card_count = max(1, int(getattr(settings, "CARD_COUNT", 400)))
    max_number = max(5, int(getattr(settings, "BINGO_NUMBER_MAX", 400)))
    if normalized < 1 or normalized > card_count:
        raise ValueError("Invalid card number")

    cache_key = (CARD_VERSION, card_count, max_number)
    cache = _CARD_LAYOUT_CACHE.get(cache_key)
    if cache is None:
        cache = _build_layout_cache(card_count, max_number)
        _CARD_LAYOUT_CACHE[cache_key] = cache

    return [row[:] for row in cache[normalized]]


def generateBingoCard(card_number):
    """CamelCase alias required by integration contract."""
    return generate_bingo_card(card_number)


def generate_bingo_grid(card_number=1):
    """Backward-compatible alias."""
    return generate_bingo_card(card_number)


def check_bingo_win(grid, called_numbers):
    """
    Check if the grid has a winning pattern
    Returns: (is_winner, pattern_name)
    """
    called_set = set(called_numbers)
    
    # Check horizontal lines
    for i, row in enumerate(grid):
        if all(num is None or num in called_set for num in row):
            return True, f"Horizontal Row {i+1}"
    
    # Check vertical lines
    for col in range(5):
        if all(grid[row][col] is None or grid[row][col] in called_set for row in range(5)):
            return True, f"Vertical Column {col+1}"
    
    # Check diagonal (top-left to bottom-right)
    if all(grid[i][i] is None or grid[i][i] in called_set for i in range(5)):
        return True, "Diagonal (↘)"
    
    # Check diagonal (top-right to bottom-left)
    if all(grid[i][4-i] is None or grid[i][4-i] in called_set for i in range(5)):
        return True, "Diagonal (↙)"
    
    return False, None


def get_next_number(called_numbers):
    """
    Get next random number that hasn't been called yet
    """
    max_number = max(1, int(getattr(settings, 'BINGO_NUMBER_MAX', 75)))
    available = [i for i in range(1, max_number + 1) if i not in called_numbers]
    if not available:
        return None
    return random.choice(available)
