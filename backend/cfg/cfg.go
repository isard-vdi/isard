package cfg

type Cfg struct {
	BackendHost string
	Redis       Redis
	Auth        Auth
	Isard       Isard
}

type Redis struct {
	Host     string
	Port     int
	Password string
}

type Auth struct {
	AutoRegistration bool
	GitHub           AuthGitHub
	SAML             AuthSAML
	Google           AuthGoogle
}

type AuthGitHub struct {
	Host,
	ID,
	Secret string
}

type AuthSAML struct {
	CertPath,
	KeyPath,
	IdpMetadataPath,
	IdpMetadataURL,
	Callback,

	AttrID,
	AttrUsername,
	AttrName,
	AttrEmail,
	AttrPhoto string
}

type AuthGoogle struct {
	ID,
	Secret string
}

type Isard struct {
	Host string
	Port int
}
