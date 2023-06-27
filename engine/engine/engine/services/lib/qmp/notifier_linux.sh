#!/bin/sh

notifier() {{
    # Like nohup
    trap '' HUP INT

    # Notify the users on the tty
    echo '{message}' | wall;

    # Notify the users using a graphical interface
    if which sw-notify-send; then
        CMD="$(which sw-notify-send) -a IsardVDI -u CRITICAL '{title}' '{message}'"

    elif which notify-send; then
        CMD="$(which notify-send) -a IsardVDI -u CRITICAL '{title}' '{message}'"

    elif which gdbus; then
        CMD="gdbus call --session \
            --dest=org.freedesktop.Notifications \
            --object-path=/org/freedesktop/Notifications \
            --method=org.freedesktop.Notifications.Notify \
            'IsardVDI' 0 '' '{title}' '{message}' \
            '[]' '{{}}' 5000"

    else
        echo "No graphical notification program found!"
        exit 1
    fi

    for uid in /run/user/*; do
        PASSWD="$(getent passwd "$(basename "$uid")")"
        USERNAME="$(echo "$PASSWD" | cut -d: -f1)"
        USER_HOME="$(echo "$PASSWD" | cut -d: -f6)"
        USER_BUS_ADDRESS="unix:path=/run/user/$(basename "$uid")/bus"

        if [ -d "$USER_HOME/.dbus/session-bus" ]; then
            USER_BUS_ADDRESS="$(cat "$USER_HOME"/.dbus/session-bus/* | grep "DBUS_SESSION_BUS_ADDRESS=" | cut -d= -f2-)"
        fi

        runuser -l "$USERNAME" -c "DBUS_SESSION_BUS_ADDRESS=$USER_BUS_ADDRESS $CMD || exit_code=$?"
    done
}}

notifier&
