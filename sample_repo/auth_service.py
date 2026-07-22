def process_user(user_id: int):
    # Bug: user object can be None if not found, causing crash
    user = get_user_from_db(user_id)
    return user.name

def get_user_from_db(user_id: int):
    # Dummy DB return
    return None
