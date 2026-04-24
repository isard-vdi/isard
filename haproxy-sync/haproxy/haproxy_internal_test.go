package haproxy

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestCheckResponse(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		Response          string
		SuccessIndicators []string
		ExpectedErr       string
	}{
		"should succeed with an empty response and no indicators": {},
		"should succeed when new ssl cert returns success": {
			Response:          "New empty certificate store '/certs/ex.pem'!",
			SuccessIndicators: []string{"New empty certificate store"},
		},
		"should succeed when set ssl cert creates a transaction": {
			Response:          "Transaction created for certificate /certs/ex.pem!",
			SuccessIndicators: []string{"Transaction created", "Transaction updated"},
		},
		"should succeed when set ssl cert updates a transaction": {
			Response:          "Transaction updated for certificate /certs/ex.pem!",
			SuccessIndicators: []string{"Transaction created", "Transaction updated"},
		},
		"should succeed when commit ssl cert returns success": {
			Response:          "Committing /certs/ex.pem.\nSuccess!",
			SuccessIndicators: []string{"Success!"},
		},
		"should succeed when add ssl crt-list returns success": {
			Response:          "Inserting certificate '/certs/ex.pem' in crt-list '/etc/haproxy/crt-list'.\nSuccess!",
			SuccessIndicators: []string{"Success!"},
		},
		"should succeed when del ssl crt-list returns success": {
			Response:          "Entry '/certs/ex.pem' deleted in crtlist '/etc/haproxy/crt-list'!",
			SuccessIndicators: []string{"deleted in crtlist"},
		},
		"should succeed when del ssl cert returns success": {
			Response:          "Certificate '/certs/ex.pem' deleted!",
			SuccessIndicators: []string{"deleted!"},
		},
		"should succeed when show map response contains hex address": {
			Response:          "0x56142a398 example.com _",
			SuccessIndicators: []string{"0x"},
		},
		"should succeed when new ssl cert slot already exists": {
			Response:          "Certificate '/certs/ex.pem' already exists!",
			SuccessIndicators: []string{"New empty certificate store", "already exists"},
		},
		"should succeed when add ssl crt-list entry already exists": {
			Response:          "Can't edit the crt-list: file already exists in this directory!",
			SuccessIndicators: []string{"Success!", "already exists"},
		},
		"should return an error if the response is not empty and no indicators are given": {
			Response:    "Certificate '/certs/ex.pem' already exists!",
			ExpectedErr: "haproxy error: Certificate '/certs/ex.pem' already exists!",
		},
		"should return an error if the response does not match the indicator": {
			Response:          "Certificate '/certs/ex.pem' already exists!",
			SuccessIndicators: []string{"New empty certificate store"},
			ExpectedErr:       "haproxy error: Certificate '/certs/ex.pem' already exists!",
		},
		"should return an error if no certificate is found": {
			Response:          "No certificate found with name '/certs/ex.pem'",
			SuccessIndicators: []string{"Transaction created", "Transaction updated"},
			ExpectedErr:       "haproxy error: No certificate found with name '/certs/ex.pem'",
		},
		"should return an error if there is no ongoing transaction": {
			Response:          "No ongoing transaction for certificate '/certs/ex.pem'!",
			SuccessIndicators: []string{"Success!"},
			ExpectedErr:       "haproxy error: No ongoing transaction for certificate '/certs/ex.pem'!",
		},
		"should return an error for unknown map identifier without indicators": {
			Response:    "Unknown map identifier 'nonexistent'.",
			ExpectedErr: "haproxy error: Unknown map identifier 'nonexistent'.",
		},
		"should return an error for unknown map identifier with indicator": {
			Response:          "Unknown map identifier 'nonexistent'.",
			SuccessIndicators: []string{"0x"},
			ExpectedErr:       "haproxy error: Unknown map identifier 'nonexistent'.",
		},
		"should return an error for unknown response without indicators": {
			Response:    "some unknown response text",
			ExpectedErr: "haproxy error: some unknown response text",
		},
		"should return an error for unknown response with indicator": {
			Response:          "some unknown response text",
			SuccessIndicators: []string{"Success!"},
			ExpectedErr:       "haproxy error: some unknown response text",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			err := checkResponse(tc.Response, tc.SuccessIndicators...)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
				return
			}

			assert.NoError(err)
		})
	}
}
