.PHONY: install dev-mobile dev-api dev test-db

install:
	cd apps/mobile && npm install
	cd apps/api && python3 -m pip install -r requirements.txt

dev-mobile:
	cd apps/mobile && npx expo start

dev-api:
	cd apps/api && source venv/bin/activate && uvicorn main:app --reload

dev:
	make -j 2 dev-mobile dev-api

# Integration tests against a throwaway PostGIS (same setup as CI).
test-db:
	docker rm -f curbsense-testdb >/dev/null 2>&1 || true
	docker run -d --name curbsense-testdb -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=curbsense -p 55432:5432 postgis/postgis:16-3.4
	until docker exec curbsense-testdb pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done; sleep 2
	PGPASSWORD=postgres psql -h localhost -p 55432 -U postgres -d curbsense -v ON_ERROR_STOP=1 -q -f apps/api/tests/sql/supabase_shim.sql
	for f in supabase/migrations/*.sql; do PGPASSWORD=postgres psql -h localhost -p 55432 -U postgres -d curbsense -v ON_ERROR_STOP=1 -q -f $$f; done
	TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:55432/curbsense pytest; status=$$?; docker rm -f curbsense-testdb >/dev/null; exit $$status
