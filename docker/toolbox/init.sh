/filebrowser config init --database=/config/filebrowser.db

# Branding
/filebrowser config set --branding.name "IsardVDI Storage" --branding.files "/branding" --branding.disableExternal --database=/config/filebrowser.db

# Admin user
/filebrowser users add admin ${WEBAPP_ADMIN_PWD} --database=/config/filebrowser.db
/filebrowser users update admin -p ${WEBAPP_ADMIN_PWD} --database=/config/filebrowser.db

## jwt authentication approach: https://github.com/filebrowser/filebrowser/issues/1448

# https://github.com/filebrowser/docs/blob/master/configuration/command-runner.md
# Note: this updates database and CAN'T be executed when filebrowser ir unning (db locked)

while true; do 
  /filebrowser cmds rm after_upload 0 --database=/config/filebrowser.db
  if [[ "$?" -ne 0 ]]; then 
    break
  fi
done
/filebrowser cmds add after_upload "/usr/bin/python3 /src/media-scan.py -f $FILE" --database=/config/filebrowser.db

while true; do 
  /filebrowser cmds rm after_copy 0 --database=/config/filebrowser.db
  if [[ "$?" -ne 0 ]]; then 
    break
  fi
done
/filebrowser cmds add after_copy "/usr/bin/python3 /src/media-scan.py -f $DESTINATION" --database=/config/filebrowser.db

while true; do 
  /filebrowser cmds rm after_delete 0 --database=/config/filebrowser.db
  if [[ "$?" -ne 0 ]]; then 
    break
  fi
done
/filebrowser cmds add after_delete "/usr/bin/python3 /src/media-scan.py -d $FILE" --database=/config/filebrowser.db


# Server
/filebrowser --root=/isard --address=0.0.0.0 --port=8080 --database=/config/filebrowser.db &

# api
export PYTHONWARNINGS="ignore:Unverified HTTPS request"
cd /api && python3 start.py