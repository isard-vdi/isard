package log

import (
	"os"
	"strings"

	"github.com/rs/zerolog"
)

func New(svc, lvl string) *zerolog.Logger {
	lvl = strings.ToLower(lvl)
	logger := zerolog.New(os.Stderr).With().Timestamp().Str("service", svc).Logger()

	switch lvl {
	case "panic":
		logger = logger.Level(zerolog.PanicLevel)

	case "fatal":
		logger = logger.Level(zerolog.FatalLevel)

	case "error":
		logger = logger.Level(zerolog.ErrorLevel)

	case "warn":
		logger = logger.Level(zerolog.WarnLevel)

	case "info":
		logger = logger.Level(zerolog.InfoLevel)

	case "debug":
		logger = logger.Level(zerolog.DebugLevel)

	case "trace":
		logger = logger.Level(zerolog.TraceLevel)

	default:
		logger = logger.Level(zerolog.InfoLevel)
		logger.Warn().Msgf("unknown '%s' log level, fallback to info", lvl)
	}

	return &logger
}
