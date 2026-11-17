def process_user(user_id: int):
    user = get_user_from_db(user_id)
    if user is None:
        return None
    return user.name

def get_user_from_db(user_id: int):
    # Dummy DB return
    return None
