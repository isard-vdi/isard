// SPDX-License-Identifier: AGPL-3.0-or-later

package cfg

import (
	"testing"

	"github.com/spf13/viper"
	"github.com/stretchr/testify/assert"
)

// TestSetDefaultsAppliesRdpgwSpecificKeys pins the two rdpgw-only
// defaults (api_addr + idle_timeout). The rest of the HTTP/log
// defaults come from pkg/cfg and are tested there.
func TestSetDefaultsAppliesRdpgwSpecificKeys(t *testing.T) {
	viper.Reset()
	defer viper.Reset()

	setDefaults()

	assert.Equal(t, "isard-apiv4:5000", viper.GetString("api_addr"),
		"api_addr default must point at the apiv4 service name")
	assert.Equal(t, "30m", viper.GetString("idle_timeout"),
		"idle_timeout default must be 30 minutes")
}
