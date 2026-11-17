def process_user(user_id: int):
    user = get_user_from_db(user_id)
    return user.name

def get_user_from_db(user_id: int):
    return None
