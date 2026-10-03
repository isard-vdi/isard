"""Which component may write a domain's terminal state, declared in one place."""

ENGINE = "engine"
STORAGE_CHAIN = "storage-chain"
TERMINAL = "terminal"

#: Who executes the work that leaves a status; the test fails on an unclassified one.
STATUS_EXECUTOR = {
    "Creating": STORAGE_CHAIN,
    "CreatingAndStarting": STORAGE_CHAIN,
    "CreatingDisk": STORAGE_CHAIN,
    "CreatingDiskFromScratch": STORAGE_CHAIN,
    "CreatingDomainFromDisk": STORAGE_CHAIN,
    "CreatingTemplate": STORAGE_CHAIN,
    "Downloaded": STORAGE_CHAIN,
    "Downloading": STORAGE_CHAIN,
    "DiskNew": STORAGE_CHAIN,
    "Maintenance": STORAGE_CHAIN,
    "CreatingDomain": ENGINE,
    "Deleting": ENGINE,
    "DeletingDomainDisk": ENGINE,
    "DiskDeleted": ENGINE,
    "Shutdown": ENGINE,
    "Shutting-down": ENGINE,
    "Starting": ENGINE,
    "StartingDomainDisposable": ENGINE,
    "StartingPaused": ENGINE,
    "Stopping": ENGINE,
    "Updating": ENGINE,
    "Failed": TERMINAL,
    "Unknown": TERMINAL,
}

#: Statuses two components both claim to finish, with why; the test allows no others.
CONTESTED = {
    "CreatingDomain": "engine fails it and the change-handler promotes it; owner undecided",
}


def executor_of(status):
    """Return the component that executes ``status``, or ``None`` if undeclared."""
    return STATUS_EXECUTOR.get(status)
