package cfg

import (
	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/pkg/cfg"
)

// Cfg represents the configuration for the DesktopBuilder microservice
type Cfg struct {
	// Log has the configuration related with logging
	Log cfg.Log
	// DB has the configuration used to connect to the DB
	DB cfg.DB
	// GraphQL has the configuration used to listen to gRPC connections
	GRPC cfg.GRPC
	// Storage has the configuration for the storage
	Storage Storage
}

// Storage has the configuration for the storage
type Storage struct {
	// BasePath is the path where the microservice is going to start to use (e.g.) /opt/isard
	BasePath string
}

// New loads the configuration for the microservice
func New() Cfg {
	config := &Cfg{}

	cfg.New("desktopbuilder", setDefaults, config)

	return *config
}

// setDefaults sets the default values for the microservice
func setDefaults() {
	viper.SetDefault("storage", map[string]string{
		"basePath": "/opt/isard/disks",
	})

	cfg.SetDBDefaults()
	cfg.SetGRPCDefaults()
}
