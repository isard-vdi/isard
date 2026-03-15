package db_test

import (
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/stretchr/testify/assert"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type testCommaSplitDoc struct {
	ID   string              `rethinkdb:"id"`
	Tags db.CommaSplitString `rethinkdb:"tags"`
}

func TestCommaSplitStringMarshalRQL(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB func(*r.Mock)
		Doc       testCommaSplitDoc
	}{
		"should marshal multiple values as a comma-separated string": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Insert(map[string]any{
					"id":   "1",
					"tags": "a,b,c",
				})).Return(r.WriteResponse{Inserted: 1}, nil)
			},
			Doc: testCommaSplitDoc{ID: "1", Tags: db.CommaSplitString{"a", "b", "c"}},
		},
		"should marshal a single value": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Insert(map[string]any{
					"id":   "2",
					"tags": "a",
				})).Return(r.WriteResponse{Inserted: 1}, nil)
			},
			Doc: testCommaSplitDoc{ID: "2", Tags: db.CommaSplitString{"a"}},
		},
		"should marshal an empty slice as an empty string": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Insert(map[string]any{
					"id":   "3",
					"tags": "",
				})).Return(r.WriteResponse{Inserted: 1}, nil)
			},
			Doc: testCommaSplitDoc{ID: "3", Tags: db.CommaSplitString{}},
		},
		"should marshal nil as an empty string": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Insert(map[string]any{
					"id":   "4",
					"tags": "",
				})).Return(r.WriteResponse{Inserted: 1}, nil)
			},
			Doc: testCommaSplitDoc{ID: "4", Tags: nil},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			mock := r.NewMock()
			tc.PrepareDB(mock)

			_, err := r.Table("test").Insert(tc.Doc).Run(mock)

			assert.NoError(err)
			mock.AssertExpectations(t)
		})
	}
}

func TestCommaSplitStringUnmarshalRQL(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB    func(*r.Mock)
		ExpectedTags db.CommaSplitString
		ExpectedErr  string
	}{
		"should unmarshal a comma-separated string into multiple values": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Get("1")).Return([]any{
					map[string]any{
						"id":   "1",
						"tags": "a,b,c",
					},
				}, nil)
			},
			ExpectedTags: db.CommaSplitString{"a", "b", "c"},
		},
		"should unmarshal a single value": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Get("1")).Return([]any{
					map[string]any{
						"id":   "1",
						"tags": "a",
					},
				}, nil)
			},
			ExpectedTags: db.CommaSplitString{"a"},
		},
		"should unmarshal an empty string as nil": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Get("1")).Return([]any{
					map[string]any{
						"id":   "1",
						"tags": "",
					},
				}, nil)
			},
			ExpectedTags: nil,
		},
		"should return an error for an unsupported type": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Get("1")).Return([]any{
					map[string]any{
						"id":   "1",
						"tags": 123,
					},
				}, nil)
			},
			ExpectedErr: "unsupported type",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			mock := r.NewMock()
			tc.PrepareDB(mock)

			res, err := r.Table("test").Get("1").Run(mock)
			assert.NoError(err)
			defer res.Close()

			var doc testCommaSplitDoc
			err = res.One(&doc)

			if tc.ExpectedErr == "" {
				assert.NoError(err)
				assert.Equal(tc.ExpectedTags, doc.Tags)
			} else {
				assert.ErrorContains(err, tc.ExpectedErr)
			}

			mock.AssertExpectations(t)
		})
	}
}

type testDurationDoc struct {
	ID  string      `rethinkdb:"id"`
	TTL db.Duration `rethinkdb:"ttl"`
}

func TestDurationMarshalRQL(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB func(*r.Mock)
		Doc       testDurationDoc
	}{
		"should marshal 5 minutes correctly": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Insert(map[string]any{
					"id":  "1",
					"ttl": "5m0s",
				})).Return(r.WriteResponse{Inserted: 1}, nil)
			},
			Doc: testDurationDoc{ID: "1", TTL: db.Duration(5 * time.Minute)},
		},
		"should marshal 1 hour 30 minutes correctly": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Insert(map[string]any{
					"id":  "2",
					"ttl": "1h30m0s",
				})).Return(r.WriteResponse{Inserted: 1}, nil)
			},
			Doc: testDurationDoc{ID: "2", TTL: db.Duration(90 * time.Minute)},
		},
		"should marshal zero duration as 0s": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Insert(map[string]any{
					"id":  "3",
					"ttl": "0s",
				})).Return(r.WriteResponse{Inserted: 1}, nil)
			},
			Doc: testDurationDoc{ID: "3", TTL: db.Duration(0)},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			mock := r.NewMock()
			tc.PrepareDB(mock)

			_, err := r.Table("test").Insert(tc.Doc).Run(mock)

			assert.NoError(err)
			mock.AssertExpectations(t)
		})
	}
}

func TestDurationUnmarshalRQL(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB   func(*r.Mock)
		ExpectedTTL db.Duration
		ExpectedErr string
	}{
		"should unmarshal a valid duration string": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Get("1")).Return([]any{
					map[string]any{
						"id":  "1",
						"ttl": "5m0s",
					},
				}, nil)
			},
			ExpectedTTL: db.Duration(5 * time.Minute),
		},
		"should unmarshal a duration with hours": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Get("1")).Return([]any{
					map[string]any{
						"id":  "1",
						"ttl": "1h30m0s",
					},
				}, nil)
			},
			ExpectedTTL: db.Duration(90 * time.Minute),
		},
		"should return an error for an invalid duration string": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Get("1")).Return([]any{
					map[string]any{
						"id":  "1",
						"ttl": "not-a-duration",
					},
				}, nil)
			},
			ExpectedErr: "could not decode",
		},
		"should return an error for an unsupported type": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("test").Get("1")).Return([]any{
					map[string]any{
						"id":  "1",
						"ttl": 123,
					},
				}, nil)
			},
			ExpectedErr: "unsupported type",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			mock := r.NewMock()
			tc.PrepareDB(mock)

			res, err := r.Table("test").Get("1").Run(mock)
			assert.NoError(err)
			defer res.Close()

			var doc testDurationDoc
			err = res.One(&doc)

			if tc.ExpectedErr == "" {
				assert.NoError(err)
				assert.Equal(tc.ExpectedTTL, doc.TTL)
			} else {
				assert.ErrorContains(err, tc.ExpectedErr)
			}

			mock.AssertExpectations(t)
		})
	}
}
