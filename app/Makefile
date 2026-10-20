# Makefile de Pomba: atajos de desarrollo y producción

up:
	@echo "🚀 Levantando servicios de Docker..."
	docker compose --env-file "Docker/.env.development" -f "Docker/docker-compose.yml" up -d --wait
	@echo "🐍 Preparando entorno local de Python..."
	@chmod +x local_setup.sh
	@./local_setup.sh

down:
	@echo "🛑 Parando servicios..."
	docker compose -f "Docker/docker-compose.yml" down

build:
	@echo "🛠️ Reconstruyendo imágenes de Docker..."
	docker compose -f Docker/docker-compose.yml build --no-cache

clean:
	@echo "🧹 Limpieza profunda: borrando contenedores y volúmenes..."
	docker compose -f Docker/docker-compose.yml down -v


up-prod:
	@echo "🚀 Levantando stack de producción..."
	docker compose --env-file "Docker/.env.prod" -f "Docker/docker-compose.prod.yml" up -d --wait

down-prod:
	@echo "🛑 Parando producción..."
	docker compose -f "Docker/docker-compose.prod.yml" down

build-prod:
	@echo "🛠️ Construyendo imágenes de producción..."
	docker compose -f Docker/docker-compose.prod.yml build --no-cache

clean-prod:
	@echo "🧹 Borrando contenedores y volúmenes de producción..."
	docker compose -f Docker/docker-compose.prod.yml down -v


# Configura Garage (layout, bucket y clave) y recrea el backend para que lea las nuevas claves
setup-garage:
	@chmod +x scripts/setup_infrastructure.sh
	@./scripts/setup_infrastructure.sh
	docker compose --env-file "Docker/.env.development" -f "Docker/docker-compose.yml" up -d --force-recreate --no-deps backend

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
