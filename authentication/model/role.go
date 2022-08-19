package model

type Role string

const (
	RoleAdmin    Role = "admin"
	RoleManager  Role = "manager"
	RoleAdvanced Role = "advanced"
	RoleUser     Role = "user"
)

var rolePrivileges = map[Role]int{
	RoleAdmin:    4,
	RoleManager:  3,
	RoleAdvanced: 2,
	RoleUser:     1,
}

func (r Role) HasMorePrivileges(r2 Role) bool {
	return rolePrivileges[r] > rolePrivileges[r2]
}

func (r Role) HasEqualOrMorePrivileges(r2 Role) bool {
	if r == r2 {
		return true
	}

	return r.HasMorePrivileges(r2)
}
