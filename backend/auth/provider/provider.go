package provider

const (
	SessionStoreKey = "session"
)

type Provider interface {
	Get()
	Login()
}
