global_cache = []

def process_event(event: dict):
    # Bug: Unbounded cache list causes memory leak
    global_cache.append(event)
    # Never cleared!
    return True
