package model

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestGenerateNameExternal(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	g := &Group{ExternalGID: "/students/GROUP1"}
	g.GenerateNameExternal("ACME")

	assert.Equal("[ACME] /students/GROUP1", g.Name)
}
