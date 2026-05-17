
echo "Running database migration..."
PYTHONPATH=src alembic upgrade head

echo "Starting Message Broker..."
PYTHONPATH=src python src/broker/broker_app.py &
BROKER_PID=$!

sleep 2

echo "Starting S3 Gateway (backend)..."
PYTHONPATH=src python src/main.py &
BACKEND_PID=$!

sleep 2

echo "Starting Haystack Node..."
PYTHONPATH=src python src/haystack/haystack_node.py &
HAYSTACK_PID=$!

sleep 1

echo "Starting Worker..."
PYTHONPATH=src python -m worker.worker_app &
WORKER_PID=$!

echo "Services started:"
echo "  - Message Broker: PID $BROKER_PID (http://localhost:8082)"
echo "  - Backend (S3 Gateway): PID $BACKEND_PID (http://localhost:8080)"
echo "  - Haystack Node: PID $HAYSTACK_PID (http://localhost:8081)"
echo "  - Worker: PID $WORKER_PID (http://localhost:8083)"
echo ""
echo "Press Ctrl+C to stop all services"

trap "kill $BROKER_PID $BACKEND_PID $HAYSTACK_PID $WORKER_PID; echo 'Stopping services...'; exit" INT TERM

wait
