"""Rate-limit budgets for the tenants domain's routes."""

READ_RATE_LIMIT_PER_MINUTE = 60
READ_RATE_LIMIT_PER_HOUR = 1000

# Tighter than the read budget: logo upload does storage I/O per request.
LOGO_UPLOAD_RATE_LIMIT_PER_MINUTE = 10
LOGO_UPLOAD_RATE_LIMIT_PER_HOUR = 100
