DOMAIN = "roblox_parental"

BASE_URL = "https://apis.roblox.com"
USERS_URL = "https://users.roblox.com"
GAMES_URL = "https://games.roblox.com"
PRESENCE_URL = "https://presence.roblox.com"
BILLING_URL = "https://billing.roblox.com"

URL_AUTHENTICATED = f"{USERS_URL}/v1/users/authenticated"
URL_CHILDREN_INFO = f"{BASE_URL}/parental-controls-api/v1/parental-controls/children-info"
URL_WEEKLY_SCREENTIME = f"{BASE_URL}/parental-controls-api/v1/parental-controls/get-weekly-screentime"
URL_TOP_UNIVERSES = f"{BASE_URL}/parental-controls-api/v1/parental-controls/get-top-weekly-screentime-by-universe"
URL_BLOCKED_EXPERIENCES = f"{BASE_URL}/experience-blocking-api/v1/get-blocked-experiences"
URL_CHILD_SETTINGS = f"{BASE_URL}/parental-controls-api/v1/parental-controls/child-settings"
URL_BILLING_SETTINGS = f"{BILLING_URL}/v1/parental-controls/get-settings"
URL_GAMES = f"{GAMES_URL}/v1/games"
URL_PRESENCE = f"{PRESENCE_URL}/v1/presence/users"

USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"

DEFAULT_SLOW_POLL_INTERVAL = 30
DEFAULT_FAST_POLL_INTERVAL = 2

CONF_COOKIE = "roblosecurity_cookie"
CONF_CHILD_IDS = "child_ids"
CONF_SLOW_INTERVAL = "slow_poll_interval"
CONF_FAST_INTERVAL = "fast_poll_interval"
CONF_PRESENCE_ENABLED = "presence_enabled"

COORDINATOR_SLOW = "slow"
COORDINATOR_FAST = "fast"
