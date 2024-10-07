package types

import "gitlab.com/isard/isardvdi/authentication/model"

const (
	ProviderUnknown  = "unknown"
	ProviderLocal    = "local"
	ProviderLDAP     = "ldap"
	ProviderForm     = "form"
	ProviderExternal = "external"
	ProviderSAML     = "saml"
	ProviderGoogle   = "google"
)

type ProviderUserData struct {
	Provider string `json:"provider"`
	Category string `json:"category"`
	UID      string `json:"uid"`

	Role     *model.Role `json:"role,omitempty"`
	Group    *string     `json:"group"`
	Username *string     `json:"username,omitempty"`
	Name     *string     `json:"name,omitempty"`
	Email    *string     `json:"email,omitempty"`
	Photo    *string     `json:"photo,omitempty"`
}

func (p ProviderUserData) ToUser() *model.User {
	u := &model.User{
		Provider: p.Provider,
		Category: p.Category,
		UID:      p.UID,
	}

	if p.Role != nil {
		u.Role = *p.Role
	}

	if p.Group != nil {
		u.Group = *p.Group
	}

	if p.Username != nil {
		u.Username = *p.Username
	}

	if p.Name != nil {
		u.Name = *p.Name
	}

	if p.Email != nil {
		u.Email = *p.Email
	}

	if p.Photo != nil {
		u.Photo = *p.Photo
	}

	return u
}

func (p *ProviderUserData) FromUser(u *model.User) {
	if u.Provider != "" {
		p.Provider = u.Provider
	}

	if u.Category != "" {
		p.Category = u.Category
	}

	if u.UID != "" {
		p.UID = u.UID
	}

	if u.Role != "" {
		p.Role = &u.Role
	}

	if u.Group != "" {
		p.Group = &u.Group
	}

	if u.Username != "" {
		p.Username = &u.Username
	}

	if u.Name != "" {
		p.Name = &u.Name
	}

	if u.Email != "" {
		p.Email = &u.Email
	}

	if u.Photo != "" {
		p.Photo = &u.Photo
	}
}
