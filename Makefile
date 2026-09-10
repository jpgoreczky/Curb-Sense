.PHONY: install dev-mobile dev-api dev

install:
	cd apps/mobile && npm install
	cd apps/api && python3 -m pip install -r requirements.txt

dev-mobile:
	cd apps/mobile && npx expo start

dev-api:
	cd apps/api && source venv/bin/activate && uvicorn main:app --reload

dev:
	make -j 2 dev-mobile dev-api