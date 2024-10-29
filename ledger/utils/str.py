def truncate_str(s, length):
    """
    Truncate a string to a specified length and add ellipsis if needed.

    Args:
    s (str): The string to truncate.
    length (int): The maximum length of the truncated string including ellipsis.

    Returns:
    str: The truncated string with ellipsis if it exceeds the specified length.
    """
    if len(s) > length:
        return s[:length - 3] + '...'
    return s
