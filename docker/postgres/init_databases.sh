#!/bin/bash

psql -v ON_ERROR_STOP=1 --username root <<-EOSQL
    CREATE USER admin SUPERUSER PASSWORD '$WEBAPP_ADMIN_PWD';
    CREATE DATABASE isard_nc;
    GRANT ALL PRIVILEGES ON DATABASE isard_nc TO admin;
EOSQL