package isardvdi

type DomainState string

const (
	DomainStateUnknown                  = "Unknown"
	DomainStateFailed                   = "Failed"
	DomainStateStarting                 = "Starting"
	DomainStateStartingDomainDisposable = "StartingDomainDisposable"
	DomainStateStarted                  = "Started"
	DomainStateStopping                 = "Stopping"
	DomainStateShuttingDown             = "Shutting-down"
	DomainStateStopped                  = "Stopped"
	DomainStateCreating                 = "Creating"
	DomainStateCreatingAndStarting      = "CreatingAndStarting"
	DomainStateCreatingDiskFromScratch  = "CreatingDiskFromScratch"
	DomainStateCreatingFromBuilder      = "CreatingFromBuilder"
	DomainStateCreatingDomain           = "CreatingDomain"
	DomainStateUpdating                 = "Updating"
	DomainStateDeleting                 = "Deleting"
	DomainStateDeletingDomainDisk       = "DeletingDomainDisk"
	DomainStateDiskDeleted              = "DiskDeleted"
)
