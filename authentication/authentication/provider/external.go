package provider

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/model"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

const ExternalString = "external"

type External struct {
	db r.QueryExecutor
}

func checkRequiredArgs(args map[string]string) error {
	var requiredArgs = []string{
		"category_id",
		"external_app_id",
		"external_group_id",
		"user_id",
		"username",
		"kid",
		"role",
		"name",
	}

request:
	for _, rA := range requiredArgs {
		for a := range args {
			if a == rA && a != "" {
				continue request
			}
		}

		return fmt.Errorf("missing required argument: '%s'", rA)
	}

	return nil
}

func (e *External) Login(ctx context.Context, categoryID string, args map[string]string) (*model.Group, *model.User, string, error) {
	if err := checkRequiredArgs(args); err != nil {
		return nil, nil, "", err
	}

	if model.Role(args["role"]).HasEqualOrMorePrivileges(model.RoleAdmin) {
		return nil, nil, "", errors.New("cannot create an admin user through an external app")
	}

	g := &model.Group{
		Category:      args["category_id"],
		ExternalAppID: args["external_app_id"],
		ExternalGID:   args["external_group_id"],
	}
	// We can safely set this parameters, since they're not going to be overrided if the group exists
	g.Description = "This is a auto register created by the authentication service. This group maps a group of an external app"
	g.GenerateNameExternal(e.String())

	u := &model.User{
		UID:      args["user_id"],
		Username: args["username"],
		Provider: fmt.Sprintf("%s_%s", e.String(), args["kid"]),

		Category: args["category_id"],
		Role:     model.Role(args["role"]),

		Name:  args["name"],
		Email: args["email"],
		Photo: args["photo"],
	}

	return g, u, "", nil
}

func (External) Callback(context.Context, *CallbackClaims, map[string]string) (*model.Group, *model.User, string, error) {
	return nil, nil, "", errInvalidIDP
}

func (External) AutoRegister() bool {
	return true
}

func (External) String() string {
	return ExternalString
}
