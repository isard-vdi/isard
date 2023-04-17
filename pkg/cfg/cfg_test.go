package cfg_test

import (
	"testing"
	"time"

	"github.com/spf13/viper"
	"github.com/stretchr/testify/assert"
	"gitlab.com/isard/isardvdi/pkg/cfg"
)

func TestTimeMapHook(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		In             string
		ExpectedResult map[time.Weekday]map[time.Time]int
		ExpectedErr    string
	}{
		"should parse the time map correctly": {
			In: `{"1": {"00:15": 1234, "13:12": 5678}}`,
			ExpectedResult: map[time.Weekday]map[time.Time]int{
				time.Monday: {
					time.Date(0, time.January, 1, 0, 15, 0, 0, time.UTC):  1234,
					time.Date(0, time.January, 1, 13, 12, 0, 0, time.UTC): 5678,
				},
			},
		},
		"should throw an error if the format is invalid": {
			In:          "THIS IS NOT AN HOUR!!!",
			ExpectedErr: "error decoding '': invalid time map: invalid character 'T' looking for beginning of value",
		},
		"should throw an error if the hour is invalid": {
			In:          `{"1": {"notanHour": 12}}`,
			ExpectedErr: `error decoding '': invalid time 'notanHour': parsing time "notanHour" as "15:04": cannot parse "notanHour" as "15"`,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			v := viper.New()
			v.Set("test", tc.In)

			var result map[time.Weekday]map[time.Time]int
			err := v.UnmarshalKey("test", &result, viper.DecodeHook(cfg.TimeMapHook()))

			if tc.ExpectedErr == "" {
				assert.NoError(err)
			} else {
				assert.EqualError(err, tc.ExpectedErr)
			}
			assert.Equal(tc.ExpectedResult, result)
		})
	}
}
