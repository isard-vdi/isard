package model

import "strings"

const userIDFieldSeparator = "-"

type User struct {
	UID      string
	Username string
	Provider string

	Category string
	// TODO: Permissions
	// Role     string
	// Group    string

	// Templates []Template

	Name  string
	Email string
	Photo string
}

func (u *User) ID() string {
	return strings.Join([]string{u.Provider, u.Category, u.UID, u.Username}, userIDFieldSeparator)
}

func (u *User) FromID(id string) {
	parts := strings.Split(id, userIDFieldSeparator)

	// TODO: Check parts length

	u.Provider = parts[0]
	u.Category = parts[1]
	u.UID = parts[2]
	u.Username = strings.Join(parts[3:], userIDFieldSeparator)
}
