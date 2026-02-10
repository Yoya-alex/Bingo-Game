import random


def generate_bingo_grid():
    """
    Generate a 5x5 Bingo grid with numbers 1-75
    B: 1-15, I: 16-30, N: 31-45, G: 46-60, O: 61-75
    Center cell is FREE (None)
    """
    grid = []
    
    # Define ranges for each column
    ranges = [
        (1, 15),    # B
        (16, 30),   # I
        (31, 45),   # N
        (46, 60),   # G
        (61, 75)    # O
    ]
    
    for row_idx in range(5):
        row = []
        for col_idx in range(5):
            # Center cell is FREE
            if row_idx == 2 and col_idx == 2:
                row.append(None)
            else:
                start, end = ranges[col_idx]
                # Generate unique number for this column
                num = random.randint(start, end)
                # Ensure no duplicates in column (simple approach)
                while num in [grid[r][col_idx] for r in range(len(grid)) if grid[r][col_idx] is not None]:
                    num = random.randint(start, end)
                row.append(num)
        grid.append(row)
    
    return grid


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
    available = [i for i in range(1, 76) if i not in called_numbers]
    if not available:
        return None
    return random.choice(available)
