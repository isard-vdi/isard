module gitlab.com/isard/isardvdi

go 1.16

require (
	github.com/bolkedebruin/rdpgw v1.0.4
	github.com/crewjam/saml v0.4.6
	github.com/go-ldap/ldap/v3 v3.4.1
	github.com/golang-jwt/jwt v3.2.2+incompatible
	// https://github.com/grafana/loki/issues/2826. This is the equivalent of 2.4.2
	github.com/grafana/loki v0.0.0-20220112164614-525040a32657
	github.com/oracle/oci-go-sdk/v65 v65.6.0
	github.com/patrickmn/go-cache v2.1.0+incompatible
	github.com/prometheus/client_golang v1.12.1
	github.com/prometheus/common v0.32.1
	github.com/rs/zerolog v1.23.0
	github.com/shirou/gopsutil/v3 v3.22.3
	github.com/spf13/viper v1.8.1
	github.com/stretchr/testify v1.7.1
	gitlab.com/isard/isardvdi-cli v0.20.0
	golang.org/x/crypto v0.0.0-20220427172511-eb4f295cb31f
	golang.org/x/oauth2 v0.0.0-20211104180415-d3ed0bb246c8
	google.golang.org/grpc v1.40.0
	google.golang.org/protobuf v1.27.1
	gopkg.in/rethinkdb/rethinkdb-go.v6 v6.2.1
	libvirt.org/go/libvirt v1.8002.0
	libvirt.org/go/libvirtxml v1.8006.0
)

// https://github.com/grafana/loki/issues/2826
replace github.com/hashicorp/consul => github.com/hashicorp/consul v1.5.1

// https://github.com/grafana/loki/issues/2826
replace k8s.io/client-go => k8s.io/client-go v0.21.0
