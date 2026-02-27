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


def generate_winning_grid_from_called_numbers(called_numbers):
    """
    Generate a valid bingo grid that creates a winning pattern from the called numbers.
    This is used for bot wins to ensure they have a legitimate winning card.
    Returns: (grid, pattern_name)
    """
    if len(called_numbers) < 5:
        return None, None
    
    # Create a 5x5 grid
    grid = [[0 for _ in range(5)] for _ in range(5)]
    grid[2][2] = None  # Free space
    
    # Determine column ranges for standard bingo
    max_number = max(1, int(getattr(settings, 'BINGO_NUMBER_MAX', 75)))
    column_ranges = _column_ranges(max_number)
    
    # Choose a random winning pattern with descriptive names
    pattern_choices = [
        ('horizontal_0', 'Horizontal Row 1'),
        ('horizontal_1', 'Horizontal Row 2'),
        ('horizontal_2', 'Horizontal Row 3'),
        ('horizontal_3', 'Horizontal Row 4'),
        ('horizontal_4', 'Horizontal Row 5'),
        ('vertical_0', 'Vertical Column B'),
        ('vertical_1', 'Vertical Column I'),
        ('vertical_2', 'Vertical Column N'),
        ('vertical_3', 'Vertical Column G'),
        ('vertical_4', 'Vertical Column O'),
        ('diagonal_lr', 'Diagonal (↘)'),
        ('diagonal_rl', 'Diagonal (↙)')
    ]
    
    pattern_key, pattern_name = random.choice(pattern_choices)
    
    # Get positions for the winning pattern
    winning_positions = []
    
    if pattern_key.startswith('horizontal'):
        row = int(pattern_key.split('_')[1])
        winning_positions = [(row, col) for col in range(5)]
    elif pattern_key.startswith('vertical'):
        col = int(pattern_key.split('_')[1])
        winning_positions = [(row, col) for row in range(5)]
    elif pattern_key == 'diagonal_lr':
        winning_positions = [(i, i) for i in range(5)]
    elif pattern_key == 'diagonal_rl':
        winning_positions = [(i, 4-i) for i in range(5)]
    
    # Remove free space from winning positions if present
    winning_positions = [(r, c) for r, c in winning_positions if not (r == 2 and c == 2)]
    
    # Assign called numbers to winning positions
    called_copy = called_numbers.copy()
    random.shuffle(called_copy)
    
    for idx, (row, col) in enumerate(winning_positions):
        if idx < len(called_copy):
            # Make sure number fits in the column range
            num = called_copy[idx]
            col_start, col_end = column_ranges[col]
            
            # Find a called number that fits this column
            valid_num = None
            for n in called_copy:
                if col_start <= n <= col_end:
                    valid_num = n
                    called_copy.remove(n)
                    break
            
            if valid_num:
                grid[row][col] = valid_num
            else:
                # If no valid called number, use any from range
                grid[row][col] = random.randint(col_start, col_end)
    
    # Fill remaining positions with numbers from appropriate column ranges
    for row in range(5):
        for col in range(5):
            if grid[row][col] == 0 and not (row == 2 and col == 2):
                col_start, col_end = column_ranges[col]
                # Use uncalled numbers
                available = [n for n in range(col_start, col_end + 1) 
                           if n not in called_numbers and n not in [grid[r][c] for r in range(5) for c in range(5)]]
                if available:
                    grid[row][col] = random.choice(available)
                else:
                    grid[row][col] = random.randint(col_start, col_end)
    
    return grid, pattern_name
