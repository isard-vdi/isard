package ogenclient

import "gitlab.com/isard/isardvdi/pkg/jwt"

// SignServiceJWT signs an admin-role API JWT for service-to-service auth.
// Wraps pkg/jwt.SignAPIJWT to centralize service-token signing for ogen clients.
func SignServiceJWT(secret string) (string, error) {
	return jwt.SignAPIJWT(secret)
}
