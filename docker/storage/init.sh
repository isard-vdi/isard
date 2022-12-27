export PYTHONWARNINGS="ignore:Unverified HTTPS request"
python3 /api/start.py &

# Wait background tasks and clean it at termination.
stop_background_tasks()
{
  echo Stopping background tasks...
  trap - SIGTERM
  kill -TERM 0
  wait
}
trap stop_background_tasks SIGTERM SIGINT SIGQUIT 
wait
