package ogenclient_test

import (
	"errors"
	"testing"

	"gitlab.com/isard/isardvdi/pkg/ogenclient"
)

// fakeBadRequest mimics ogen ErrorResponse layout. Suffix "BadRequest"
// triggers status 400 inference in AsAPIError.
type fakeBadRequest struct {
	Error           string
	Description     string
	DescriptionCode string
	Params          map[string][]byte
}

// fakeAdminFooNotFound is an alias-like type with the same layout.
type fakeAdminFooNotFound fakeBadRequest

type fakeUnauthorizedError struct {
	Detail string
}

func TestAsAPIError_AliasNotFound(t *testing.T) {
	t.Parallel()
	v := &fakeAdminFooNotFound{Error: "not_found", Description: "missing", DescriptionCode: "desktop_missing"}
	err := ogenclient.AsAPIError(v)
	if !errors.Is(err, ogenclient.ErrNotFound) {
		t.Fatalf("expected ErrNotFound, got %v", err)
	}
	apiErr := err.(ogenclient.APIError)
	if apiErr.Code != "not_found" || apiErr.Description != "missing" || apiErr.DescriptionCode != "desktop_missing" {
		t.Fatalf("unexpected fields: %+v", apiErr)
	}
}

func TestAsAPIError_Unauthorized(t *testing.T) {
	t.Parallel()
	v := &fakeUnauthorizedError{Detail: "no token"}
	err := ogenclient.AsAPIError(v)
	if !errors.Is(err, ogenclient.ErrUnauthorized) {
		t.Fatalf("expected ErrUnauthorized, got %v", err)
	}
}

func TestAsAPIError_NilReturnsError(t *testing.T) {
	t.Parallel()
	if err := ogenclient.AsAPIError(nil); err == nil {
		t.Fatal("expected error for nil")
	}
}

func TestAsAPIError_ParamsRawJSON(t *testing.T) {
	t.Parallel()
	v := &fakeBadRequest{
		Error:  "bad",
		Params: map[string][]byte{"count": []byte("3"), "raw": []byte("not-json")},
	}
	err := ogenclient.AsAPIError(v)
	if !errors.Is(err, ogenclient.ErrBadRequest) {
		t.Fatalf("expected ErrBadRequest, got %v", err)
	}
	apiErr := err.(ogenclient.APIError)
	if apiErr.Params["count"].(float64) != 3 {
		t.Fatalf("expected count=3, got %+v", apiErr.Params["count"])
	}
	if apiErr.Params["raw"].(string) != "not-json" {
		t.Fatalf("expected raw fallback string, got %+v", apiErr.Params["raw"])
	}
}
