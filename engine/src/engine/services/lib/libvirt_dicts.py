virDomainRunningReason = {
    0: {"id_reason": "VIR_DOMAIN_RUNNING_UNKNOWN", "detail": ""},
    1: {"id_reason": "VIR_DOMAIN_RUNNING_BOOTED", "detail": "normal startup from boot"},
    2: {
        "id_reason": "VIR_DOMAIN_RUNNING_MIGRATED",
        "detail": "migrated from another host",
    },
    3: {
        "id_reason": "VIR_DOMAIN_RUNNING_RESTORED",
        "detail": "restored from a state file",
    },
    4: {
        "id_reason": "VIR_DOMAIN_RUNNING_FROM_SNAPSHOT",
        "detail": "restored from snapshot",
    },
    5: {
        "id_reason": "VIR_DOMAIN_RUNNING_UNPAUSED",
        "detail": "returned from paused state",
    },
    6: {
        "id_reason": "VIR_DOMAIN_RUNNING_MIGRATION_CANCELED",
        "detail": "returned from migration",
    },
    7: {
        "id_reason": "VIR_DOMAIN_RUNNING_SAVE_CANCELED",
        "detail": "returned from failed save process",
    },
    8: {
        "id_reason": "VIR_DOMAIN_RUNNING_WAKEUP",
        "detail": "returned from pmsuspended due to wakeup event",
    },
    9: {"id_reason": "VIR_DOMAIN_RUNNING_CRASHED", "detail": "resumed from crashed"},
    10: {
        "id_reason": "VIR_DOMAIN_RUNNING_POSTCOPY",
        "detail": "running in post-copy migration mode",
    },
    11: {"id_reason": "VIR_DOMAIN_RUNNING_LAST", "detail": ""},
}


virDomainPausedReason = {
    0: {"id_reason": "VIR_DOMAIN_PAUSED_UNKNOWN", "detail": "the reason is unknown"},
    1: {"id_reason": "VIR_DOMAIN_PAUSED_USER", "detail": "paused on user request"},
    2: {
        "id_reason": "VIR_DOMAIN_PAUSED_MIGRATION",
        "detail": "paused for offline migration",
    },
    3: {"id_reason": "VIR_DOMAIN_PAUSED_SAVE", "detail": "paused for save"},
    4: {
        "id_reason": "VIR_DOMAIN_PAUSED_DUMP",
        "detail": "paused for offline core dump",
    },
    5: {
        "id_reason": "VIR_DOMAIN_PAUSED_IOERROR",
        "detail": "paused due to a disk I/O error",
    },
    6: {
        "id_reason": "VIR_DOMAIN_PAUSED_WATCHDOG",
        "detail": "paused due to a watchdog event",
    },
    7: {
        "id_reason": "VIR_DOMAIN_PAUSED_FROM_SNAPSHOT",
        "detail": "paused after restoring from snapshot",
    },
    8: {
        "id_reason": "VIR_DOMAIN_PAUSED_SHUTTING_DOWN",
        "detail": "paused during shutdown process",
    },
    9: {
        "id_reason": "VIR_DOMAIN_PAUSED_SNAPSHOT",
        "detail": "paused while creating a snapshot",
    },
    10: {
        "id_reason": "VIR_DOMAIN_PAUSED_CRASHED",
        "detail": "paused due to a guest crash",
    },
    11: {
        "id_reason": "VIR_DOMAIN_PAUSED_STARTING_UP",
        "detail": "the domain is being started",
    },
    12: {
        "id_reason": "VIR_DOMAIN_PAUSED_POSTCOPY",
        "detail": "paused for post-copy migration",
    },
    13: {
        "id_reason": "VIR_DOMAIN_PAUSED_POSTCOPY_FAILED",
        "detail": "paused after failed post-copy",
    },
    14: {"id_reason": "VIR_DOMAIN_PAUSED_LAST", "detail": ""},
}

virDomainShutdownReason = {
    0: {"reason_id": "VIR_DOMAIN_SHUTDOWN_UNKNOWN", "reason": "the reason is unknown"},
    1: {
        "reason_id": "VIR_DOMAIN_SHUTDOWN_USER",
        "reason": "shutting down on user request",
    },
    2: {"reason_id": "VIR_DOMAIN_SHUTDOWN_LAST", "reason": ""},
}

virDomainShutoffReason = {
    0: {"reason_id": "VIR_DOMAIN_SHUTOFF_UNKNOWN", "reason": "the reason is unknown"},
    1: {"reason_id": "VIR_DOMAIN_SHUTOFF_SHUTDOWN", "reason": "normal shutdown"},
    2: {"reason_id": "VIR_DOMAIN_SHUTOFF_DESTROYED", "reason": "forced poweroff"},
    3: {"reason_id": "VIR_DOMAIN_SHUTOFF_CRASHED", "reason": "domain crashed"},
    4: {
        "reason_id": "VIR_DOMAIN_SHUTOFF_MIGRATED",
        "reason": "migrated to another host",
    },
    5: {"reason_id": "VIR_DOMAIN_SHUTOFF_SAVED", "reason": "saved to a file"},
    6: {"reason_id": "VIR_DOMAIN_SHUTOFF_FAILED", "reason": "domain failed to start"},
    7: {
        "reason_id": "VIR_DOMAIN_SHUTOFF_FROM_SNAPSHOT",
        "reason": "restored from a snapshot which was taken while domain was shutoff",
    },
    8: {
        "reason_id": "VIR_DOMAIN_SHUTOFF_DAEMON",
        "reason": "daemon decides to kill domain during reconnection processing",
    },
    9: {"reason_id": "VIR_DOMAIN_SHUTOFF_LAST", "reason": ""},
}

virDomainCrashedReason = {
    0: {
        "reason_id": "VIR_DOMAIN_CRASHED_UNKNOWN",
        "reason": "crashed for unknown reason",
    },
    1: {"reason_id": "VIR_DOMAIN_CRASHED_PANICKED", "reason": "domain panicked"},
    2: {"reason_id": "VIR_DOMAIN_CRASHED_LAST", "reason": ""},
}


virDomainState = {
    0: {
        "status": "Unknown",
        "libvirt_state": "VIR_DOMAIN_NOSTATE",
        "detail": "no state",
    },
    1: {
        "status": "Started",
        "libvirt_state": "VIR_DOMAIN_RUNNING",
        "detail": "the domain is running",
        "reason": virDomainRunningReason,
    },
    2: {
        "status": "Unknown",
        "libvirt_state": "VIR_DOMAIN_BLOCKED",
        "detail": "the domain is blocked on resource",
    },
    3: {
        "status": "Paused",
        "libvirt_state": "VIR_DOMAIN_PAUSED",
        "detail": "the domain is paused by user",
        "reason": virDomainPausedReason,
    },
    4: {
        "status": "Unknown",
        "libvirt_state": "VIR_DOMAIN_SHUTDOWN",
        "detail": "the domain is being shut down",
        "reason": virDomainShutdownReason,
    },
    5: {
        "status": "Stopped",
        "libvirt_state": "VIR_DOMAIN_SHUTOFF",
        "detail": "the domain is shut off",
        "reason": virDomainShutoffReason,
    },
    6: {
        "status": "Crashed",
        "libvirt_state": "VIR_DOMAIN_CRASHED",
        "detail": "the domain is crashed",
        "reason": virDomainCrashedReason,
    },
    7: {
        "status": "Unknown",
        "libvirt_state": "VIR_DOMAIN_PMSUSPENDED",
        "detail": "the domain is suspended by guest power management",
    },
    8: {
        "status": "Unknown",
        "libvirt_state": "VIR_DOMAIN_LAST",
        "detail": "NB: this enum value will increase over time as new events are added to the libvirt API. It reflects the last state supported by this version of the libvirt API.",
    },
}
