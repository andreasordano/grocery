# =============================================================================
# STORES CONFIGURATION
# =============================================================================
# Centralized store definitions. To add a new store:
# 1. Create api/{store}_api.py with a search_{store}(query, page=0) function
# 2. Add entry to STORES_CONFIG below
# 3. Done! No need to update fetch.py, app.py, or service.py
# =============================================================================

# Available stores and their metadata
STORES_CONFIG = {
    "selver": {
        "name": "Selver",
        "module": "api.selver_api",
        "function": "search_selver",
        "pagination_param": "size",
    },
    "barbora": {
        "name": "Barbora",
        "module": "api.barbora_api",
        "function": "search_barbora",
        "pagination_param": "size",
    },
    "rimi": {
        "name": "Rimi",
        "module": "api.rimi_api",
        "function": "search_rimi",
        "pagination_param": "page",
    },
    "prisma": {
        "name": "Prisma",
        "module": "api.prisma_api",
        "function": "search_prisma",
        "pagination_param": "page",
    },
}

# Default stores to search (ordered list of store keys)
DEFAULT_STORES = ["selver", "barbora", "rimi", "prisma"]


def get_store_names():
    """Return list of available store names (keys)."""
    return list(STORES_CONFIG.keys())


def get_default_stores():
    """Return default stores list."""
    return DEFAULT_STORES


def get_fetcher(store_name):
    """Dynamically import and return the fetcher function for a store.
    
    Args:
        store_name: store key (e.g., 'selver')
    
    Returns:
        Fetcher function (e.g., search_selver)
    
    Raises:
        ValueError: if store_name not found
    """
    if store_name not in STORES_CONFIG:
        raise ValueError(f"Unknown store: {store_name}")
    
    config = STORES_CONFIG[store_name]
    module_name = config["module"]
    function_name = config["function"]
    
    # Dynamically import the module and get the function
    import importlib
    module = importlib.import_module(module_name)
    return getattr(module, function_name)


def get_pagination_param(store_name):
    """Get the pagination parameter name for a store.
    
    Different stores use different parameter names:
    - Rimi uses 'page' (0-indexed page number)
    - Others use 'size' (number of results to return)
    
    Args:
        store_name: store key (e.g., 'rimi')
    
    Returns:
        Parameter name string ('page' or 'size')
    
    Raises:
        ValueError: if store_name not found
    """
    if store_name not in STORES_CONFIG:
        raise ValueError(f"Unknown store: {store_name}")
    return STORES_CONFIG[store_name].get("pagination_param", "size")
