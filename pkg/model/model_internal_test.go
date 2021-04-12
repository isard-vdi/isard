package model

// import (
// 	"context"
// 	"testing"

// 	"github.com/DATA-DOG/go-sqlmock"
// 	"github.com/go-pg/pg/v10"
// 	"github.com/stretchr/testify/assert"
// 	"github.com/stretchr/testify/require"
// )

// func TestLoadWithUUID(t *testing.T) {
// 	require := require.New(t)
// 	assert := assert.New(t)

// 	cases := map[string]struct {
// 		PrepareTest func(mock sqlmock.Sqlmock)
// 	}{}

// 	for name, tc := range cases {
// 		t.Run(name, func(t *testing.T) {
// 			db, mock, err := sqlmock.New()
// 			require.NoError(err)
// 			defer db.Close()

// 			ctx := context.Background()

// 			tc.PrepareTest(mock)

// 			disk := &Disk{}
// 			err = loadWithUUID(ctx, pg.DB, disk, "test")
// 		})
// 	}
// }
