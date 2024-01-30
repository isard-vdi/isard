package http

import (
	"encoding/json"
	"strings"
	"time"

	"github.com/ogen-go/ogen/middleware"
	"github.com/rs/zerolog"
)

func Logging(log *zerolog.Logger) middleware.Middleware {
	return func(req middleware.Request, next middleware.Next) (middleware.Response, error) {
		start := time.Now()

		rsp, err := next(req)
		// TODO: This needs to be removed
		// Don't log the heathcheck calls
		if req.OperationID == "Healthcheck" {
			return rsp, err
		}

		remoteAddr := req.Raw.RemoteAddr
		if addr := req.Raw.Header.Get("X-Forwarded-For"); addr != "" {
			remoteAddr = strings.TrimSpace(strings.Split(addr, ",")[0])
		}

		params := map[string]interface{}{}
		for k, v := range req.Params {
			pK := k.In.String()

			in, ok := params[pK]
			if !ok {
				in = map[string]interface{}{}
			}

			location := in.(map[string]interface{})
			location[k.Name] = v
			params[pK] = location
		}

		log := log.With().
			Str("operation_id", req.OperationID).
			Str("operation_name", req.OperationName).
			Str("path", req.Raw.URL.Path).
			Str("method", req.Raw.Method).
			Str("remote_addr", remoteAddr).
			Dur("duration", time.Since(start)).
			Any("params", asJSON([]string{}, params)).
			Any("body", asJSON([]string{"password"}, req.Body)).
			Logger()

		if err != nil {
			log.Error().Err(err).Msg("error handling request")
			return rsp, err
		}

		log.Debug().Any("response", asJSON([]string{}, rsp.Type)).Msg("response served")

		return rsp, err
	}
}

// TODO: This is really ugly, but it's the only way I can think of right now
func asJSON(exclKeys []string, m any) map[string]any {
	b, err := json.Marshal(m)
	if err != nil {
		return nil
	}

	vals := map[string]any{}
	if err := json.Unmarshal(b, &vals); err != nil {
		return nil
	}

	return excludeKeys(exclKeys, vals)
}

func excludeKeys(exclKeys []string, m map[string]any) map[string]any {
	result := map[string]any{}
mLoop:
	for k, v := range m {
		lower := strings.ToLower(k)
		for _, e := range exclKeys {
			if e == lower {
				result[lower] = "[[masked]]"
				continue mLoop
			}
		}

		// We haven't found any key to exclude

		// We've found a nested map!
		if m2, ok := v.(map[string]any); ok {
			result[lower] = excludeKeys(exclKeys, m2)
			continue
		}

		result[lower] = v
	}

	return result
}
