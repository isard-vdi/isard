package cfg

import (
	"time"

	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log      cfg.Log
	Redis    cfg.Redis
	GRPC     cfg.GRPC
	Sessions Sessions
}

type Sessions struct {
	// MaxTime is the time when the session will expire and won't be able to be renewed
	MaxTime time.Duration `mapstructure:"max_time"`
	//  MaxRenewTime is the time when the session won't be able to be renewed
	MaxRenewTime time.Duration `mapstructure:"max_renew_time"`
	// ExpirationTime is the time when the session will expire if it's not renewed
	ExpirationTime time.Duration `mapstructure:"expiration_time"`
	// RemoteAddrControl is a flag to enable IP control
	RemoteAddrControl bool `mapstructure:"remote_addr_control"`
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("sessions", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetRedisDefaults()
	cfg.SetGRPCDefaults()

	viper.SetDefault("redis.db", 1)

	viper.SetDefault("sessions", map[string]any{
		"max_time":            "4h",
		"max_renew_time":      "4h",
		"expiration_time":     "4h",
		"remote_addr_control": false,
	})
}
