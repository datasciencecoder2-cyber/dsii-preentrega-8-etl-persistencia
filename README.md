# Data Science II — Pre-entrega 8

## Persistencia e integración de scripts ETL (CSV → SQLite)

**Objetivo:** automatizar un proceso de **extracción, transformación y carga** que parte de transacciones de ventas simuladas en CSV y mantiene una tabla analítica persistente en SQLite, sin duplicar datos entre ejecuciones.

El conjunto de ejemplo es **100 % sintético** y se entrega para que cualquier persona pueda reproducir la práctica sin descargar nada ni disponer de credenciales. No son datos reales de clientes.

## Requisitos

- **Python 3.10 o superior**, con SQLite incorporado (módulo `sqlite3`).
- No se necesitan paquetes externos: `requirements.txt` lo deja expresamente documentado.
- Windows, macOS o Linux. Comandos ilustrados con `py` en Windows; si no existe, utilizar `python` o `python3`.

## Estructura del proyecto

```text
.
├── main.py                         # Orquestación y línea de comandos
├── schema.sql                      # DDL, clave primaria, validaciones, índice y vista
├── requirements.txt                # Solo biblioteca estándar
├── .gitignore                      # No versionar SQLite ni temporales de Python
├── datos/
│   └── ventas_transaccionales.csv  # Datos de entrada sintéticos
├── src/
│   ├── extraer.py                  # Lectura CSV con control de encabezado
│   ├── transformar.py              # Tipos, estados, nulos, montos y duplicados
│   ├── cargar.py                   # UPSERT, transacción y rollback
│   └── pipeline.py                 # Orquestación y reporte JSON atómico
├── tests/
│   └── test_pipeline.py            # 21 pruebas con unittest
└── evidencia/
    └── resultados_ejecucion.txt    # Corridas comprobadas sobre una copia limpia
```

Se genera localmente `salidas/analytics.db` y `salidas/reporte_etl.json`. Ambos están **ignorados por Git**, dado que pueden regenerarse con el script.

## Pasos para ejecutar

1. Clonar o descargar el repositorio; abrir una terminal en la carpeta del proyecto.
2. Ejecutar el pipeline:

   ```powershell
   py main.py
   ```

3. Ejecutarlo de nuevo, para comprobar la idempotencia:

   ```powershell
   py main.py
   ```

4. Ejecutar las pruebas:

   ```powershell
   py -m unittest discover -s tests -v
   ```

5. Opcional: utilizar otras rutas de archivo (sin editar código):

   ```powershell
   py main.py --origen datos/ventas_transaccionales.csv --db salidas/otro_destino.db --reporte salidas/otro_reporte.json
   ```

El programa **termina con código de error y un mensaje claro** si falta el CSV/DDL, hay columnas obligatorias ausentes, aparecen IDs contradictorios o SQLite no puede escribir. La carga DML usa una transacción que hace **ROLLBACK** ante fallos; un test lo comprueba.

## Cómo funciona el ETL

| Etapa | Qué hace | Archivo |
|---|---|---|
| E — Extracción | Lee CSV UTF-8 (también BOM) y valida columnas | `src/extraer.py` |
| T — Transformación | Verifica tipos, fechas ISO, categorías, montos, estados y duplicados | `src/transformar.py` |
| L — Carga | Crea el esquema (`schema.sql`), inserta/corrige por PK, valida con SQLite | `src/cargar.py` |
| Reporte | Escribe JSON al finalizar; nunca reporta éxito de una carga fallida | `src/pipeline.py` |

### Reglas de negocio y calidad

- Solo se incorporan transacciones con estado **confirmada**. Las canceladas y pendientes se cuentan pero no se cargan.
- Registros con fecha inválida, producto vacío, cantidad no positiva, precio inválido o categoría desconocida se descartan y quedan en el reporte de calidad con su número de fila y motivo.
- `id_venta` es el identificador único. Si el CSV repite una fila idéntica se ignora; si repite un ID con **datos incompatibles**, el proceso se detiene antes de escribir en SQLite.
- Las categorías se estandarizan: `Alimentos`, `Hogar`, `Tecnologia` (acepta `Tecnología`).
- `precio_unitario_centavos` y `total_centavos` usan enteros, calculados mediante `Decimal` para evitar diferencias de redondeo con `float`.
- SQLite aplica `PRIMARY KEY`, `NOT NULL`, `CHECK` y un índice `(mes,categoria)`. El DDL está en `schema.sql`.
- La carga es **idempotente** gracias a `ON CONFLICT(id_venta) DO UPDATE`, que solo actualiza una fila cuando los datos cambiaron: ejecutar dos veces no crea ventas duplicadas. Si el origen corrige una venta anterior, también se actualiza la fila analítica existente.
- El reporte incluye rechazos y un resumen agregado por mes/categoría consultando la **vista** `resumen_mensual`.

## Hallazgos y verificación

En la muestra sintética incluida:

| Métrica | Resultado esperado |
|---|---:|
| Filas de entrada | 39 |
| Duplicados exactos | 2 |
| Pedidos cancelados/pendientes | 3 |
| Filas inválidas descartadas | 4 |
| Ventas confirmadas válidas | **30** |
| Nuevas filas en la primera ejecución | 30 |
| Nuevas filas en la segunda ejecución | **0** |
| Pruebas de automatización | **21/21 OK** |

Los resultados de referencia del comando y de las pruebas están en `evidencia/resultados_ejecucion.txt`. No se afirma rendimiento de grandes volúmenes: el propósito es demostrar el patrón ETL y persistencia segura sobre una muestra pequeña.

### Por qué SQLite

SQLite permite persistencia durable en un solo archivo local, SQL estándar para consultas y un esquema auditable, sin servidor ni claves privadas. En proyectos mayores, la misma separación de etapas facilita sustituir la capa de carga por PostgreSQL u otro destino.

## Publicación incremental en GitHub

Para que el historial refleje **desarrollo incremental y descriptivo**, publicar por grupos de archivos, cada uno con su propio commit (la plantilla Python de `.gitignore` se puede crear al iniciar el repositorio):

1. **Commit 1 —** `docs: iniciar repositorio y describir objetivo ETL` — `.gitignore`, `README.md`, `requirements.txt`.
2. **Commit 2 —** `feat: agregar origen transaccional y esquema SQLite` — `datos/ventas_transaccionales.csv`, `schema.sql`.
3. **Commit 3 —** `feat: implementar pipeline ETL idempotente y transaccional` — `main.py` y carpeta `src/`.
4. **Commit 4 —** `test: agregar validaciones automatizadas y evidencia` — carpeta `tests/` y `evidencia/`.

No versionar `salidas/analytics.db`, archivos temporales, entornos virtuales ni `__pycache__`. **`CREATE TABLE IF NOT EXISTS` solo evita recrear la tabla; la no duplicación de registros la garantiza la PK más el UPSERT.**
