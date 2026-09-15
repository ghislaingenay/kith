from datetime import timedelta

ROLE_CACHE_TTL = timedelta(minutes=5)
ROLES_CACHE_KEY = "rbac:roles"
PERMISSIONS_CACHE_KEY = "rbac:permissions"
