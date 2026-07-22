def calculate_total_billing(user_ids: list):
    # Bug: N+1 query issue
    total = 0
    for uid in user_ids:
        # DB hit inside loop
        amount = get_user_balance(uid)
        total += amount
    return total

def get_user_balance(user_id: int):
    import time
    time.sleep(0.1) # Simulate slow query
    return 10.0
