# Makefile de Pomba: atajos de desarrollo y producción

DC = docker compose --env-file "Docker/.env.development" -f "Docker/docker-compose.yml"
DC_PROD = docker compose --env-file "Docker/.env.prod" -f "Docker/docker-compose.prod.yml"

up:
	@echo "🚀 Levantando servicios de Docker..."
	$(DC) up -d --wait
	@echo "🐍 Preparando entorno local de Python..."
	@chmod +x local_setup.sh
	@./local_setup.sh

down:
	@echo "🛑 Parando servicios..."
	$(DC) down

build:
	@echo "🛠️ Reconstruyendo imágenes de Docker..."
	$(DC) build --no-cache

clean:
	@echo "🧹 Limpieza profunda: borrando contenedores y volúmenes..."
	$(DC) down -v


up-prod:
	@echo "🚀 Levantando stack de producción..."
	$(DC_PROD) up -d --wait

down-prod:
	@echo "🛑 Parando producción..."
	$(DC_PROD) down

build-prod:
	@echo "🛠️ Construyendo imágenes de producción..."
	$(DC_PROD) build --no-cache

clean-prod:
	@echo "🧹 Borrando contenedores y volúmenes de producción..."
	$(DC_PROD) down -v


# Configura Garage (layout, bucket y clave) y recrea el backend para que lea las nuevas claves
setup-garage:
	@chmod +x scripts/setup_infrastructure.sh
	@./scripts/setup_infrastructure.sh
	$(DC) up -d --force-recreate --no-deps backend

status:
	@docker exec garage /garage status

start-app:
	docker exec -it django_backend python manage.py startapp $(NAME)

# --- Atajos de desarrollo (contenedor del backend) ---
bash:
	docker exec -it django_backend bash

migrate:
	docker exec -it django_backend python manage.py makemigrations
	docker exec -it django_backend python manage.py migrate

logs:
	docker logs -f django_backend

createsuperuser:
	docker exec -it django_backend python manage.py createsuperuser
