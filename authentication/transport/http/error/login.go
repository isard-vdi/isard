package error

import "net/http"

type LoginError string

const (
	LoginUnknown        LoginError = "unknown"
	LoginInternalServer LoginError = "internal_server"
	LoginUserDisabled   LoginError = "user_disabled"
	LoginUserDisallowed LoginError = "user_disallowed"
)

func LoginRedirect(w http.ResponseWriter, r *http.Request, code LoginError) {
	http.Redirect(w, r, "/login?error="+string(code), http.StatusFound)
}
