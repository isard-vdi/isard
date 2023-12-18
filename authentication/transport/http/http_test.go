package http

// func TestLogin(t *testing.T) {
// 	assert := assert.New(t)

// 	httptest.NewRecorder().Result().Cookies()

// 	cases := map[string]struct {
// 		PrepareTest        func(m *authentication.AuthenticationMock)
// 		Request            *http.Request
// 		ExpectedStatusCode int
// 		ExpectedCookies    []*http.Cookie
// 		ExpectedBody       []byte
// 	}{
// 		"should login correctly": {
// 			PrepareTest: func(m *authentication.AuthenticationMock) {
// 				m.On("Provider", "local")
// 				m.On("Login", context.Background(), "local", "default", map[string]string{
// 					"request_body": "",
// 					"token":        "",
// 					"provider":     "local",
// 					"category_id":  "default",
// 					"username":     "nefix",
// 					"password":     "f0cKt3Rf$",
// 				}).Return("imaginethisisatoken", "", nil)
// 			},
// 			Request:            httptest.NewRequest(http.MethodGet, "/?provider=local&category_id=default&username=nefix&password=f0cKt3Rf$", nil),
// 			ExpectedStatusCode: http.StatusOK,
// 			ExpectedCookies: []*http.Cookie{{
// 				Name:  "Authorization",
// 				Value: "imaginethisisatoken",
// 			}},
// 			ExpectedBody: []byte("imaginethisisatoken"),
// 		},
// 		"should return an error if the provider isn't sent": {
// 			Request:            httptest.NewRequest(http.MethodGet, "/?category_id=default", nil),
// 			ExpectedStatusCode: http.StatusBadRequest,
// 			ExpectedBody:       []byte("provider not sent"),
// 		},
// 		"should return an error if there's an error logging in": {
// 			PrepareTest: func(m *authentication.AuthenticationMock) {
// 				m.On("Provider", "local")
// 				m.On("Login", context.Background(), "local", "default", map[string]string{
// 					"request_body": "",
// 					"token":        "",
// 					"provider":     "local",
// 					"category_id":  "default",
// 					"username":     "nefix",
// 					"password":     "f0cKt3Rf$",
// 				}).Return("", "", errors.New("testing error"))
// 			},
// 			Request:            httptest.NewRequest(http.MethodGet, "/?provider=local&category_id=default&username=nefix&password=f0cKt3Rf$", nil),
// 			ExpectedStatusCode: http.StatusInternalServerError,
// 			ExpectedBody:       []byte("testing error"),
// 		},
// 		"should redirect if the login function says so": {
// 			PrepareTest: func(m *authentication.AuthenticationMock) {
// 				m.On("Provider", "local")
// 				m.On("Login", context.Background(), "local", "default", map[string]string{
// 					"request_body": "",
// 					"token":        "",
// 					"provider":     "local",
// 					"category_id":  "default",
// 					"username":     "nefix",
// 					"password":     "f0cKt3Rf$",
// 				}).Return("imaginethisisatoken", "/", nil)
// 			},
// 			Request:            httptest.NewRequest(http.MethodGet, "/?provider=local&category_id=default&username=nefix&password=f0cKt3Rf$", nil),
// 			ExpectedStatusCode: http.StatusFound,
// 			ExpectedCookies: []*http.Cookie{{
// 				Name:  "Authorization",
// 				Value: "imaginethisisatoken",
// 			}},
// 			ExpectedBody: []byte("<a href=\"/\">Found</a>.\n\n"),
// 		},
// 	}

// 	for name, tt := range cases {
// 		t.Run(name, func(t *testing.T) {
// 			mock := authentication.NewAuthenticationMock()

// 			a := &AuthenticationServer{Authentication: mock}

// 			if tt.PrepareTest != nil {
// 				tt.PrepareTest(mock)
// 			}

// 			rr := httptest.NewRecorder()
// 			handler := http.HandlerFunc(a.login)
// 			handler.ServeHTTP(rr, tt.Request)

// 			assert.Equal(tt.ExpectedStatusCode, rr.Code)
// 			assert.Len(rr.Result().Cookies(), len(tt.ExpectedCookies))
// 			for i, c := range rr.Result().Cookies() {
// 				assert.Equal(tt.ExpectedCookies[i].Value, c.Value)
// 			}
// 			assert.Equal(tt.ExpectedBody, rr.Body.Bytes())

// 			mock.AssertExpectations(t)
// 		})
// 	}
// }
