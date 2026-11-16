# Evaluación vocacional Hereford

Backend para aplicar y calificar el cuestionario de intereses vocacionales de
Hereford. El personal habilita el acceso, cada participante completa su
evaluación y el sistema calcula un puntaje interno por área. La API separa
la gestión del proceso, el acceso del participante y el cálculo.

## Índice

- [Evaluación vocacional Hereford](#evaluación-vocacional-hereford)
  - [Índice](#índice)
  - [Flujo de evaluación](#flujo-de-evaluación)
  - [Estructura del código](#estructura-del-código)
  - [Tecnologías y decisiones](#tecnologías-y-decisiones)
  - [Modelos y base de datos](#modelos-y-base-de-datos)
  - [Validación y calificación](#validación-y-calificación)
    - [Del JSON a PostgreSQL](#del-json-a-postgresql)
    - [Del puntaje al percentil](#del-puntaje-al-percentil)
  - [API y seguridad](#api-y-seguridad)
    - [Procesos y acceso](#procesos-y-acceso)
    - [Evaluaciones y resultados](#evaluaciones-y-resultados)
    - [Ejemplo de envío](#ejemplo-de-envío)
  - [Ejecutar en local](#ejecutar-en-local)
    - [Variables de entorno](#variables-de-entorno)
    - [uv](#uv)
    - [pip](#pip)
    - [Docker Compose](#docker-compose)
    - [Preparar una base local vacía](#preparar-una-base-local-vacía)
  - [Despliegue](#despliegue)

## Flujo de evaluación

1. **Abrir el proceso.** El gestor define la vigencia, las instrucciones y la
   versión del aviso. Elige un enlace compartible o invitaciones individuales.
2. **Habilitar la cuenta y asignar la evaluación.** En el proceso compartible,
   la persona se registra con un código y confirma su correo. Una invitación
   individual puede activarse con un enlace manual de un solo uso. La asignación
   vincula a la persona, el proceso y la evaluación.
3. **Responder.** El participante inicia sesión, elige una de sus asignaciones
   vigentes y recibe el número y el enunciado de las 90 preguntas. Responde
   en una escala de 1 a 5 y envía el cuestionario completo.
4. **Calificar.** Se calcula un puntaje directo por cada una de las nueve áreas.
   El backend registra qué catálogo y baremo usó en la conversión. El
   participante consulta si su envío se completó.

Los puntajes describen intereses y se consultan para orientación interna.

## Estructura del código

```text
hereford/
|-- manage.py
|-- hereford/                 # Configuracion y entrada del servidor
|   |-- asgi.py               # Aplicacion que ejecuta Uvicorn
|   |-- settings.py           # Configuracion base
|   |-- settings_container.py
|   |-- settings_production.py
|   |-- urls.py
|   |-- api_urls.py           # Registro de rutas de la API
|   `-- health.py             # Sondas del servidor y de PostgreSQL
|-- cuestionario/
|   |-- models.py             # Catalogo, respuestas, baremos y resultados
|   |-- calificacion.py       # Puntajes, conversion y huella del catalogo
|   |-- psicometria.py        # Reglas de conversion del baremo
|   |-- catalogo_cache.py     # Cache de textos de preguntas
|   |-- selectors.py          # Consultas del catalogo y las evaluaciones
|   |-- pagination.py         # Paginacion del catalogo interno de preguntas
|   |-- serializers.py        # Validacion de las 90 respuestas
|   |-- services.py           # Envio y calificacion en una transaccion
|   |-- permissions.py        # Permisos de modelo de la API interna
|   |-- views.py              # API interna de evaluaciones y resultados
|   |-- management/           # Verificacion del catalogo
|   |   `-- commands/
|   |       `-- verificar_catalogo_hereford.py
|   `-- migrations/
`-- accesos/
    |-- admin.py              # Gestion desde el panel de Django
    |-- backends.py           # Autenticacion por correo
    |-- enlaces.py            # Construccion de enlaces de acceso
    |-- middleware.py        # Cabeceras de las respuestas de API
    |-- models.py             # Procesos, invitaciones y asignaciones
    |-- permissions.py        # Permisos de gestores y participantes
    |-- serializers.py
    |-- services.py           # Activacion, asignacion y envio del participante
    |-- throttles.py          # Limites de peticiones
    |-- urls.py
    |-- views.py              # Acceso y evaluaciones asignadas
    |-- management/
    `-- migrations/
```

## Tecnologías y decisiones

El backend usa Python 3.14. Las versiones de paquetes vienen de `uv.lock`.

| Tecnología            | Versión                                  | Por qué se usa                                                                                         |
| --------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Django                | 6.1.2                                    | Reúne el ORM, las migraciones y el panel que usa el personal para gestionar procesos.                  |
| Django REST Framework | 3.18.3                                   | Aplica validación y permisos en las rutas HTTP mediante serializers y vistas.                          |
| Simple JWT            | 5.5.1                                    | Emite tokens de acceso y renovación para las sesiones de la API.                                       |
| PostgreSQL y psycopg  | PostgreSQL 17 en Compose, psycopg 3.3.6  | Guardan el catálogo y las evaluaciones con relaciones, restricciones y transacciones.                  |
| Redis                 | Redis 8 en Compose, cliente Python 8.1.0 | Cachea número y enunciado durante 60 segundos. Si la caché falla, la API lee los textos de PostgreSQL. |
| Uvicorn               | 0.54.0                                   | Ejecuta la aplicación ASGI de Django.                                                                  |
| WhiteNoise            | 6.12.0                                   | Sirve los archivos estáticos del panel dentro del contenedor.                                          |
| Docker Compose        | —                                        | Levanta la misma imagen del backend junto a PostgreSQL y Redis en local.                               |
| uv y pip              | —                                        | El lock fija las dependencias y `requirements.txt` permite instalarlas con pip y comprobar sus hashes. |

## Modelos y base de datos

| Modelo                        | Tabla                              | Relación o regla                                                                                                                          |
| ----------------------------- | ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `ProcesoEvaluacion`           | `procesos_evaluacion`              | Define modalidad y vigencia. El fin debe ser posterior al inicio.                                                                         |
| `IdentidadAcceso`             | `identidades_acceso`               | Enlaza una cuenta de Django con la identidad de acceso y, para participantes, con su ficha. El correo es único sin distinguir mayúsculas. |
| `Invitacion`                  | `invitaciones_evaluacion`          | Pertenece a un proceso y a un destinatario. PostgreSQL restringe la combinación de proceso y correo.                                      |
| `AsignacionEvaluacion`        | `asignaciones_evaluacion`          | Une proceso e identidad con una evaluación. Hay una asignación por par de proceso e identidad.                                            |
| `AreaVocacional` y `Pregunta` | `areas_vocacionales` y `preguntas` | Cada pregunta pertenece a un área y usa su número como clave.                                                                             |
| `Baremo` y `PuntoBaremo`      | `baremos` y `puntos_baremo`        | Hay un baremo vigente por área y grupo. Sus puntos asocian umbrales directos con percentiles.                                             |
| `Postulante` y `Evaluacion`   | `postulantes` y `evaluaciones`     | Una ficha puede tener varias evaluaciones. Cada evaluación registra su estado de envío.                                                   |
| `Respuesta`                   | `respuestas`                       | Cada combinación de evaluación y pregunta es única.                                                                                       |
| `ResultadoArea`               | `resultados_area`                  | Guarda un puntaje directo por área y el percentil cuando corresponde.                                                                     |
| `RegistroCalificacion`        | `registros_calificacion`           | Guarda la instantánea del catálogo, su huella SHA-256, el grupo de baremo y el algoritmo usados.                                          |

## Validación y calificación

### Del JSON a PostgreSQL

El cuerpo del envío contiene `respuestas`. Cada elemento tiene `pregunta`
y `valor`. `EnviarRespuestasSerializer` exige los 90 números de pregunta
sin repetir y un entero de 1 a 5 por pregunta.

La vista de `accesos/views.py` busca la asignación del usuario. El servicio
confirma que sigue activa y que el proceso está vigente. Luego
`cuestionario/services.py` bloquea la fila de la evaluación con
`select_for_update()`, guarda las respuestas y calcula los resultados.
La transacción incluye el cambio a completado. Una segunda entrega de una
evaluación completada recibe HTTP 409.

### Del puntaje al percentil

1. Se suman diez respuestas por área para obtener un puntaje directo de 10 a 50.
2. Se selecciona el baremo vigente por área y grupo. Se usa el umbral exacto o
   el siguiente superior de esa tabla. Si el puntaje supera su máximo, se usa
   el valor de salida configurado en el baremo.
3. Si la tabla está marcada para revisión, se conserva el puntaje directo y
   el percentil queda pendiente. La instantánea guarda la conversión y el
   catálogo aplicado para poder consultar el cálculo histórico.

## API y seguridad

### Procesos y acceso

| Método y ruta                          | Quién la usa y para qué                                         |
| -------------------------------------- | --------------------------------------------------------------- |
| `GET /api/procesos/{codigo}/`          | Cualquier visitante consulta el proceso y su aviso.             |
| `POST /api/admin/procesos/`            | El gestor autorizado crea un proceso.                           |
| `POST /api/admin/invitaciones/enlace/` | El gestor genera una invitación individual para compartirla.    |
| `POST /api/auth/registro/`             | La persona solicita el registro en un proceso compartible.      |
| `POST /api/auth/verificar-correo/`     | La persona confirma su correo mediante el token recibido.       |
| `POST /api/auth/activar/`              | La persona activa su cuenta con una invitación individual.      |
| `POST /api/auth/login/`                | La persona inicia sesión por correo y obtiene tokens JWT.       |
| `POST /api/auth/refresh/`              | Quien posee un token de renovación válido obtiene un nuevo par. |
| `POST /api/auth/logout/`               | El usuario autenticado revoca su token de renovación.           |

### Evaluaciones y resultados

| Método y ruta                                         | Quién la usa y para qué                                                                                                 |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `GET /api/mis-evaluaciones/`                          | El participante autenticado lista sus asignaciones.                                                                     |
| `GET /api/mis-evaluaciones/{asignacion}/preguntas/`   | El participante obtiene los textos de su evaluación.                                                                    |
| `GET /api/preguntas/?page=1&page_size=20`             | El personal autorizado consulta el catálogo ordenado por número. Devuelve 20 por defecto y admite hasta 100 por página. |
| `POST /api/mis-evaluaciones/{asignacion}/respuestas/` | El participante envía las 90 respuestas de su asignación.                                                               |
| `GET /api/mis-evaluaciones/{asignacion}/estado/`      | El participante comprueba si completó el envío.                                                                         |
| `GET /api/evaluaciones/{evaluacion}/resultados/`      | El personal con permiso consulta los resultados internos por área.                                                      |

El participante envía su token en `Authorization: Bearer`. El acceso JWT
dura 5 minutos y el token de renovación dura un día. Al renovar, el backend
revoca el token anterior. La API de gestión exige permisos de personal y
admite sesión de Django con CSRF o JWT según la ruta.

En las vistas que aplican el límite de acceso, PostgreSQL conserva el contador
en ventanas de 10 minutos. Se admiten 300 peticiones por IP y vista, y 10
por correo y vista cuando la petición incluye correo. En el ingreso web
de Render, la IP se toma de `CF-Connecting-IP`.

| HTTP | Caso en el flujo                                                         |
| ---- | ------------------------------------------------------------------------ |
| 400  | El envío tiene preguntas repetidas, faltantes o valores fuera de escala. |
| 401  | La ruta exige JWT y la petición carece de un token válido.               |
| 403  | El usuario autenticado carece del permiso requerido.                     |
| 404  | La asignación no aparece entre las del participante.                     |
| 409  | La evaluación ya fue completada o el proceso ya no admite el envío.      |
| 429  | Se agotó el cupo en una ruta que aplica límites.                         |

### Ejemplo de envío

Con el JWT del participante y el identificador de una asignación propia, estos
comandos generan un envío completo para una evaluación local de ejemplo.

```powershell
$asignacion = Read-Host 'ID de la asignación local'
$cuerpo = @{
    respuestas = @(1..90 | ForEach-Object { @{ pregunta = $_; valor = 3 } })
} | ConvertTo-Json -Depth 4
$cabeceras = @{ Authorization = "Bearer $env:HEREFORD_ACCESS_TOKEN" }
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8020/api/mis-evaluaciones/$asignacion/respuestas/" `
    -Headers $cabeceras -ContentType 'application/json' -Body $cuerpo
```

El ejemplo toma el token de `HEREFORD_ACCESS_TOKEN`. Si usas Compose,
cambia el puerto a `8023`. La API devuelve HTTP 201 al registrar el envío.

## Ejecutar en local

### Variables de entorno

| Variable                                                                                | Uso local                                                                                 |
| --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `DJANGO_SECRET_KEY`                                                                     | Clave de Django para firmas. Defínela para los tres modos de arranque.                    |
| `DJANGO_ALLOWED_HOSTS`                                                                  | Con uv o pip, incluye `127.0.0.1`. Compose ya configura los hosts locales.                |
| `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` | Con uv o pip, apuntan a PostgreSQL. Compose conecta al servicio `postgres`.               |
| `REDIS_URL`                                                                             | Con uv o pip, configura la caché si tienes Redis. Compose la conecta al servicio `redis`. |
| `DOCKER_POSTGRES_PASSWORD`                                                              | Contraseña que Compose asigna al PostgreSQL local.                                        |

### uv

Usa Python 3.14 y un servidor PostgreSQL disponible.

```powershell
uv sync --locked --no-dev
uv run --no-dev uvicorn hereford.asgi:application --app-dir hereford --host 127.0.0.1 --port 8020
```

### pip

Ejecuta los comandos con Python 3.14.

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn hereford.asgi:application --app-dir hereford --host 127.0.0.1 --port 8000
```

Con uv o pip, la API queda en `http://127.0.0.1:8000/`.

### Docker Compose

Para un entorno local con el catálogo cargado, levanta los tres servicios.

```powershell
docker compose up -d --build --wait
```

Compose levanta la API en `http://127.0.0.1:8023/` junto con PostgreSQL y Redis.

### Preparar una base local vacía

Aplica las migraciones antes de arrancar la API para usar el cuestionario.
Usa el comando que corresponda al entorno que instalaste.

| Entorno | Comando de migración                                                          |
| ------- | ----------------------------------------------------------------------------- |
| uv      | `uv run --no-dev python hereford/manage.py migrate --noinput`                 |
| pip     | `.\venv\Scripts\python.exe hereford/manage.py migrate --noinput`              |
| Docker  | `docker compose run --rm backend python hereford/manage.py migrate --noinput` |

Para preparar Docker por primera vez, ejecuta
`docker compose build backend` y `docker compose up -d --wait postgres redis`
antes de migrar.

Usa un respaldo en formato custom de una base Hereford con catálogo cargado.
Debe contener solo los datos de `areas_vocacionales`, `preguntas`, `baremos`
y `puntos_baremo`. Revisa su listado y restaura en la base local recién
migrada dentro de una sola transacción.

Con uv o pip, usa los clientes de PostgreSQL en el equipo.

```powershell
$catalogo = Read-Host 'Ruta al respaldo local del catálogo'
pg_restore --list $catalogo
pg_restore -h $env:DATABASE_HOST -p $env:DATABASE_PORT -U $env:DATABASE_USER -d $env:DATABASE_NAME -W `
    --single-transaction --no-owner --no-privileges $catalogo
```

Con Compose, copia el respaldo al contenedor de PostgreSQL.

```powershell
$catalogo = Read-Host 'Ruta al respaldo local del catálogo'
docker compose cp $catalogo postgres:/tmp/hereford-catalogo.dump
docker compose exec -T postgres pg_restore --list /tmp/hereford-catalogo.dump
docker compose exec -T postgres pg_restore -U hereford -d hereford_container `
    --single-transaction --no-owner --no-privileges /tmp/hereford-catalogo.dump
```

Con el mismo lanzador que usaste para migrar, ejecuta
`verificar_catalogo_hereford` en lugar de `migrate --noinput`. El catálogo
vigente contiene 9 áreas, 90 preguntas, 18 baremos y 234 umbrales.

## Despliegue

El Blueprint de Render ejecuta la imagen Docker y conecta Key Value para la
caché. Neon aloja PostgreSQL. Django usa TLS con `PGSSLMODE=verify-full` y
`PGCHANNELBINDING=require`. El perfil de producción exige un host permitido
explícito, desactiva DEBUG y sirve la API por HTTPS detrás del proxy.

| Sonda                | Qué comprueba                                                  |
| -------------------- | -------------------------------------------------------------- |
| `GET /health/live/`  | Django responde. Render la usa para comprobar el servicio web. |
| `GET /health/ready/` | Django puede ejecutar `SELECT 1` en PostgreSQL.                |
