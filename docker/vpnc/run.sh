# Start guacd
guacd -b 0.0.0.0 -L info -f &

python3 networking.py
cd /src
python3 wgadmin.py
sleep infinity
