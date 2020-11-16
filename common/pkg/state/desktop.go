package state

import "github.com/qmuntal/stateless"

const (
	DesktopStateUnknown          = "Unknown"
	DesktopStatePreCreating      = "PreCreating"
	DesktopStateCreating         = "Creating"
	DesktopStateCreatingPreXML   = "CreatingPreXML"
	DesktopStateCreatingXML      = "CreatingXML"
	DesktopStateCreatingPostXML  = "CreatingPostXML"
	DesktopStateCreatingPreDisk  = "CreatingPreDisk"
	DesktopStateCreatingDisk     = "CreatingDisk"
	DesktopStateCreatingPostDisk = "CreatingPostDisk"
	DesktopStatePostCreating     = "PostCreating"
	DesktopStateCreatingFailed   = "CreatingFailed"
	DesktopStateStarted          = "Started"
	DesktopStatePausing          = "Pausing"
	DesktopStatePaused           = "Paused"
	DesktopStateResuming         = "Resuming"
	DesktopStateMigrating        = "Migrating"
	DesktopStateStopping         = "Stopping"
	DesktopStateStopped          = "Stopped"
	DesktopStateTemplating       = "Templating"
	DesktopStateUpdating         = "Updating"
	DesktopStateDeleting         = "Deleting"
	DesktopStateDeleted          = "Deleted"
	DesktopStateStarting         = "Starting"
)

const (
	DesktopTriggerUnknown                 = "Unknown"
	DesktopTriggerUnknownToStarted        = "UnknownToStarted"
	DesktopTriggerUnknownToPaused         = "UnknownToPaused"
	DesktopTriggerUnknownToStopped        = "UnknownToStopped"
	DesktopTriggerUnknownToDeleted        = "UnknownToDeleted"
	DesktopTriggerPreCreatingSuccess      = "PreCreatingSuccess"
	DesktopTriggerPreCreatingFailure      = "PreCreatingFailure"
	DesktopTriggerCreatingPreXMLSuccess   = "CreatingPreXMLSuccess"
	DesktopTriggerCreatingPreXMLFailure   = "CreatingPreXMLFailure"
	DesktopTriggerCreatingXMLSuccess      = "CreatingXMLSuccess"
	DesktopTriggerCreatingXMLFailure      = "CreatingXMLFailure"
	DesktopTriggerCreatingPostXMLSuccess  = "CreatingPostXMLSuccess"
	DesktopTriggerCreatingPostXMLFailure  = "CreatingPostXMLFailure"
	DesktopTriggerCreatingPreDiskSuccess  = "CreatingPreDiskSuccess"
	DesktopTriggerCreatingPreDiskFailure  = "CreatingPreDiskFailure"
	DesktopTriggerCreatingDiskSuccess     = "CreatingDiskSuccess"
	DesktopTriggerCreatingDiskFailure     = "CreatingDiskFailure"
	DesktopTriggerCreatingPostDiskSuccess = "CreatingPostDiskSuccess"
	DesktopTriggerCreatingPostDiskFailure = "CreatingPostDiskFailure"
	DesktopTriggerPostCreatingSuccess     = "PostCreatingSuccess"
	DesktopTriggerPostCreatingFailure     = "PostCreatingFailure"
	DesktopTriggerCreatingRetry           = "CreatingRetry"
	DesktopTriggerPause                   = "Pause"
	DesktopTriggerPausingSuccess          = "PausingSuccess"
	DesktopTriggerPausingFailure          = "PausingFailure"
	DesktopTriggerResume                  = "Resume"
	DesktopTriggerResumingSuccess         = "ResumingSuccess"
	DesktopTriggerResumingFailure         = "ResumingFailure"
	DesktopTriggerMigrate                 = "Migrate"
	DesktopTriggerMigratingSuccess        = "MigratingSuccess"
	DesktopTriggerMigratingFailure        = "MigratingFailure"
	DesktopTriggerStop                    = "Stop"
	DesktopTriggerStoppingSuccess         = "StoppingSuccess"
	DesktopTriggerStoppingFailure         = "StoppingFailure"
	DesktopTriggerTemplate                = "Template"
	DesktopTriggerTemplatingSuccess       = "TemplatingSuccess"
	DesktopTriggerTemplatingFailure       = "TemplatingFailure"
	DesktopTriggerUpdate                  = "Update"
	DesktopTriggerUpdatingSuccess         = "UpdatingSuccess"
	DesktopTriggerUpdatingFailure         = "UpdatingFailure"
	DesktopTriggerDelete                  = "Delete"
	DesktopTriggerDeletingSuccess         = "DeletingSuccess"
	DesktopTriggerDeletingFailure         = "DeletingFailure"
	DesktopTriggerStart                   = "Start"
	DesktopTriggerStartingSuccess         = "StartingSuccess"
	DesktopTriggerStartingFailure         = "StartingFailure"
)

func NewDesktopState(m *stateless.StateMachine) {
	m.Configure(DesktopStatePreCreating).SubstateOf(DesktopStateCreating).
		Permit(DesktopTriggerPreCreatingSuccess, DesktopStateCreatingPreXML).
		Permit(DesktopTriggerPreCreatingFailure, DesktopStateCreatingFailed).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateCreatingPreXML).SubstateOf(DesktopStateCreating).
		Permit(DesktopTriggerCreatingPreXMLSuccess, DesktopStateCreatingXML).
		Permit(DesktopTriggerCreatingPreXMLFailure, DesktopStateCreatingFailed).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateCreatingXML).SubstateOf(DesktopStateCreating).
		Permit(DesktopTriggerCreatingXMLSuccess, DesktopStateCreatingPostXML).
		Permit(DesktopTriggerCreatingXMLFailure, DesktopStateCreatingFailed).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateCreatingPostXML).SubstateOf(DesktopStateCreating).
		Permit(DesktopTriggerCreatingPostXMLSuccess, DesktopStateCreatingPreDisk).
		Permit(DesktopTriggerCreatingPostXMLFailure, DesktopStateCreatingFailed).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateCreatingPreDisk).SubstateOf(DesktopStateCreating).
		Permit(DesktopTriggerCreatingPreDiskSuccess, DesktopStateCreatingDisk).
		Permit(DesktopTriggerCreatingPreDiskFailure, DesktopStateCreatingFailed).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateCreatingDisk).SubstateOf(DesktopStateCreating).
		Permit(DesktopTriggerCreatingDiskSuccess, DesktopStateCreatingPostDisk).
		Permit(DesktopTriggerCreatingDiskFailure, DesktopStateCreatingFailed).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateCreatingPostDisk).SubstateOf(DesktopStateCreating).
		Permit(DesktopTriggerCreatingPostDiskSuccess, DesktopStatePostCreating).
		Permit(DesktopTriggerCreatingPostDiskFailure, DesktopStateCreatingFailed).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStatePostCreating).SubstateOf(DesktopStateCreating).
		Permit(DesktopTriggerPostCreatingSuccess, DesktopStateStarted).
		Permit(DesktopTriggerPostCreatingFailure, DesktopStateCreatingFailed).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateCreatingFailed).
		Permit(DesktopTriggerCreatingRetry, DesktopStatePreCreating).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateStarted).
		Permit(DesktopTriggerPause, DesktopStatePausing).
		Permit(DesktopTriggerMigrate, DesktopStateMigrating).
		Permit(DesktopTriggerStop, DesktopStateStopping)

	m.Configure(DesktopStatePausing).SubstateOf(DesktopStateStarted).
		Permit(DesktopTriggerPausingSuccess, DesktopStatePaused).
		Permit(DesktopTriggerPausingFailure, DesktopStateUnknown).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStatePaused).
		Permit(DesktopTriggerResume, DesktopStateResuming).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateResuming).SubstateOf(DesktopStatePaused).
		Permit(DesktopTriggerResumingSuccess, DesktopStateStarted).
		Permit(DesktopTriggerResumingFailure, DesktopStateUnknown).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateMigrating).SubstateOf(DesktopStateStarted).
		Permit(DesktopTriggerMigratingSuccess, DesktopStateStarted).
		Permit(DesktopTriggerMigratingFailure, DesktopStateUnknown).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateStopping).SubstateOf(DesktopStateStarted).
		Permit(DesktopTriggerStoppingSuccess, DesktopStateStopped).
		Permit(DesktopTriggerStoppingFailure, DesktopStateUnknown).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateStopped).
		Permit(DesktopTriggerTemplate, DesktopStateTemplating).
		Permit(DesktopTriggerUpdate, DesktopStateUpdating).
		Permit(DesktopTriggerDelete, DesktopStateDeleting).
		Permit(DesktopTriggerStart, DesktopStateStarting).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateTemplating).SubstateOf(DesktopStateStopped).
		Permit(DesktopTriggerTemplatingSuccess, DesktopStateStopped).
		Permit(DesktopTriggerTemplatingFailure, DesktopStateUnknown).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateUpdating).SubstateOf(DesktopStateStopped).
		Permit(DesktopTriggerUpdatingSuccess, DesktopStateStopped).
		Permit(DesktopTriggerUpdatingFailure, DesktopStateUnknown).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateDeleting).SubstateOf(DesktopStateStopped).
		Permit(DesktopTriggerDeletingSuccess, DesktopStateDeleted).
		Permit(DesktopTriggerDeletingFailure, DesktopStateUnknown).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateStarting).SubstateOf(DesktopStateStopped).
		Permit(DesktopTriggerStartingSuccess, DesktopStateStarted).
		Permit(DesktopTriggerStartingFailure, DesktopStateUnknown).
		Permit(DesktopTriggerUnknown, DesktopStateUnknown)

	m.Configure(DesktopStateUnknown).
		Permit(DesktopTriggerUnknownToStarted, DesktopStateStarted).
		Permit(DesktopTriggerUnknownToPaused, DesktopStatePaused).
		Permit(DesktopTriggerUnknownToStopped, DesktopStateStopped).
		Permit(DesktopTriggerUnknownToDeleted, DesktopStateDeleted)
}
