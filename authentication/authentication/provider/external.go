package provider

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/model"
)

const ExternalString = "external"

type External struct{}

func checkRequiredArgs(args map[string]string) error {
	var requiredArgs = []string{"user_id", "username", "kid", "category_id", "role", "group_id", "name"}

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

func (e *External) Login(ctx context.Context, categoryID string, args map[string]string) (*model.User, string, error) {
	if err := checkRequiredArgs(args); err != nil {
		return nil, "", err
	}

	if model.Role(args["role"]).HasEqualOrMorePrivileges(model.RoleAdmin) {
		return nil, "", errors.New("cannot create an admin user through an external app")
	}

	u := &model.User{
		UID:      args["user_id"],
		Username: args["username"],
		Provider: fmt.Sprintf("%s_%s", ExternalString, args["kid"]),

		Category: args["category_id"],
		Role:     model.Role(args["role"]),
		Group:    args["group_id"],

		Name:  args["name"],
		Email: args["email"],
		Photo: args["photo"],
	}

	return u, "", nil
}

func (External) Callback(context.Context, *CallbackClaims, map[string]string) (*model.User, string, error) {
	return nil, "", errInvalidIDP
}

func (External) AutoRegister() bool {
	return true
}

func (External) String() string {
	return ExternalString
}
