package ogenclient

import (
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"strings"
)

// APIError is a typed error mapped from an ogen API response.
type APIError struct {
	StatusCode      int
	Code            string
	Description     string
	DescriptionCode string
	Params          map[string]any
}

func (e APIError) Error() string {
	return fmt.Sprintf("ogen %d %s: %s [%s]", e.StatusCode, e.Code, e.Description, e.DescriptionCode)
}

// Is implements errors.Is matching with wildcard semantics.
func (e APIError) Is(target error) bool {
	t, ok := target.(APIError)
	if !ok {
		return false
	}
	if e.StatusCode != t.StatusCode {
		return false
	}
	return t.Code == "" || e.Code == t.Code
}

// Sentinels for HTTP status matching. All have empty Code so they wildcard-match.
var (
	ErrBadRequest           = APIError{StatusCode: 400}
	ErrUnauthorized         = APIError{StatusCode: 401}
	ErrForbidden            = APIError{StatusCode: 403}
	ErrNotFound             = APIError{StatusCode: 404}
	ErrConflict             = APIError{StatusCode: 409}
	ErrPreconditionRequired = APIError{StatusCode: 428}
	ErrInternalServer       = APIError{StatusCode: 500}
	ErrMaintenance          = APIError{StatusCode: 503}
	ErrGatewayTimeout       = APIError{StatusCode: 504}
	ErrInsufficientStorage  = APIError{StatusCode: 507}
)

// AsAPIError converts any non-success ogen response value into an APIError.
//
// It handles:
//   - Pointer-to-struct types whose underlying layout matches the ogen
//     ErrorResponse shape (Error / Msg / Description / DescriptionCode / Params
//     fields). This covers all per-operation alias types like
//     `type AdminFooNotFound ErrorResponse`.
//   - UnauthorizedError-like structs (single Detail field).
//   - HTTPValidationError-like structs (Detail slice/struct).
//
// Status code is inferred from the type name suffix (NotFound→404, etc.).
func AsAPIError(res any) error {
	return asAPIErrorWithStatus(res, 0)
}

func asAPIErrorWithStatus(res any, statusHint int) error {
	if res == nil {
		return errors.New("ogenclient: nil response")
	}

	rv := reflect.ValueOf(res)
	if rv.Kind() != reflect.Pointer || rv.IsNil() {
		return fmt.Errorf("ogenclient: unsupported response %T", res)
	}
	elem := rv.Elem()
	if elem.Kind() != reflect.Struct {
		return fmt.Errorf("ogenclient: unsupported response %T", res)
	}

	typeName := elem.Type().Name()
	status := statusFromTypeName(typeName)
	if status == 0 {
		status = statusHint
	}

	if elem.NumField() == 1 {
		if f := elem.FieldByName("Detail"); f.IsValid() && f.Kind() == reflect.String {
			return APIError{
				StatusCode:  effective(status, 401),
				Code:        defaultCodeFor(typeName, "unauthorized"),
				Description: f.String(),
			}
		}
	}

	errF := elem.FieldByName("Error")
	if errF.IsValid() && errF.Kind() == reflect.String {
		return APIError{
			StatusCode:      effective(status, 500),
			Code:            errF.String(),
			Description:     stringField(elem, "Description"),
			DescriptionCode: stringField(elem, "DescriptionCode"),
			Params:          paramsField(elem, "Params"),
		}
	}

	return fmt.Errorf("ogenclient: unexpected response %T", res)
}

// statusFromTypeName extracts an HTTP status from the type-name suffix.
func statusFromTypeName(name string) int {
	for suffix, code := range knownSuffixStatuses {
		if strings.HasSuffix(name, suffix) {
			return code
		}
	}
	return 0
}

var knownSuffixStatuses = map[string]int{
	"BadRequest":           400,
	"Unauthorized":         401,
	"UnauthorizedError":    401,
	"Forbidden":            403,
	"NotFound":             404,
	"Conflict":             409,
	"PreconditionRequired": 428,
	"HTTPValidationError":  422,
	"InternalServerError":  500,
	"Maintenance":          503,
	"GatewayTimeout":       504,
	"InsufficientStorage":  507,
}

func effective(status, fallback int) int {
	if status != 0 {
		return status
	}
	return fallback
}

func defaultCodeFor(typeName, fallback string) string {
	if typeName == "" {
		return fallback
	}
	return strings.ToLower(typeName)
}

func stringField(rv reflect.Value, name string) string {
	f := rv.FieldByName(name)
	if !f.IsValid() || f.Kind() != reflect.String {
		return ""
	}
	return f.String()
}

// paramsField walks any map-shaped field, json-unmarshalling raw bytes when
// values are []byte (ogen `jx.Raw` fields). Non-string keys are ignored.
func paramsField(rv reflect.Value, name string) map[string]any {
	f := rv.FieldByName(name)
	if !f.IsValid() {
		return nil
	}
	if f.Kind() != reflect.Map || f.Type().Key().Kind() != reflect.String {
		return nil
	}
	if f.Len() == 0 {
		return nil
	}
	out := make(map[string]any, f.Len())
	iter := f.MapRange()
	for iter.Next() {
		k := iter.Key().String()
		v := iter.Value()
		switch v.Kind() {
		case reflect.Slice:
			if v.Type().Elem().Kind() == reflect.Uint8 {
				raw := v.Bytes()
				var decoded any
				if err := json.Unmarshal(raw, &decoded); err == nil {
					out[k] = decoded
					continue
				}
				out[k] = string(raw)
				continue
			}
			out[k] = v.Interface()
		default:
			out[k] = v.Interface()
		}
	}
	return out
}
