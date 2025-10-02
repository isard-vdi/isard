module gitlab.com/isard/isardvdi/pkg/haproxy-bastion-sync

go 1.23

replace (
	gitlab.com/isard/isardvdi => ../..
	gitlab.com/isard/isardvdi/pkg/sdk => ../sdk
)

require (
	github.com/rs/zerolog v1.34.0
	github.com/spf13/viper v1.20.1
	gitlab.com/isard/isardvdi v0.0.0
	google.golang.org/grpc v1.72.2
)
