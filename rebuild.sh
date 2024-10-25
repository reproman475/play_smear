docker compose down
docker compose build
docker compose up -d
echo "Sleeping 10 for server boot"
sleep 10
./scripts/my_run.sh
