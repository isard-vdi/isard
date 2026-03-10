package authentication

import "net/url"

// ValidateRedirect ensures redirect is a safe relative path.
// Returns "/" as fallback if the redirect is invalid or malicious,
// so the login flow still completes with a redirect to the homepage.
func ValidateRedirect(redirect string) string {
	if redirect == "" {
		return ""
	}
	u, err := url.Parse(redirect)
	if err != nil || u.Host != "" || u.Scheme != "" {
		return "/"
	}
	return u.String()
}
