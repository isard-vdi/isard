package http

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"

	"gitlab.com/isard/isardvdi/authentication/authentication/provider"
)

type argsJSON struct {
	Provider   string `json:"provider,omitempty"`
	CategoryID string `json:"category_id,omitempty"`
}

// TODO: Parse args depending on the content type
func parseArgs(r *http.Request) (map[string]string, error) {
	args := map[string]string{}

	// Parse the token
	args[provider.TokenArgsKey] = strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")

	r.ParseMultipartForm(32 << 20)
	for k, v := range r.Form {
		if len(v) == 0 {
			continue
		}

		args[k] = v[0]
	}

	// Pass the body as argument too
	defer r.Body.Close()
	b, err := io.ReadAll(r.Body)
	if err != nil {
		return map[string]string{}, fmt.Errorf("read request body: %w", err)
	}

	argsJSON := &argsJSON{}
	json.Unmarshal(b, argsJSON)
	if argsJSON.Provider != "" {
		args[provider.ProviderArgsKey] = argsJSON.Provider
	}

	if argsJSON.CategoryID != "" {
		args[provider.CategoryIDArgsKey] = argsJSON.CategoryID
	}

	args[provider.RequestBodyArgsKey] = string(b)

	return args, nil
}

func requiredArgs(requiredArgs []string, args map[string]string) error {
	for _, a := range requiredArgs {
		if args[a] == "" {
			return fmt.Errorf("%s not sent", a)
		}
	}

	return nil
}
