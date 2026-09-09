# Cargar notas USS

Aplicación web local para hacer calzar el listado de estudiantes de **MiPortal USS (Sistema Notas Docente)** con las calificaciones exportadas desde **Blackboard**. Genera un Excel con las notas en el mismo orden del listado de MiPortal y permite copiarlas al portapapeles para facilitar su traspaso.

El flujo se realiza con archivos exportados: la aplicación no inicia sesión ni carga notas automáticamente en las plataformas.

## Funcionalidades

- Lee archivos `.xls`, `.xlsx` y `.csv`, incluidos archivos de Blackboard con extensión `.xls` que contienen texto separado por tabulaciones.
- Detecta columnas de identificación y nombres a partir de sus encabezados.
- Permite elegir la evaluación de destino en MiPortal y la columna de nota de origen en Blackboard.
- Busca coincidencias por RUT/ID y por nombres, normalizando mayúsculas, tildes, separadores y el orden de las palabras.
- Conserva todas las columnas y el orden de las filas de MiPortal; reemplaza los valores de la evaluación seleccionada.
- Muestra el resultado y los estudiantes sin coincidencia en pantalla.
- Permite descargar el Excel, copiar las notas, reemplazar archivos y borrar los archivos de la sesión.

## Requisitos e instalación

Necesitas Python 3.10 o superior y `pip`. Las dependencias están declaradas en [requirements.txt](requirements.txt): Flask, pandas, openpyxl y xlrd.

Clona el repositorio y entra en la carpeta:

```bash
git clone https://github.com/ffelipev2/cargarNotasUSS.git
cd cargarNotasUSS
```

En Windows, desde PowerShell, crea un entorno virtual e instala las dependencias:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

En Linux o macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Abre **http://127.0.0.1:5000** en el navegador. Para detener la aplicación, presiona `Ctrl+C` en la terminal.

## Preparación de los archivos

### MiPortal USS / Sistema Notas Docente

Usa el listado del curso con al menos tres columnas. La disposición esperada es **N, Rut, Nombre**, seguida por las evaluaciones, por ejemplo **SOLEMNE 1**, **SOLEMNE 2**, **CONTROLES** y **NF**. Todas las columnas desde la cuarta aparecen como opciones de destino, incluidas las vacías. Se conservan sus encabezados y los datos de las columnas no seleccionadas.

Si el listado solo tiene las tres columnas de identificación, puedes seleccionar `nota (nueva columna)` como destino. El Excel generado conserva los datos tabulares; no conserva el formato del libro ni recalcula fórmulas como NF.

El nombre y el identificador se buscan entre esas tres columnas. Si no se reconoce un encabezado de nombre, se utiliza la tercera columna. Si no se detecta RUT/ID, el cruce se realiza por nombre.

### Blackboard / Archivo GC

Exporta el listado del mismo curso con los nombres y la calificación que deseas traspasar. Se reconocen nombres completos, como `Nombre completo` o `Student Name`, y columnas separadas, como `Nombre` y `Apellido`, o `First Name` y `Last Name`. El RUT/ID es opcional; se reconocen encabezados como `Rut`, `Student ID` e `ID de estudiante`.

La columna de nota se selecciona explícitamente después de cargar los archivos. Puedes mantener varias evaluaciones en la exportación y elegir la que corresponde. Las columnas reconocidas de nombre, identificación, usuario, correo, último acceso y disponibilidad se excluyen del selector. Las evaluaciones sin calificaciones también aparecen; sus valores vacíos siguen la regla de estudiantes sin coincidencia utilizable.

En Excel se lee la primera hoja y se utiliza la primera fila como encabezado. El límite de carga es de **16 MiB por solicitud**, considerando ambos archivos y los datos del formulario.

## Uso

1. Selecciona el listado de MiPortal en **Sistema Notas Docente**.
2. Selecciona la exportación de Blackboard en **Archivo GC / Notas Blackboard**.
3. Pulsa **Cargar columnas**. Este paso muestra las opciones y todavía no genera notas.
4. En **Evaluación de destino en MiPortal**, elige la columna que quieres completar. En **Nota de origen en Blackboard**, elige la evaluación correspondiente.
5. Pulsa **Procesar y generar archivo** y revisa la tabla, el número de coincidencias y el detalle de estudiantes sin coincidencia. La evaluación seleccionada queda resaltada y se muestra su columna de origen.
6. Usa **Descargar resultado** para obtener el `.xlsx`, o **Copiar notas** para copiar solo la evaluación seleccionada, con una nota por línea en el orden del listado. Las celdas de nota vacías se omiten al copiar.
7. Traspasa las notas a MiPortal después de verificar los resultados.

Por ejemplo, para Solemne 2, selecciona `SOLEMNE 2 (35%) 09-SEP-2026` como destino y la columna `U3 | S13 Solemne II [Puntos totales: 100 Escala Chilena]` de Blackboard como origen (puede incluir un emoji y un identificador en el encabezado). Las notas de Solemne 1 y Controles conservan sus valores.

Puedes cambiar las evaluaciones y reprocesar sin volver a cargar los archivos. Cada resultado se genera desde los archivos cargados originalmente. Si reemplazas un archivo, debes cargar sus columnas y volver a elegir origen y destino. Al cambiar una selección, se ocultan el resultado anterior y su descarga hasta volver a procesar. **Borrar archivo** elimina ese archivo y el resultado asociado; **Borrar todo** elimina ambos archivos cargados y el resultado de la sesión.

## Reglas del cruce

Para cada estudiante de MiPortal, se intenta encontrar un registro de Blackboard en este orden:

1. RUT/ID normalizado, sin signos ni espacios.
2. Solo los dígitos del RUT/ID.
3. Nombre completo normalizado, sin importar el orden de las palabras.
4. Nombre simplificado, omitiendo partículas como `de`, `del` o `la`.
5. Coincidencia parcial cuando las palabras de un nombre están contenidas en el otro, con al menos dos palabras en cada uno; se elige el candidato con más palabras compartidas.

Cada registro de Blackboard se usa una sola vez. Los registros sin nombre utilizable o sin calificación numérica se descartan. Los nombres duplicados o las coincidencias parciales pueden ser ambiguos: el algoritmo no solicita confirmación para resolverlos.

**Un estudiante sin coincidencia recibe `10` por defecto** y aparece en el detalle correspondiente. Ese valor no confirma que exista una nota en Blackboard. Las filas identificadas por el código como resumen o sin datos de estudiante se conservan con la nota vacía.

## Conversión de notas

La aplicación acepta coma o punto decimal, extrae el primer número del valor y aplica estas reglas:

- Si el número es menor o igual a `7`, lo multiplica por `10`.
- Redondea a un entero; los valores terminados en `.5` se redondean hacia arriba para notas positivas.
- Omite valores vacíos, `-`, `--` o sin número reconocible.

| Valor en Blackboard | Nota generada |
| --- | --- |
| `6,5` | `65` |
| `7.0` | `70` |
| `5.55` | `56` |
| `65` | `65` |
| `65.5` | `66` |

No se aplica una fórmula de conversión de puntajes o porcentajes a la escala chilena ni se valida un rango de notas. Por ejemplo, `85%` se interpreta como `85`. Usa una columna que ya contenga la calificación adecuada para este formato.

## Estructura y archivos generados

```text
cargarNotasUSS/
├── app.py                 # Servidor Flask, lectura, cruce y exportación
├── requirements.txt       # Dependencias de Python
├── templates/
│   └── index.html         # Interfaz de carga y resultados
├── static/
│   ├── app.js             # Selección de archivos y copia de notas
│   └── styles.css         # Estilos de la interfaz
├── uploads/               # Archivos cargados; se crea al ejecutar
│   ├── docente/
│   └── blackboard/
└── results/               # Excel generados y metadatos JSON
```

Los resultados se guardan como `AAAAMMDD_HHMMSS_notas_preparadas.xlsx`, junto con un archivo `.json` que contiene la tabla, el resumen y los casos sin coincidencia. No se necesita una base de datos.

Los archivos se almacenan en el equipo que ejecuta Flask. `uploads/` está excluido de Git; `results/` no lo está y puede contener nombres, RUT y calificaciones. Revisa su contenido antes de incluir nuevos resultados en un commit.

El arranque con `app.py` utiliza el servidor de desarrollo de Flask, con depuración activada y una clave de sesión fija en el código. Esta configuración está orientada al uso local.

## Pruebas

```bash
python -m unittest discover -s tests -v
```

Las pruebas usan datos ficticios y directorios temporales. Cubren la selección de evaluaciones, el orden del cruce, la conservación de otras columnas, los valores vacíos y el flujo de carga, descarga y reemplazo de archivos.

Si tienes Node.js, puedes comprobar también la lógica del formulario y la copia de notas con `node tests/test_app.js`.
