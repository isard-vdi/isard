#!/bin/bash

cd /opt/graphite

if [ ! -f /opt/graphite/conf/local_settings.py ]; then
  echo "Creating default config for graphite-web..."
  cp /opt/graphite/conf.example/local_settings.py /opt/graphite/conf/local_settings.py
  RANDOM_STRING=$(python -c 'import random; import string; print "".join([random.SystemRandom().choice(string.digits + string.letters) for i in range(100)])')
  sed "s/%%SECRET_KEY%%/${RANDOM_STRING}/" -i /opt/graphite/conf/local_settings.py
fi

if [ ! -L /opt/graphite/webapp/graphite/local_settings.py ]; then
  echo "Creating symbolic link for local_settings.py in graphite-web..."
  ln -s /opt/graphite/conf/local_settings.py /opt/graphite/webapp/graphite/local_settings.py
fi

if [ ! -f /opt/graphite/conf/carbon.conf ]; then
  echo "Creating default config for carbon..."
  cp /opt/graphite/conf.example/carbon.conf /opt/graphite/conf/carbon.conf
fi

if [ ! -f /opt/graphite/conf/storage-schemas.conf ]; then
  echo "Creating default storage schema for carbon..."
  cp /opt/graphite/conf.example/storage-schemas.conf /opt/graphite/conf/storage-schemas.conf
fi

if [ ! -f /opt/graphite/conf/storage-aggregation.conf ]; then
  echo "Creating default storage schema for carbon..."
  cp /opt/graphite/conf.example/storage-aggregation.conf /opt/graphite/conf/storage-aggregation.conf
fi

if [ ! -f /opt/graphite/storage/graphite.db ]; then
  echo "Creating database..."
  PYTHONPATH=$GRAPHITE_ROOT/webapp django-admin.py migrate --settings=graphite.settings --run-syncdb --noinput
  chown nginx:nginx /opt/graphite/storage/graphite.db
  # Auto-magical create an django user with default login
  script="from django.contrib.auth.models import User;

username = 'admin';
password = 'admin';
email = 'admin@example.com';

if User.objects.filter(username=username).count()==0:
    User.objects.create_superuser(username, email, password);
    print('Superuser created.');
else:
    print('Superuser creation skipped.');

"
  printf "$script" | PYTHONPATH=$GRAPHITE_ROOT/webapp django-admin.py shell --settings=graphite.settings
fi

exec supervisord -c /etc/supervisord.conf
