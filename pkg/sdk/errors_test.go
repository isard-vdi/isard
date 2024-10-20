package sdk_test

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"gitlab.com/isard/isardvdi/pkg/sdk"
)

func TestErrors(t *testing.T) {
	assert := assert.New(t)

	const NotFound = `{"data":"","debug":"","description":"Hypervisor with ID isard-hyiipervisor does not exist.","description_code":"not_found","error":"not_found","function":"api_hypervisors.py:87:get_hypervisors","function_call":"HypervisorsView.py:242:api_v3_orch_hypers_list","msg":"Not found","params":null,"request":"----------- REQUEST START -----------\nGET http://localhost/api/v3/orchestrator/hypervisor/isard-hyiipervisor\r\nHost: localhost\r\nUser-Agent: isardvdi-cli v0.26.1\r\nAccept: application/json\r\nAuthorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE2NzgxMDk1NTMsImlzcyI6ImlzYXJkLWF1dGhlbnRpY2F0aW9uIiwia2lkIjoiaXNhcmR2ZGkiLCJkYXRhIjp7InByb3ZpZGVyIjoibG9jYWwiLCJ1c2VyX2lkIjoibG9jYWwtZGVmYXVsdC1hZG1pbi1hZG1pbiIsInJvbGVfaWQiOiJhZG1pbiIsImNhdGVnb3J5X2lkIjoiZGVmYXVsdCIsImdyb3VwX2lkIjoiZGVmYXVsdC1kZWZhdWx0IiwibmFtZSI6IkFkbWluaXN0cmF0b3IifX0.-hqxaGYbWIuk-OhtYPsIYWE6aqhmeCK_bCHGfzCa8Qg\r\nAccept-Encoding: gzip\r\nX-Forwarded-For: 172.31.255.1\r\nConnection: close\r\n\r\n----------- REQUEST STOP  -----------"}`
	workingErr := sdk.Err{}
	err := json.Unmarshal([]byte(NotFound), &workingErr)

	assert.NoError(err)
	assert.True(errors.Is(workingErr, sdk.ErrNotFound))

	const BadRequest = `{"data":"","debug":"","description":"Password must be at least 8 characters long","description_code":"password_character_length","error":"bad_request","function":"","function_call":"","msg":"Bad request","params":{"num":8},"request":""}`

	workingErr = sdk.Err{}
	err = json.Unmarshal([]byte(BadRequest), &workingErr)

	assert.NoError(err)

	assert.True(errors.Is(workingErr, sdk.ErrBadRequest))

	expectedDescriptionCode := "password_character_length"
	expectedDescription := "Password must be at least 8 characters long"
	expectedParams := map[string]interface{}{
		"num": float64(8),
	}
	expectedErr := sdk.Err{
		Err:             "bad_request",
		Msg:             "Bad request",
		DescriptionCode: &expectedDescriptionCode,
		Description:     &expectedDescription,
		Params:          &expectedParams,
	}
	assert.Equal(expectedErr, workingErr)
}
