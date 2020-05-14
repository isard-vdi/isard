package cfg

// Cfg holds all the configuration for the hyper
type Cfg struct {
	GRPC GRPC
}

// GRPC holds the configuration for the GRPC server
type GRPC struct {
	Port int
}
