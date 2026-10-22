import boto3
from botocore.client import Config
from storages.backends.s3 import S3Storage
from storages.utils import clean_name
from django.conf import settings

# Al generar URLs presignadas con S3Storage estándar, boto3 firma la URL
# usando el endpoint interno de Docker (http://garage:3900). 

# Ese hostname no es resoluble desde el navegador, y aunque lo fuera, la firma S3v4
# incluye el host — si el navegador accede con host=localhost:3900 la firma
# no coincide y Garage devuelve 403.
#
# Solución: sobreescribir url() para generar la URL presignada con un
# cliente boto3 apuntando al endpoint público (http://localhost:3900),
# de forma que la firma se calcula con el host correcto desde el principio.
# Django sigue usando el endpoint interno para subir y borrar archivos.

class GarageStorage(S3Storage):
    """
    Storage personalizado para Garage que genera URLs presignadas
    usando el endpoint PÚBLICO en lugar del endpoint interno de Docker.

    Problema sin esto:
      - Django usa http://garage:3900 (red interna Docker) para subir/bajar archivos
      - Pero boto3 también firma las URLs presignadas con host=garage:3900.
      - El navegador recibe esa URL, hace GET a localhost:3900 con host=localhost:3900,
        Garage recalcula la firma con ese host y no coinciden 403 Forbidden.

    Solución:
      - Para operaciones S3 (subida, borrado...) se sigue usando el endpoint interno.
      - Para GENERAR URLs presignadas se usa un cliente boto3 separado con el endpoint
        público (GARAGE_PUBLIC_URL), así la firma se calcula con el host correcto.
    """

    def url(self, name, parameters=None, expire=None, http_method=None):
        name = self._normalize_name(clean_name(name))

        if expire is None:
            expire = self.querystring_expire  # por defecto 3600 s

        public_endpoint = getattr(
            settings, 'GARAGE_PUBLIC_URL', settings.AWS_S3_ENDPOINT_URL
        )

        # Cliente independiente apuntando al endpoint público
        client = boto3.client(
            's3',
            endpoint_url=public_endpoint,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'garage'),
            config=Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'},
            ),
        )

        params = {'Bucket': self.bucket_name, 'Key': name}
        if parameters:
            params.update(parameters)

        return client.generate_presigned_url(
            'get_object',
            Params=params,
            ExpiresIn=expire,
            HttpMethod=http_method or 'GET',
        )
