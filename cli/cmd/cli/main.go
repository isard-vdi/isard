package main

import (
	"fmt"
	"os/exec"

	"github.com/rs/xid"
	"gitlab.com/isard/isardvdi/common/pkg/db"
	"gitlab.com/isard/isardvdi/common/pkg/model"
	"golang.org/x/crypto/bcrypt"
)

func main() {
	if _, err := exec.Command("dropdb", "isard", "-h", "/var/run/postgresql").CombinedOutput(); err != nil {
		panic(err)
	}

	if _, err := exec.Command("createdb", "isard", "-h", "/var/run/postgresql").CombinedOutput(); err != nil {
		panic(err)
	}

	db, err := db.New("localhost:5432", "dev", "dev", "isard")
	if err != nil {
		panic(err)
	}

	e := &model.Entity{
		UUID: xid.New().String(),

		Name:        "Entitat",
		Description: "Això és una entitat",
	}

	result, err := db.Model(e).Returning("id").Insert()
	if err != nil {
		panic(err)
	}

	fmt.Println("Entitat insertada")
	fmt.Println(result.RowsAffected())

	g := &model.Group{
		UUID: xid.New().String(),

		EntityID: e.ID,

		Name:        "Grup",
		Description: "Això és un grup",
	}

	result, err = db.Model(g).Returning("id").Insert()
	if err != nil {
		panic(err)
	}

	fmt.Println("Grup insertada")
	fmt.Println(result.RowsAffected())

	pwd, err := bcrypt.GenerateFromPassword([]byte("password"), 1)
	if err != nil {
		panic(err)
	}

	a := &model.AuthConfig{
		UUID: xid.New().String(),

		EntityID: e.ID,
		Type:     "local",

		Name:        "Auth Config",
		Description: "Això és una AuthConfig",
	}
	result, err = db.Model(a).Returning("id").Insert()
	if err != nil {
		panic(err)
	}

	u := &model.User{
		UUID: xid.New().String(),

		EntityID:     e.ID,
		GroupID:      g.ID,
		AuthConfigID: a.ID,

		Username: "nefix",
		Password: string(pwd),

		Name:    "Néfix",
		Surname: "Estrada",
	}

	result, err = db.Model(u).Returning("id").Insert()
	if err != nil {
		panic(err)
	}

	fmt.Println("Usuari insertada")
	fmt.Println(result.RowsAffected())

}
