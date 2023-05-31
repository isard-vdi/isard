#!/bin/sh

personalUnit() {{
    # Like nohup
    trap '' HUP INT

    # KDE
    if which kioclient || which kioclient5; then
        CMD=<<EOF
ruby -e 'require "rexml/document"
include REXML

filepath = File.expand_path("~/.local/share/user-places.xbel")
doc = Document.new File.new(filepath)
root = doc.root

bookmarkTitle = "[IsardVDI] Unitat Personal"
href = "webdav{protocol}://{user}:{password}@{host}" 


bookmark = XPath.first(doc, "//bookmark[contains(@href, \"dav://\")]/title[text()=\"" + bookmarkTitle + "\"]")
if bookmark == nil
    bookmark = Element.new "bookmark"

    title = Element.new "title"
    title.text = bookmarkTitle
    bookmark.add_element title

    info = Element.new "info"
    bookmark.add_element info


    metadata = Element.new "metadata"
    metadata.attributes["owner"] = "http://freedesktop.org"
    info.add_element metadata

    icon = Element.new "bookmark:icon"
    icon.attributes["name"] = "folder-remote"
    metadata.add_element icon

    root.add_element bookmark

end

bookmark.attributes["href"] = href

doc.write(File.open(filepath,"w"), 2)'
EOF

    # Gnome
    elif which gio; then
        CREDS=""
        if [ "{verify_cert}" = "False" ]; then
            CREDS="1
"
        fi
        CREDS="${{CREDS}}{user}
{password}
"
        CMD="$(which gio) mount dav{protocol}://{host} <<< \"$CREDS\""

    # Old Gnome
    elif which gvfs-mount; then
        CMD="$(which gvfs-mount) dav{protocol}://{user}:{password}@{host}"

    else
        echo "No WebDav client found!"
        exit 1
    fi

    # Wait for users to log in
    SLEPT=0
    until ls -A1q /run/user/ | grep -q .; do
        if [ $SLEPT -eq 90 ]; then
            echo "Login users timeout!"
            exit 1
        fi

        sleep 1
        (( SLEPT++ ))
    done

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

personalUnit&
