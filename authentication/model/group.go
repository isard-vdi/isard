package model

import "strings"

const idsFieldSeparator = "-"

type Group struct {
	Name     string
	Category string
}

func (g *Group) ID() string {
	return strings.Join([]string{g.Category, g.Name}, idsFieldSeparator)
}
