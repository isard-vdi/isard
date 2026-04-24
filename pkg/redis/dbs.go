package redis

// DB assignments for the shared isard-redis instance. Hardcoded per
// functional area so services sharing a namespace (RQ queues, change feed
// bus, socket.io fan-out) cooperate, while unrelated services stay isolated.
// Must stay in sync with component/_common/isardvdi_common/connections/redis_urls.py.
const (
	DBRQ         = 0
	DBSessions   = 1
	DBChangeFeed = 2
	DBSocketIO   = 3
)
