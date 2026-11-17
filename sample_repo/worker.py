MAX_CACHE_SIZE = 1000
global_cache = []

def process_event(event: dict):
    global_cache.append(event)
    if len(global_cache) > MAX_CACHE_SIZE:
        del global_cache[:-MAX_CACHE_SIZE]
    return True
