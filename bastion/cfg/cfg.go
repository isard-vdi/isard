package cfg

import (
	"fmt"

	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log  cfg.Log `mapstructure:"log"`
	DB   cfg.DB  `mapstructure:"db"`
	HTTP HTTP    `mapstructure:"http"`
	SSH  SSH     `mapstructure:"ssh"`
}

type HTTP struct {
	Host    string `mapstructure:"host"`
	Port    int    `mapstructure:"port"`
	BaseURL string `mapstructure:"base_url"`
}

func (h HTTP) Addr() string {
	return fmt.Sprintf("%s:%d", h.Host, h.Port)
}

type SSH struct {
	PrivateKeyPath string `mapstructure:"private_key_path"`
	PrivateKeySize int    `mapstructure:"private_key_size"`
	Host           string `mapstructure:"host"`
	Port           int    `mapstructure:"port"`
}

func (s *SSH) Addr() string {
	return fmt.Sprintf("%s:%d", s.Host, s.Port)
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("bastion", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetDBDefaults()
	cfg.SetHTTPDefaults()

	viper.BindEnv("http.base_url", "DOMAIN")
	viper.SetDefault("http.base_url", "")

	viper.SetDefault("ssh", map[string]interface{}{
		"private_key_path": "/opt/isard/bastion/ssh/id_rsa",
		"private_key_size": 4096,
		"host":             "",
		"port":             1315,
	})

}
