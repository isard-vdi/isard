package guac

type Config struct {
	ConnectionID string
	Protocol     string
	Parameters   map[string]string
}

func NewGuacamoleConfiguration() *Config {
	return &Config{
		Parameters: make(map[string]string),
	}
}
