package log_test

// import (
// 	"testing"

// 	"github.com/rs/zerolog"
// 	"github.com/stretchr/testify/assert"
// 	"gitlab.com/isard/isardvdi/common/pkg/log"
// )

// func TestNew(t *testing.T) {
// 	assert := assert.New(t)

// 	cases := map[string]struct {
// 		Level         string
// 		ExpectedLevel zerolog.Level
// 	}{
// 		"should set the log level at panic": {
// 			Level:         "panic",
// 			ExpectedLevel: zerolog.PanicLevel,
// 		},
// 		"should set the log level at fatal": {
// 			Level:         "fatal",
// 			ExpectedLevel: zerolog.FatalLevel,
// 		},
// 		"should set the log level at error": {
// 			Level:         "error",
// 			ExpectedLevel: zerolog.ErrorLevel,
// 		},
// 		"should set the log level at warning": {
// 			Level:         "warn",
// 			ExpectedLevel: zerolog.WarnLevel,
// 		},
// 		"should set the log level at info": {
// 			Level:         "info",
// 			ExpectedLevel: zerolog.InfoLevel,
// 		},
// 		"should set the log level at debug": {
// 			Level:         "debug",
// 			ExpectedLevel: zerolog.DebugLevel,
// 		},
// 		"should set the log level at trace": {
// 			Level:         "trace",
// 			ExpectedLevel: zerolog.TraceLevel,
// 		},
// 		"should set the log level at info if the level is unknown": {
// 			Level:         "iufhewiuhfwiuefh",
// 			ExpectedLevel: zerolog.InfoLevel,
// 		},
// 	}

// 	for name, tc := range cases {
// 		t.Run(name, func(t *testing.T) {
// 			logger := log.New("service", tc.Level)

// 			assert.Equal(tc.ExpectedLevel, logger.GetLevel())
// 		})
// 	}
// }
