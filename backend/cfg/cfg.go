package cfg

import (
	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

// Cfg represents the configuration for the Backend microservice
type Cfg struct {
	// Log has the configuration related with logging
	Log cfg.Log
	// DB has the configuration used to connect to the DB
	DB cfg.DB
	// Redis has the configuration used to connect to Redis
	Redis cfg.Redis
	// GraphQL has the configuration used to listen to GraphQL connections
	GraphQL GraphQL
	// ClientsAddr has the configuration to connect to other microservices
	ClientsAddr ClientsAddr
}

// ClientsAddr has the configuration to connect to other microservices
type ClientsAddr struct {
	// Auth is the address (host:port) of the Auth microservice
	Auth string
	// Controller is the address (host:port) of the Controller microservice
	Controller string
	// DiskOperations is the address (host:port) of the DiskOperations microservice
	DiskOperations string
}

// GraphQL has the configuration used to listen to GraphQL connections
type GraphQL struct {
	// Host is the host that is going to be used to listen
	Host string
	// Port is the port that is going to be listen to
	Port int
}

// New loads the configuration for the microservice
func New() Cfg {
	config := &Cfg{}

	cfg.New("backend", setDefaults, config)

	return *config
}

// setDefaults sets the default values for the microservice
func setDefaults() {
	viper.SetDefault("graphql", map[string]interface{}{
		"host": "",
		"port": 1312,
	})

	viper.SetDefault("clientsaddr", map[string]string{
		"auth":           "auth:1312",
		"controller":     "controller:1312",
		"diskoperations": "diskoperations:1312",
	})

	cfg.SetDBDefaults()
	cfg.SetRedisDefaults()
}
