package cfg

type Cfg struct {
	Redis Redis
}

type Redis struct {
	Host string
	Port int
}
