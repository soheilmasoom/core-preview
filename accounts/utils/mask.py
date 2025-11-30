

def get_masked_phone(phone: str):
    a, b = 4, -3
    first = phone[:a]
    last = phone[b:]
    return first + '*' * len(phone[a: b]) + last
