#!/bin/sh

SCRIPT_DIR="`dirname "$0"`"
DEFAULT_CONFIG_FILE="$SCRIPT_DIR/../../isardvdi.cfg"

if [ "$1" ]; then
    CONFIG_FILE="$1"
else
    CONFIG_FILE="$DEFAULT_CONFIG_FILE"
fi

[ ! -f "$CONFIG_FILE" ] && echo "Error: $CONFIG_FILE not found" && exit 1

if grep -q "TEST CONFIGURATION FIELDS" "$CONFIG_FILE"; then
    echo "Test fields already exist"
    exit 0
fi

cat >> "$CONFIG_FILE" << 'EOF'

##################################################################
## TEST CONFIGURATION FIELDS                                    ##
##################################################################

# ------ Google OAuth -----------------------------------------------
## Google authentication configuration for tests
AUTHENTICATION_AUTHENTICATION_GOOGLE_ENABLED=true

# ------ Notify Email ---------------------------------------------------
## Email credentials that will be used to send email notifications.
NOTIFY_EMAIL=True

# ------ LDAP -----------------------------------------------------------
## LDAP authentication (updated configuration from v2.29.0)
AUTHENTICATION_AUTHENTICATION_LDAP_ENABLED=true

# ------ Bastion -------------------------------------------------------
## Bastion feature configuration
BASTION_ENABLED=true
BASTION_SSH_PORT=2222

# ------ Authentication Test SAML -----------------------------------
## SAML test category IDs (comma separated)
AUTHENTICATION_TEST_SAML_CATEGORY_IDS=default
EOF

# TODO: this is the initial state. For more tests other values may be needed.

echo "Test fields added successfully"
