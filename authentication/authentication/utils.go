package authentication

import (
	"strings"

	"gitlab.com/isard/isardvdi/authentication/model"
)

// normalizeIdentity ensures the identities have valid UTF-8 characters in all the names and descriptions
func normalizeIdentity(g *model.Group, u *model.User) {
	// Normalize group
	if g != nil {
		g.Name = normalizeString(g.Name)
		g.Description = normalizeString(g.Description)
	}

	// Normalize user
	if u != nil {
		u.Name = normalizeString(u.Name)
	}
}

// normalizeString removes all non-UTF-8 characters from a string
func normalizeString(s string) string {
	return strings.ToValidUTF8(s, "")
}
