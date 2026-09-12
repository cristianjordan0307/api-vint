# Fix CORS — API VINT (FastAPI)

## Problema

La app móvil de VINT corre en **Flutter Web** y hace peticiones HTTP a `https://api-vint.onrender.com`. El navegador bloquea todas las peticiones con el error:

```
Access to XMLHttpRequest at 'https://api-vint.onrender.com/api/products'
from origin 'http://localhost:8080' has been blocked by CORS policy:
No 'Access-Control-Allow-Origin' header is present on the requested resource.
```

Esto afecta **todos los endpoints** de la API — GET, POST, PATCH, DELETE.

---

## Solución

Agregar el middleware de CORS de FastAPI en `main.py`.

### Paso 1 — Agregar el import

```python
from fastapi.middleware.cors import CORSMiddleware
```

### Paso 2 — Registrar el middleware

Agrega esto en `main.py` **antes** de registrar cualquier router:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",       # Flutter Web — desarrollo local
        "http://localhost:5000",       # por si el puerto varía
        "http://127.0.0.1:8080",
        # Agrega aquí el dominio de producción cuando lo tengas:
        # "https://app.vint.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
```

### Ejemplo de `main.py` completo (estructura mínima)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# ... otros imports ...

app = FastAPI()

# ── CORS ── debe ir ANTES de los routers ──────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(products.router)
app.include_router(vendedor.router)
# ... resto de routers ...
```

---

## Por qué es necesario el preflight OPTIONS

El navegador hace una petición `OPTIONS` automática antes de cada `POST`, `PATCH` o `DELETE` con headers personalizados (como `Authorization: Bearer ...`). FastAPI con `CORSMiddleware` responde correctamente a estas peticiones. Sin el middleware, el navegador rechaza la petición antes de que llegue al endpoint real.

---

## Verificación

Después de hacer el deploy, verifica con este comando:

```bash
curl -I -X OPTIONS "https://api-vint.onrender.com/api/products" \
  -H "Origin: http://localhost:8080" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization"
```

La respuesta debe incluir:

```
Access-Control-Allow-Origin: http://localhost:8080
Access-Control-Allow-Methods: GET, POST, PATCH, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: *
```

---

## Notas adicionales

- El middleware de CORS **no afecta la seguridad de los endpoints** — los tokens JWT siguen siendo requeridos y validados por el `get_current_user` dependency.
- En producción, reemplaza `allow_origins=["*"]` con la lista explícita de dominios permitidos.
- Si Render.com tiene alguna capa de proxy (nginx), asegúrate de que no esté sobreescribiendo los headers CORS.
