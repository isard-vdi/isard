//go:generate go run gen.go

package state

import "github.com/qmuntal/stateless"

type HyperState string

const (
	HyperStateUnknown   HyperState = "Unknown"
	HyperStateReady     HyperState = "Ready"
	HyperStateDown      HyperState = "Down"
	HyperStateMigrating HyperState = "Migrating"
)

type HyperTrigger string

const (
	HyperTriggerUnknown           HyperTrigger = "Unknown"
	HyperTriggerUnkownToReady     HyperTrigger = "UnknownToReady"
	HyperTriggerUnkownToDown      HyperTrigger = "UnknownToDown"
	HyperTriggerUnkownToMigrating HyperTrigger = "UnknownToMigrating"
	HyperTriggerMigrating         HyperTrigger = "Migrating"
	HyperTriggerDown              HyperTrigger = "Down"
	HyperTriggerReady             HyperTrigger = "Ready"
)

func NewHyperState() *stateless.StateMachine {
	m := stateless.NewStateMachine(HyperStateReady)
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

	return m
}
