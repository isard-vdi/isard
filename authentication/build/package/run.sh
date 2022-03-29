#!/bin/sh

if [ "$AUTHENTICATION_AUTHENTICATION_SAML_ENABLED" == "true" ]; then
    if [ -z "$AUTHENTICATION_AUTHENTICATION_SAML_KEY_FILE" ]; then
        export AUTHENTICATION_AUTHENTICATION_SAML_KEY_FILE="/keys/isardvdi.key"
    fi

    if [ -z "$AUTHENTICATION_AUTHENTICATION_SAML_CERT_FILE" ]; then
        export AUTHENTICATION_AUTHENTICATION_SAML_CERT_FILE="/keys/isardvdi.cert"
    fi

    if [ ! -e "$AUTHENTICATION_AUTHENTICATION_SAML_KEY_FILE" ] || [ ! -e "$AUTHENTICATION_AUTHENTICATION_SAML_CERT_FILE" ]; then
        # Ensure that neither of them exist
        rm -rf $AUTHENTICATION_AUTHENTICATION_SAML_KEY_FILE $AUTHENTICATION_AUTHENTICATION_SAML_CERT_FILE

        # Generate the certificates
        openssl req -x509 -newkey rsa:4096 -keyout $AUTHENTICATION_AUTHENTICATION_SAML_KEY_FILE -out $AUTHENTICATION_AUTHENTICATION_SAML_CERT_FILE -days 3650 -nodes -subj "/CN=$DOMAIN"
    fi
fi

/authentication
