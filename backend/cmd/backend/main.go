package main

import (
	"net/http"
	"os"
	"strconv"

	"github.com/isard-vdi/isard/backend/api"
	"github.com/isard-vdi/isard/backend/auth"
	"github.com/isard-vdi/isard/backend/cfg"
	"github.com/isard-vdi/isard/backend/env"
	"github.com/isard-vdi/isard/backend/isard"

	"github.com/spf13/afero"
	"go.uber.org/zap"
)

var (
	e *env.Env

	logger *zap.Logger
	sugar  *zap.SugaredLogger
)

func init() {
	logger, _ = zap.NewProduction()
	sugar = logger.Sugar()
	defer logger.Sync()

	var (
		redisPort,
		isardPort int

		err error
	)

	redisPortStr := os.Getenv("BACKEND_REDIS_PORT")
	if redisPortStr != "" {
		redisPort, err = strconv.Atoi(redisPortStr)
		if err != nil {
			sugar.Fatalw("invalid redis port",
				"err", err,
			)
		}

	} else {
		redisPort = 6379
	}

	isardPortStr := os.Getenv("BACKEND_ISARD_API_PORT")
	if isardPortStr != "" {
		isardPort, err = strconv.Atoi(isardPortStr)
		if err != nil {
			sugar.Fatalw("invalid isard port",
				"err", err,
			)
		}

	} else {
		isardPort = 7039
	}

	autoregistration, err := strconv.ParseBool(os.Getenv("BACKEND_AUTH_AUTOREGISTRATION"))
	if err != nil {
		sugar.Fatalw("invalid autoregistration value",
			"err", err,
		)
	}

	var frontendShowAdmin bool
	frontendShowAdminEnv := os.Getenv("FRONTEND_SHOW_ADMIN_BTN")
	if frontendShowAdminEnv != "" {
		frontendShowAdmin, err = strconv.ParseBool(frontendShowAdminEnv)
		if err != nil {
			sugar.Fatalw("invalid frontend show admin button value",
				"err", err,
			)
		}

	}

	e = &env.Env{
		Sugar: sugar,
		FS:    afero.NewOsFs(),
		Cfg: cfg.Cfg{
			BackendHost: os.Getenv("BACKEND_HOST"),
			Redis: cfg.Redis{
				Host:     os.Getenv("BACKEND_REDIS_HOST"),
				Port:     redisPort,
				Password: os.Getenv("BACKEND_REDIS_PASSWORD"),
			},
			Auth: cfg.Auth{
				AutoRegistration: autoregistration,
				GitHub: cfg.AuthGitHub{
					Host:   os.Getenv("BACKEND_AUTH_GITHUB_HOST"),
					ID:     os.Getenv("BACKEND_AUTH_GITHUB_ID"),
					Secret: os.Getenv("BACKEND_AUTH_GITHUB_SECRET"),
				},
				SAML: cfg.AuthSAML{
					CertPath:        os.Getenv("BACKEND_AUTH_SAML_CERT_PATH"),
					KeyPath:         os.Getenv("BACKEND_AUTH_SAML_KEY_PATH"),
					IdpMetadataURL:  os.Getenv("BACKEND_AUTH_SAML_IDP_URL"),
					IdpMetadataPath: os.Getenv("BACKEND_AUTH_SAML_IDP_METADATA_PATH"),
					Callback:        os.Getenv("BACKEND_AUTH_SAML_CALLBACK_URL"),
					AttrID:          os.Getenv("BACKEND_AUTH_SAML_ATTR_ID"),
					AttrName:        os.Getenv("BACKEND_AUTH_SAML_ATTR_NAME"),
				},
				Google: cfg.AuthGoogle{
					ID:     os.Getenv("BACKEND_AUTH_GOOGLE_ID"),
					Secret: os.Getenv("BACKEND_AUTH_GOOGLE_SECRET"),
				},
			},
			Isard: cfg.Isard{
				Host: os.Getenv("BACKEND_ISARD_API_HOST"),
				Port: isardPort,
			},
			Frontend: cfg.Frontend{
				ShowAdminButton: frontendShowAdmin,
			},
		},
		Auth: &env.Auth{},
	}

	auth.Init(e)
	e.Isard = isard.New(sugar, e.Cfg.Isard.Host, e.Cfg.Isard.Port)
}

func main() {
	defer logger.Sync()

	a := api.New(e)

	sugar.Info("listening to port :8080")
	if err := http.ListenAndServe(":8080", a.Mux); err != nil {
		sugar.Fatalw("listen http",
			"err", err,
			"addr", ":8080",
		)
	}
}
