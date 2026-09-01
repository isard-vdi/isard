package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/ioutil"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"

	"gitlab.com/isard/isardvdi/guac"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"

	"github.com/golang-jwt/jwt/v5"
	"github.com/sirupsen/logrus"
)

var (
	guacdAddr      string
	apiAddr        string
	apiIgnoreCerts bool
	jwtSecret      string
	apiCli         apiv4.Invoker
)

type LoginClaims struct {
	*jwt.RegisteredClaims
	KeyID     string          `json:"kid"`
	Type      string          `json:"type,omitempty"`
	SessionID string          `json:"session_id"`
	Data      LoginClaimsData `json:"data"`
}

type LoginClaimsData struct {
	Provider   string `json:"provider"`
	ID         string `json:"user_id"`
	RoleID     string `json:"role_id"`
	CategoryID string `json:"category_id"`
	GroupID    string `json:"group_id"`
	Name       string `json:"name"`
}

type ViewerClaims struct {
	*jwt.RegisteredClaims
	KeyID string           `json:"kid"`
	Type  string           `json:"type,omitempty"`
	Data  ViewerClaimsData `json:"data"`
}

type ViewerClaimsData struct {
	DesktopID  string `json:"desktop_id"`
	RoleID     string `json:"role_id,omitempty"`
	CategoryID string `json:"category_id,omitempty"`
}

func init() {
	guacdAddr = os.Getenv("GUACD_ADDR")
	if guacdAddr == "" {
		guacdAddr = "isard-vpn:4822"
	}

	apiAddr = os.Getenv("API_DOMAIN")
	if apiAddr == "" || apiAddr == "isard-apiv4" {
		apiAddr = "http://isard-apiv4:5000"
	} else {
		apiAddr = "https://" + apiAddr
		apiIgnoreCerts = true
	}

	jwtSecret = os.Getenv("API_ISARDVDI_SECRET")
	if jwtSecret == "" {
		logrus.Fatal("API_ISARDVDI_SECRET is required")
	}
}

func isAuthenticated(handler http.Handler) http.HandlerFunc {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		logrus.Debugf("authenticating request: %s %s", r.Method, r.URL.String())

		scheme := r.URL.Query().Get("scheme")
		if scheme != "rdp" {
			logrus.Errorf("rejected non-rdp scheme: %s", scheme)
			w.WriteHeader(http.StatusBadRequest)
			return
		}

		tkn := r.URL.Query().Get("session")
		hostname := r.URL.Query().Get("hostname")

		if tkn == "" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		iclaims, err := verifyToken(tkn)
		if err != nil {
			// Routine client-side event: viewer session tokens expire while a
			// tab is left open, so a rejected/expired token is expected and
			// must not pollute error dashboards. Warn keeps audit visibility.
			logrus.Warnf("rejected viewer token (expired or invalid): %v", err)
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		var subject string
		switch claims := iclaims.(type) {
		case *LoginClaims:
			subject = fmt.Sprintf("user %s (id: %s)", claims.Data.Name, claims.Data.ID)
		case *ViewerClaims:
			subject = "viewer for desktop " + claims.Data.DesktopID
		default:
			logrus.Error("unknown claims type or missing required fields")
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		logrus.Infof("%s is trying to access %s", subject, hostname)

		res, err := apiCli.UserOwnsDesktop(ogenclient.ContextWithAPIv4Token(r.Context(), tkn), &apiv4.UserOwnsDesktopRequest{
			IP: apiv4.NewOptNilString(hostname),
		})
		if err != nil {
			logrus.Errorf("error checking if %s owns desktop %s: %v", subject, hostname, err)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}

		if _, ok := res.(*apiv4.EmptyResponse); !ok {
			apiErr := ogenclient.AsAPIError(res)
			if errors.Is(apiErr, ogenclient.ErrUnauthorized) || errors.Is(apiErr, ogenclient.ErrForbidden) {
				logrus.Errorf("%s doesn't own desktop %s", subject, hostname)
				w.WriteHeader(http.StatusUnauthorized)
				return
			}

			logrus.Errorf("error checking if %s owns desktop %s: %v", subject, hostname, apiErr)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}

		logrus.Debugf("%s authorized to access %s", subject, hostname)
		handler.ServeHTTP(w, r)
	})
}

func verifyToken(tokenString string) (jwt.Claims, error) {
	keyFunc := func(tkn *jwt.Token) (interface{}, error) {
		if _, ok := tkn.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", tkn.Header["alg"])
		}
		return []byte(jwtSecret), nil
	}

	loginClaims := &LoginClaims{}
	tkn, err := jwt.ParseWithClaims(tokenString, loginClaims, keyFunc)
	if err == nil && tkn.Valid && loginClaims.SessionID != "" && loginClaims.Data.ID != "" {
		return loginClaims, nil
	}

	viewerClaims := &ViewerClaims{}
	tkn, err = jwt.ParseWithClaims(tokenString, viewerClaims, keyFunc)
	if err == nil && tkn.Valid && viewerClaims.Data.DesktopID != "" {
		return viewerClaims, nil
	}

	return nil, fmt.Errorf("token does not match known claim types or signature invalid")
}

func logLevel() {
	levelStr := os.Getenv("LOG_LEVEL")
	if levelStr == "" {
		levelStr = "info"
	}

	if level, err := logrus.ParseLevel(levelStr); err != nil {
		logrus.Fatalf("Invalid LOG_LEVEL envrionment variable: %s", levelStr)
	} else {
		logrus.SetLevel(level)
		logrus.Infof("Log level set to %s", levelStr)
	}
}

type ServiceLogrusHook struct{}

func (h *ServiceLogrusHook) Levels() []logrus.Level {
	return logrus.AllLevels
}

func (h *ServiceLogrusHook) Fire(entry *logrus.Entry) error {
	entry.Data["service"] = "guac"
	return nil
}

func logFormat() {
	logrus.SetFormatter(&logrus.JSONFormatter{})
	logrus.AddHook(&ServiceLogrusHook{})
}

func main() {
	logFormat()
	logLevel()

	opts := []ogenclient.Option{ogenclient.WithUserAgent("isardvdi-guac")}
	if apiIgnoreCerts {
		opts = append(opts, ogenclient.WithIgnoreCerts())
	}

	var err error
	apiCli, err = apiv4.NewClient(apiAddr, ogenclient.APIv4Context{}, apiv4.WithClient(ogenclient.NewHTTPClient(opts...)))
	if err != nil {
		logrus.Fatalf("create the API client: %v", err)
	}

	servlet := guac.NewServer(DemoDoConnect)
	wsServer := guac.NewWebsocketServer(DemoDoConnect)

	sessions := guac.NewMemorySessionStore()
	wsServer.OnConnect = sessions.Add
	wsServer.OnDisconnect = sessions.Delete

	mux := http.NewServeMux()
	mux.HandleFunc("/tunnel", isAuthenticated(servlet))
	mux.HandleFunc("/tunnel/", isAuthenticated(servlet))
	mux.HandleFunc("/websocket-tunnel", isAuthenticated(wsServer))
	mux.HandleFunc("/sessions/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		sessions.RLock()
		defer sessions.RUnlock()

		type ConnIds struct {
			Uuid string `json:"uuid"`
			Num  int    `json:"num"`
		}

		connIds := make([]*ConnIds, len(sessions.ConnIds))

		i := 0
		for id, num := range sessions.ConnIds {
			connIds[i] = &ConnIds{
				Uuid: id,
				Num:  num,
			}
		}

		if err := json.NewEncoder(w).Encode(connIds); err != nil {
			logrus.Error(err)
		}
	})

	logrus.Println("Serving on http://127.0.0.1:4567")

	s := &http.Server{
		Addr:           "0.0.0.0:4567",
		Handler:        mux,
		ReadTimeout:    guac.SocketTimeout,
		WriteTimeout:   guac.SocketTimeout,
		MaxHeaderBytes: 1 << 20,
	}
	if err := s.ListenAndServe(); err != nil {
		logrus.Fatalf("serve: %v", err)
	}
}

// DemoDoConnect creates the tunnel to the remote machine (via guacd)
func DemoDoConnect(request *http.Request) (guac.Tunnel, error) {
	config := guac.NewGuacamoleConfiguration()

	var query url.Values
	if request.URL.RawQuery == "connect" {
		// http tunnel uses the body to pass parameters
		data, err := ioutil.ReadAll(request.Body)
		if err != nil {
			logrus.Errorf("Failed to read body: %v", err)
			return nil, err
		}
		_ = request.Body.Close()
		queryString := string(data)
		query, err = url.ParseQuery(queryString)
		if err != nil {
			logrus.Errorf("Failed to parse body query: %v", err)
			return nil, err
		}
		logrus.Debugln("body:", queryString, query)
	} else {
		query = request.URL.Query()
	}

	config.Protocol = query.Get("scheme")
	config.Parameters = map[string]string{}
	dangerousParams := map[string]bool{
		"port":             true,
		"gateway-hostname": true,
		"gateway-port":     true,
		"gateway-username": true,
		"gateway-password": true,
		"gateway-domain":   true,
		"private-key":      true,
		"passphrase":       true,
	}
	for k, v := range query {
		if !dangerousParams[k] {
			config.Parameters[k] = v[0]
		}
	}

	// Set defaults for guacd connect args that must not be empty
	if config.Parameters["security"] == "" {
		config.Parameters["security"] = "any"
	}
	if config.Parameters["ignore-cert"] == "" {
		config.Parameters["ignore-cert"] = "true"
	}

	var err error
	if query.Get("width") != "" {
		config.OptimalScreenWidth, err = strconv.Atoi(query.Get("width"))
		if err != nil || config.OptimalScreenWidth == 0 {
			logrus.Error("Invalid width")
			config.OptimalScreenWidth = 1024
		}
	}
	if query.Get("height") != "" {
		config.OptimalScreenHeight, err = strconv.Atoi(query.Get("height"))
		if err != nil || config.OptimalScreenHeight == 0 {
			logrus.Error("Invalid height")
			config.OptimalScreenHeight = 768
		}
	}
	config.AudioMimetypes = []string{"audio/L16"}

	logrus.Debug("Connecting to guacd")
	addr, err := net.ResolveTCPAddr("tcp", guacdAddr)
	if err != nil {
		logrus.Errorf("resolve guacd address: %v", err)
		return nil, err
	}

	conn, err := net.DialTCP("tcp", nil, addr)
	if err != nil {
		logrus.Errorf("error while connecting to guacd: %v", err)
		return nil, err
	}

	stream := guac.NewStream(conn, guac.SocketTimeout)

	logrus.Debug("Connected to guacd")
	if request.URL.Query().Get("uuid") != "" {
		config.ConnectionID = request.URL.Query().Get("uuid")
	}
	logrus.Debugf("Starting handshake with %+v", config)
	err = stream.Handshake(config)
	if err != nil {
		return nil, err
	}
	logrus.Debug("Socket configured")
	return guac.NewSimpleTunnel(stream), nil
}
