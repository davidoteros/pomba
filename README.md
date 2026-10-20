# Pomba

**Pomba** es una plataforma web de almacenamiento personal de ficheros, diseñada como alternativa libre y privada a servicios como Google Drive o Dropbox. Permite a los usuarios guardar, organizar y gestionar sus documentos, imágenes y archivos de audio desde el navegador, sin depender de terceros que puedan hacer uso de sus datos.

El sistema ofrece autenticación segura con JWT, gestión de ficheros en carpetas, previsualización de contenido (PDF, imágenes y audio) y un motor de búsqueda basado en Elasticsearch que permite localizar archivos por nombre, tipo o metadatos. El almacenamiento se realiza mediante **Garage**, un sistema compatible con el protocolo S3.

Una de las funcionalidades más destacadas es el **control de versiones de ficheros de audio**, orientado a músicos, que permite comparar y recuperar versiones previas de cualquier canción o proyecto musical.

Toda la aplicación se ejecuta en Docker y tiene una arquitectura desacoplada: backend en **Django REST Framework**, frontend en **Vue.js 3**, base de datos **PostgreSQL**, búsqueda con **Elasticsearch** y almacenamiento de objetos con **Garage**.

---

## Capturas de pantalla

![Login](screenshots/login.png)

![Explorador de archivos](screenshots/explorador.png)

---

## Instalación / Puesta en marcha

### Requisitos previos

- Docker y Docker Compose
- `make`
- Python 3.12+

### Pasos

**1. Clonar el repositorio**

```bash
git clone https://github.com/davidoteros/pomba.git
cd pomba/app
```

**2. Configurar las variables de entorno**

Copia el fichero de ejemplo y completa los valores:

```bash
cp Docker/.env.example Docker/.env.development
```

Los campos obligatorios son:

| Variable | Descripción |
|---|---|
| `DJANGO_SECRET_KEY` | Clave secreta de Django |
| `POSTGRES_DB` | Nombre de la base de datos |
| `POSTGRES_USER` | Usuario de PostgreSQL |
| `POSTGRES_PASSWORD` | Contraseña de PostgreSQL |
| `GARAGE_RPC_SECRET` | Secreto RPC de Garage (cadena hexadecimal de 64 caracteres) |

Las claves `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY` las rellena automáticamente `make setup-garage` en el paso 5.

Para generar `GARAGE_RPC_SECRET` puedes usar:

```bash
openssl rand -hex 32
```

**3. Configurar Garage**

Copia el ejemplo de configuración y pega en `rpc_secret` el mismo valor que pusiste en `GARAGE_RPC_SECRET`:

```bash
cp Docker/garage.toml.example Docker/garage.toml
```

Este fichero debe existir antes de levantar los servicios.

**4. Levantar los servicios**

```bash
make up
```

Esto levanta todos los contenedores (Nginx, Django, Vue, PostgreSQL, Garage, Elasticsearch, Kibana) y crea un entorno virtual local de Python con las dependencias.

**5. Inicializar el almacenamiento (Garage)**

```bash
make setup-garage
```

El script crea el layout, el bucket `pomba-app` y la clave `django-app`, guarda las claves en `Docker/.env.development` y recrea el backend para que las lea. Si prefieres hacerlo a mano, consulta [Configuración manual de Garage](#configuración-manual-de-garage).

**6. Crear un superusuario (opcional, para el admin de Django)**

```bash
make createsuperuser
```

---

## Configuración manual de Garage

[Garage](https://garagehq.deuxfleurs.fr/) es un sistema de almacenamiento de objetos compatible con S3, ligero e ideal para ser autoalojado. A continuación se explica paso a paso lo que hace `make setup-garage`, por si quieres entenderlo o repetirlo a mano.

Requisito: haber copiado `Docker/garage.toml` y tener `rpc_secret` igual a `GARAGE_RPC_SECRET` (paso 3 de la instalación).

### 1. Levantar solo Garage

Si ya has ejecutado `make up`, saltate este paso.

```bash
docker compose --env-file Docker/.env.development -f Docker/docker-compose.yml up -d garage
```

### 2. Ver el estado del clúster

```bash
docker exec -it garage /garage status
```

### 3. Obtener el ID del nodo

```bash
docker exec -it garage /garage node id
```

La última línea de la salida tiene la forma `<ID>@garage:3901`, donde el ID son 64 caracteres hexadecimales. Copia solo el ID, es decir, lo que va antes de la `@`.

### 4. Asignar el layout al nodo

```bash
docker exec -it garage /garage layout assign -z dc1 -c 1G <NODE_ID>
```

- `-z dc1` → zona del centro de datos (puede ser cualquier nombre)
- `-c 1G` → capacidad asignada al nodo
- `<NODE_ID>` → sustitúyelo por el ID obtenido en el paso anterior

### 5. Aplicar el layout

```bash
docker exec -it garage /garage layout apply --version 1
```

### 6. Crear el bucket

```bash
docker exec -it garage /garage bucket create pomba-app
```

### 7. Crear una clave de acceso

```bash
docker exec -it garage /garage key create django-app
```

La salida mostrará los valores de `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY`. Cópialos en tu `.env.development`:

```env
AWS_ACCESS_KEY_ID=GKxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 8. Dar permisos a la clave sobre el bucket

```bash
docker exec -it garage /garage bucket allow --read --write pomba-app --key django-app
```

### 9. Verificar

```bash
docker exec -it garage /garage bucket list
docker exec -it garage /garage key list
```

### 10. Recrear el backend

El backend solo lee las variables de entorno al crearse, así que hay que recrearlo para que use las claves nuevas:

```bash
docker compose --env-file Docker/.env.development -f Docker/docker-compose.yml up -d --force-recreate --no-deps backend
```

---

## Uso

La aplicación está accesible en:

| Servicio | URL |
|---|---|
| Aplicación web | [pomba.me](https://pomba.me) |
| API Swagger | [pomba.me/api/schema/swagger/](https://pomba.me/api/schema/swagger/) |

En local (modo desarrollo):

| Servicio | URL |
|---|---|
| Aplicación web | `http://localhost` |
| API Swagger | `http://localhost/api/schema/swagger/` |
| Admin de Django | `http://localhost/admin/` |
| Kibana (Elasticsearch) | `http://localhost:5601` |

### Comandos útiles

Todos se ejecutan desde la carpeta `app/`.

**Desarrollo**

```bash
make up          # Levanta todos los servicios
make down        # Para todos los servicios
make build       # Reconstruye las imágenes de Docker
make clean       # Elimina contenedores y volúmenes (borra los datos)
```

**Producción**

```bash
make up-prod     # Levanta el stack de producción
make down-prod   # Para el stack de producción
make build-prod  # Construye las imágenes de producción
make clean-prod  # Elimina contenedores y volúmenes de producción
```

**Otros**

```bash
make setup-garage     # Inicializa Garage (layout, bucket y claves)
make status           # Muestra el estado del clúster Garage
make bash             # Abre una terminal en el contenedor del backend
make migrate          # Crea y aplica las migraciones
make logs             # Sigue los logs del backend
make createsuperuser  # Crea un superusuario para el admin de Django
make start-app NAME=<nombre>  # Crea una nueva app de Django
```

---

## Sobre el autor

Soy David Otero, estudiante de Desarrollo de Aplicaciones Web en el IES San Clemente (Santiago de Compostela). Tengo especial interés en el desarrollo backend, la privacidad digital y el software libre.

Elegí este proyecto porque quería construir algo con utilidad real: una alternativa a Google Drive que cualquier persona pueda autoalojar en su propio servidor, sin ceder sus datos a terceros ni depender de plataformas privativas. La creciente preocupación por la privacidad y por el uso que las grandes empresas hacen de los datos de los usuarios fue el principal motivo para desarrollar Pomba.

Puedes contactar conmigo en: **doterosouto@gmail.com**

---

## Licencia

Este proyecto está licenciado bajo la [GNU General Public License v3.0](LICENSE).

Puedes usar, modificar y distribuir este software libremente, siempre que las versiones derivadas mantengan la misma licencia y el código fuente permanezca accesible. Consulta el fichero [LICENSE](LICENSE) para más detalles.

---

## Guía de contribución

Las contribuciones son bienvenidas. Si quieres colaborar:

1. Haz un *fork* del repositorio.
2. Crea una rama nueva para tu funcionalidad: `git checkout -b feature/nueva-funcionalidad`.
3. Haz tus cambios y súbelos con mensajes descriptivos.
4. Abre un *pull request* describiendo qué has hecho y por qué.

Algunas áreas donde se puede contribuir:

- Nuevas funcionalidades (compartir ficheros entre usuarios, editor Markdown...)
- Mejoras de rendimiento o seguridad
- Tests automatizados
- Traducciones de la interfaz
