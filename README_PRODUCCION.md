# Cotyland - integración controlada de producción

Esta entrega corresponde exclusivamente a la aplicación Streamlit de etiquetas y comparación de precios de Cotyland. Mantiene las tres pestañas, su interfaz general y las medidas Chica, Mediana y Gigante.

## Diagnóstico de la pantalla negra

Los dos ZIP recibidos tienen exactamente el mismo SHA-256 (`F02F358096B386E3CF5A2B0A9576D970287EBB90139E023C4646B9D005D2B5AF`) y todos sus archivos internos son idénticos byte por byte. Por lo tanto, los adjuntos no contienen dos versiones diferentes que permitan atribuir la pantalla negra a un cambio específico entre ellas.

El log tampoco contiene un error de Python: finaliza en `Uvicorn server started on 0.0.0.0:8501`, antes de registrar un traceback o una caída. Esto prueba que el servidor inició; no prueba que el navegador haya completado una sesión de Streamlit.

Sí se encontró un riesgo concreto en el código base: `download_products(URL_DRIVE)` se ejecutaba durante el render inicial. Streamlit no envía la interfaz completa hasta terminar la ejecución del script, de modo que una respuesta lenta o bloqueada de Google podía dejar la pantalla esperando sin traceback. En esta entrega no se realiza ninguna request durante el arranque: Google Sheets se carga al primer escaneo o al pulsar Comparar, y Apps Script se consulta únicamente al pulsar Comparar o Confirmar seguimiento.

## Procedencia de los archivos

- Base funcional: cualquiera de los dos ZIP adjuntos, porque son idénticos.
- `app.py`: estructura, tres pestañas, widgets y flujo base del ZIP funcional; se agregaron de forma selectiva red diferida, impresión directa, cruce de código y seguimiento.
- `cotyland_core.py`: motores PDF, escáner y comparador del ZIP funcional; se agregaron `Codigo_Impresion`, acceso seguro a seguimiento y ajuste de descripción.
- `Codigo.gs`: tomado de `CODEGS.txt`, con deduplicación adicional por `IdArticulo` o código.
- `requirements.txt` y `runtime.txt`: sin cambios respecto del ZIP funcional.
- `viejo.csv` y `nuevo.csv`: usados solamente para las pruebas exactas; no se incluyen en el ZIP final.

## Comportamiento de red y secretos

La aplicación abre y muestra título y tres pestañas cuando:

- `APPS_SCRIPT_URL` no existe;
- contiene una URL válida;
- contiene una URL inválida;
- la conexión produce timeout.

Todas las requests tienen timeout. Un fallo de Google o Apps Script se transforma en warning y no derriba la aplicación. `APPS_SCRIPT_URL` se lee exclusivamente desde `st.secrets`.

## Comparador y Codigo_Impresion

El comparador sigue cruzando por `IdArticulo` y lee solo los índices 9, 10, 11 y 14. Después de obtener los cambios, cruza por `IdArticulo` contra la base `CONSULTA_CORREGIDO.CSV` publicada en Google Sheets:

1. `Codigo_Impresion = Codigo_Barra` recuperado de Google.
2. Si el producto no existe o `Codigo_Barra` está vacío, usa `IdArticulo`.
3. Los PDF del Comparador imprimen `Codigo_Impresion` en el pie.

Los códigos permanecen como texto. No se eliminan puntos, guiones, letras, ceros iniciales ni espacios internos.

Resultado certificado con los CSV adjuntos, también en orden inverso:

- Coincidencias: **131037**
- Cambios: **294**
- Aumentos: **290**
- Bajas: **4**

## ETIQUETAS_SEGUIDAS

Al comparar, los productos guardados quedan seleccionados. **Confirmar seguimiento en Drive** reemplaza el seguimiento con la selección actual: agrega los nuevos, elimina los destildados y evita duplicados. No hay escrituras por escaneo.

Para habilitarlo:

1. Abrir Apps Script vinculado a la planilla.
2. Reemplazar su contenido por `Codigo.gs`.
3. Implementar como aplicación web.
4. Copiar la URL terminada en `/exec`.
5. Configurar en los secretos de Streamlit:

```toml
APPS_SCRIPT_URL = "https://script.google.com/macros/s/IDENTIFICADOR/exec"
```

Sin este secreto, todas las funciones salvo sincronización con Drive siguen disponibles.

## PDF e impresión directa

Los tres tamaños mantienen sus medidas. La descripción permanece en la zona superior, reduce fuente o limita líneas cuando es necesario, el precio conserva una posición central fija y solo reduce tamaño por ancho, y código/fecha quedan abajo.

Después de generar aparecen:

- **Descargar PDF**
- **Imprimir directamente**

La impresión reutiliza el PDF ya generado, lo sirve como archivo estático y no usa base64 ni `st.components.v1.html`. Si el navegador bloquea la ventana, muestra un aviso para habilitar pop-ups.

## Prueba local exacta

Copiar `viejo.csv` y `nuevo.csv` junto a `app.py`, abrir PowerShell y ejecutar:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
streamlit run app.py
```

Resultado esperado de esta entrega: `26 passed`.

## Publicación

1. Hacer copia de seguridad de la versión publicada.
2. Reemplazar completos `app.py`, `cotyland_core.py`, `Codigo.gs`, `requirements.txt`, `runtime.txt`, `pytest.ini`, `.streamlit/config.toml`, `static` y `tests` con los archivos del ZIP.
3. No subir credenciales JSON ni los CSV grandes.
4. Mantener `app.py` como archivo principal y Python 3.12.
5. Configurar opcionalmente `APPS_SCRIPT_URL`.
6. Reiniciar la aplicación y comprobar primero el título y las tres pestañas.

No se modifica ni publica GitHub automáticamente.
