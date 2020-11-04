//go:generate go run gen.go

package state

import (
	"github.com/qmuntal/stateless"
)

const (
	HyperStateUnknown   = "Unknown"
	HyperStateReady     = "Ready"
	HyperStateDown      = "Down"
	HyperStateMigrating = "Migrating"
)

const (
	HyperTriggerUnknown           = "Unknown"
	HyperTriggerUnkownToReady     = "UnknownToReady"
	HyperTriggerUnkownToDown      = "UnknownToDown"
	HyperTriggerUnkownToMigrating = "UnknownToMigrating"
	HyperTriggerMigrating         = "Migrating"
	HyperTriggerDown              = "Down"
	HyperTriggerReady             = "Ready"
)

func NewHyperState(m *stateless.StateMachine) {
	m.Configure(HyperStateReady).
		Permit(HyperTriggerDown, HyperStateDown).
		Permit(HyperTriggerMigrating, HyperStateMigrating).
		Permit(HyperTriggerUnknown, HyperStateUnknown)

	m.Configure(HyperStateMigrating).
		Permit(HyperTriggerDown, HyperStateDown).
		Permit(HyperTriggerUnknown, HyperStateUnknown)

	m.Configure(HyperStateDown).
		Permit(HyperTriggerReady, HyperStateReady).
		Permit(HyperTriggerUnknown, HyperStateUnknown)

	m.Configure(HyperStateUnknown).
		Permit(HyperTriggerUnkownToReady, HyperStateReady).
		Permit(HyperTriggerUnkownToMigrating, HyperStateMigrating).
		Permit(HyperTriggerUnkownToDown, HyperStateDown)
}
