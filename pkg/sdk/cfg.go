package sdk

type Cfg struct {
	Token       string
	Host        string
	IgnoreCerts bool `mapstructure:"ignore_certs"`
}
