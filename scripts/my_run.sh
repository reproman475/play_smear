echo "Running migrations"
docker compose exec api python manage.py migrate

echo "Restarting django"
docker compose restart api

echo "Waiting for django to come back"
sleep 5

echo "Creating test user"
curl -X POST -H "Content-Type: application/json" -d '{"username": "test", "password": "test"}' http://localhost:8000/api/users/v1/
curl -X POST -H "Content-Type: application/json" -d '{"username": "test2", "password": "test2"}' http://localhost:8000/api/users/v1/

echo
echo "Success!"
