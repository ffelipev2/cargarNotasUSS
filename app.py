from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import pandas as pd
from flask import Flask, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
RESULT_DIR = BASE_DIR / "results"
UPLOAD_SLOTS = {
    "docente": {
        "label": "Sistema Notas Docente",
        "folder": UPLOAD_DIR / "docente",
        "session_key": "docente_file",
    },
    "blackboard": {
        "label": "Archivo GC / Notas Blackboard",
        "folder": UPLOAD_DIR / "blackboard",
        "session_key": "blackboard_file",
    },
}
ALLOWED_EXTENSIONS = {".xls", ".xlsx", ".csv"}
TEXT_TABLE_ENCODINGS = ("utf-16", "utf-16-le", "utf-8-sig", "utf-8", "latin-1")
DOCENTE_NAME_HINTS = ("nombre", "alumno", "estudiante", "student")
DOCENTE_ID_HINTS = ("rut", "id", "identificacion")
FULL_NAME_HINTS = (
    "nombre completo",
    "student name",
    "full name",
    "display name",
    "nombre y apellido",
)
BLACKBOARD_NAME_HINTS = (
    "nombre",
    "estudiante",
    "alumno",
)
BLACKBOARD_ID_HINTS = ("id de estudiante", "student id", "id estudiante", "rut")
FIRST_NAME_HINTS = ("first name", "given name", "nombre", "nombres")
LAST_NAME_HINTS = ("last name", "family name", "surname", "apellido", "apellidos")
GRADE_HINTS = ("nota", "calificacion", "grade", "score", "puntaje", "resultado", "promedio")
SUMMARY_ROW_HINTS = {"promedio", "desviacion", "desviacionestandar", "average", "median", "minimo", "maximo"}
IGNORE_NAME_TOKENS = {
    "de",
    "del",
    "la",
    "las",
    "los",
    "y",
    "da",
    "das",
    "do",
    "dos",
    "van",
    "von",
}


app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


class ProcessingError(Exception):
    pass


@dataclass
class BlackboardRecord:
    full_key: str
    simplified_key: str
    grade: int
    used: bool = False


@dataclass
class BlackboardIndexes:
    by_full_name: defaultdict[str, deque[BlackboardRecord]]
    by_simplified_name: defaultdict[str, deque[BlackboardRecord]]
    by_id: defaultdict[str, deque[BlackboardRecord]]
    by_digits: defaultdict[str, deque[BlackboardRecord]]


@dataclass
class ProcessedResult:
    dataframe: pd.DataFrame
    columns: list[str]
    table_rows: list[dict[str, object]]
    unmatched_rows: list[dict[str, str]]
    matched_count: int
    unmatched_count: int
    skipped_count: int


def ensure_runtime_dirs() -> None:
    for slot in UPLOAD_SLOTS.values():
        slot["folder"].mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def build_saved_name(filename: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_name = secure_filename(filename)
    return f"{timestamp}_{clean_name}"


def get_slot_path(slot_name: str) -> Path | None:
    slot = UPLOAD_SLOTS[slot_name]
    saved_name = session.get(slot["session_key"])
    if not saved_name:
        return None

    target_path = slot["folder"] / saved_name
    return target_path if target_path.exists() else None


def get_result_metadata_path(result_name: str) -> Path:
    return RESULT_DIR / f"{Path(result_name).stem}.json"


def serialize_value(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value)


def remove_slot_file(slot_name: str) -> None:
    file_path = get_slot_path(slot_name)
    session.pop(UPLOAD_SLOTS[slot_name]["session_key"], None)
    if file_path is not None and file_path.exists():
        file_path.unlink()


def remove_result_file() -> None:
    result_name = session.pop("result_file", None)
    if not result_name:
        return

    result_path = RESULT_DIR / result_name
    metadata_path = get_result_metadata_path(result_name)
    for path in (result_path, metadata_path):
        if path.exists():
            path.unlink()


def build_empty_result_view() -> dict[str, object]:
    return {
        "result_columns": [],
        "result_rows": [],
        "unmatched_rows": [],
        "result_summary": {
            "total_rows": 0,
            "student_rows": 0,
            "matched_count": 0,
            "unmatched_count": 0,
            "skipped_count": 0,
        },
    }


def write_result_metadata(result_name: str, metadata: dict[str, object]) -> None:
    metadata_path = get_result_metadata_path(result_name)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def load_result_metadata(result_name: str | None) -> dict[str, object] | None:
    if not result_name:
        return None

    metadata_path = get_result_metadata_path(result_name)
    if not metadata_path.exists():
        return None

    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def build_result_metadata(processed_result: ProcessedResult) -> dict[str, object]:
    return {
        "columns": processed_result.columns,
        "rows": processed_result.table_rows,
        "unmatched_rows": processed_result.unmatched_rows,
        "summary": {
            "total_rows": len(processed_result.table_rows),
            "student_rows": processed_result.matched_count + processed_result.unmatched_count,
            "matched_count": processed_result.matched_count,
            "unmatched_count": processed_result.unmatched_count,
            "skipped_count": processed_result.skipped_count,
        },
    }


def get_result_view(result_name: str | None) -> dict[str, object]:
    if not result_name:
        return build_empty_result_view()

    metadata = load_result_metadata(result_name)
    if metadata is None:
        docente_path = get_slot_path("docente")
        blackboard_path = get_slot_path("blackboard")
        if docente_path is not None and blackboard_path is not None:
            try:
                processed_result = build_result_dataframe(read_table(docente_path), read_table(blackboard_path))
            except ProcessingError:
                return build_empty_result_view()

            metadata = build_result_metadata(processed_result)
            write_result_metadata(result_name, metadata)
        else:
            return build_empty_result_view()

    summary = metadata.get("summary", {})
    return {
        "result_columns": metadata.get("columns", []),
        "result_rows": metadata.get("rows", []),
        "unmatched_rows": metadata.get("unmatched_rows", []),
        "result_summary": {
            "total_rows": summary.get("total_rows", 0),
            "student_rows": summary.get("student_rows", 0),
            "matched_count": summary.get("matched_count", 0),
            "unmatched_count": summary.get("unmatched_count", 0),
            "skipped_count": summary.get("skipped_count", 0),
        },
    }


def get_upload_state() -> dict[str, str | bool | None]:
    docente_name = session.get(UPLOAD_SLOTS["docente"]["session_key"])
    blackboard_name = session.get(UPLOAD_SLOTS["blackboard"]["session_key"])
    result_name = session.get("result_file")
    has_docente = get_slot_path("docente") is not None
    has_blackboard = get_slot_path("blackboard") is not None
    has_result = bool(result_name and (RESULT_DIR / result_name).exists())
    state = {
        "docente_name": docente_name if has_docente else None,
        "blackboard_name": blackboard_name if has_blackboard else None,
        "result_name": result_name if has_result else None,
        "has_uploads": has_docente and has_blackboard,
        "has_any_files": has_docente or has_blackboard or has_result,
        "ready": has_result,
    }
    state.update(get_result_view(state["result_name"]))
    return state


def normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    normalized = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_header(value: object) -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_name_keys(value: object) -> tuple[str, str]:
    text = normalize_text(value)
    text = re.sub(r"[-_/.,;:()]+", " ", text)
    tokens = re.findall(r"[a-z0-9]+", text)

    if not tokens:
        return "", ""

    full_key = " ".join(sorted(tokens))
    simplified_tokens = [token for token in tokens if token not in IGNORE_NAME_TOKENS]
    simplified_key = " ".join(sorted(simplified_tokens or tokens))
    return full_key, simplified_key


def build_id_keys(value: object) -> tuple[str, str]:
    text = normalize_text(value)
    alphanumeric_key = re.sub(r"[^a-z0-9]+", "", text)
    digits_key = re.sub(r"\D+", "", text)
    return alphanumeric_key, digits_key


def is_non_student_row(id_key: str, digits_key: str, simplified_name_key: str) -> bool:
    if digits_key:
        return False

    if id_key in SUMMARY_ROW_HINTS:
        return True

    return not simplified_name_key


def parse_grade(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()
    if not text or text in {"-", "--"}:
        return None

    cleaned = text.replace("%", "").replace(",", ".").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None

    try:
        grade = Decimal(match.group(0))
    except InvalidOperation:
        return None

    if grade <= Decimal("7"):
        grade *= Decimal("10")

    return int(grade.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def is_probably_text_table(file_path: Path) -> bool:
    header = file_path.read_bytes()[:4096]
    if header.startswith(b"\xd0\xcf\x11\xe0") or header.startswith(b"PK\x03\x04"):
        return False

    if header.startswith((b"\xff\xfe", b"\xfe\xff")):
        return True

    return b"\x00" in header or b"\t" in header


def read_delimited_table(file_path: Path, separators: tuple[str | None, ...]) -> pd.DataFrame:
    last_error: Exception | None = None

    for encoding in TEXT_TABLE_ENCODINGS:
        for separator in separators:
            try:
                read_kwargs = {
                    "dtype": object,
                    "encoding": encoding,
                    "engine": "python",
                }
                if separator is None:
                    read_kwargs["sep"] = None
                else:
                    read_kwargs["sep"] = separator

                dataframe = pd.read_csv(file_path, **read_kwargs)
            except Exception as exc:
                last_error = exc
                continue

            if len(dataframe.columns) == 1:
                first_column = str(dataframe.columns[0])
                if "\t" in first_column or ";" in first_column:
                    continue

            return dataframe

    raise ProcessingError(f"No se pudo leer el archivo {file_path.name}.") from last_error


def read_table(file_path: Path) -> pd.DataFrame:
    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        return read_delimited_table(file_path, separators=(None, ";", "\t"))

    if suffix == ".xls" and is_probably_text_table(file_path):
        return read_delimited_table(file_path, separators=("\t", ";", None))

    try:
        return pd.read_excel(file_path, dtype=object)
    except ImportError as exc:
        raise ProcessingError(
            "Falta una libreria para leer ese archivo Excel. Instala las dependencias del proyecto."
        ) from exc
    except Exception as exc:
        if suffix == ".xls":
            try:
                return read_delimited_table(file_path, separators=("\t", ";", None))
            except ProcessingError:
                pass

        raise ProcessingError(f"No se pudo leer el archivo {file_path.name}.") from exc


def find_column_by_hints(columns: list[object], hints: tuple[str, ...]) -> object | None:
    exact_map = {normalize_header(column): column for column in columns}
    for hint in hints:
        if hint in exact_map:
            return exact_map[hint]

    for column in columns:
        header = normalize_header(column)
        if any(hint in header for hint in hints):
            return column

    return None


def detect_docente_name_column(columns: list[object]) -> object:
    first_three = columns[:3]
    detected = find_column_by_hints(first_three, DOCENTE_NAME_HINTS)
    if detected is not None:
        return detected

    return first_three[2]


def detect_docente_id_column(columns: list[object]) -> object | None:
    first_three = columns[:3]
    return find_column_by_hints(first_three, DOCENTE_ID_HINTS)


def pick_grade_column(dataframe: pd.DataFrame, excluded_columns: set[object]) -> object:
    ranked_columns: list[tuple[int, int, int, object]] = []

    for index, column in enumerate(dataframe.columns):
        if column in excluded_columns:
            continue

        header = normalize_header(column)
        header_score = 0
        if any(hint in header for hint in GRADE_HINTS):
            header_score = 10
        elif any(token in header for token in ("rut", "id", "username", "access", "availability", "correo", "email")):
            header_score = -5

        numeric_matches = sum(1 for value in dataframe[column] if parse_grade(value) is not None)
        ranked_columns.append((header_score, numeric_matches, index, column))

    ranked_columns.sort(key=lambda item: (item[0], item[1], item[2]))
    best_score, best_numeric_matches, _, best_column = ranked_columns[-1]

    if best_numeric_matches == 0 and best_score <= 0:
        raise ProcessingError("No pude detectar la columna de nota en el archivo de Blackboard.")

    return best_column


def build_blackboard_name_series(dataframe: pd.DataFrame) -> tuple[pd.Series, set[object]]:
    columns = list(dataframe.columns)
    full_name_column = find_column_by_hints(columns, FULL_NAME_HINTS)
    if full_name_column is not None:
        return dataframe[full_name_column], {full_name_column}

    first_name_column = find_column_by_hints(columns, FIRST_NAME_HINTS)
    last_name_column = find_column_by_hints(columns, LAST_NAME_HINTS)
    if first_name_column is not None and last_name_column is not None:
        combined_series = (
            dataframe[first_name_column].fillna("").astype(str).str.strip()
            + " "
            + dataframe[last_name_column].fillna("").astype(str).str.strip()
        ).str.strip()
        return combined_series, {first_name_column, last_name_column}

    fallback_name_column = find_column_by_hints(columns, BLACKBOARD_NAME_HINTS)
    if fallback_name_column is not None:
        return dataframe[fallback_name_column], {fallback_name_column}

    raise ProcessingError("No pude detectar la columna de nombre en el archivo de Blackboard.")


def build_blackboard_records(dataframe: pd.DataFrame) -> BlackboardIndexes:
    name_series, name_columns = build_blackboard_name_series(dataframe)
    id_column = find_column_by_hints(list(dataframe.columns), BLACKBOARD_ID_HINTS)
    excluded_columns = set(name_columns)
    if id_column is not None:
        excluded_columns.add(id_column)

    grade_column = pick_grade_column(dataframe, excluded_columns=excluded_columns)
    grade_series = dataframe[grade_column]
    id_series = dataframe[id_column] if id_column is not None else pd.Series([None] * len(dataframe))

    records_by_full: defaultdict[str, deque[BlackboardRecord]] = defaultdict(deque)
    records_by_simplified: defaultdict[str, deque[BlackboardRecord]] = defaultdict(deque)
    records_by_id: defaultdict[str, deque[BlackboardRecord]] = defaultdict(deque)
    records_by_digits: defaultdict[str, deque[BlackboardRecord]] = defaultdict(deque)

    for name_value, grade_value, id_value in zip(name_series, grade_series, id_series):
        full_key, simplified_key = build_name_keys(name_value)
        id_key, digits_key = build_id_keys(id_value)
        grade = parse_grade(grade_value)

        if not full_key or grade is None:
            continue

        record = BlackboardRecord(full_key=full_key, simplified_key=simplified_key, grade=grade)
        records_by_full[full_key].append(record)
        records_by_simplified[simplified_key].append(record)
        if id_key:
            records_by_id[id_key].append(record)
        if digits_key:
            records_by_digits[digits_key].append(record)

    return BlackboardIndexes(
        by_full_name=records_by_full,
        by_simplified_name=records_by_simplified,
        by_id=records_by_id,
        by_digits=records_by_digits,
    )


def pop_unused_record(bucket: deque[BlackboardRecord]) -> BlackboardRecord | None:
    while bucket and bucket[0].used:
        bucket.popleft()

    if not bucket:
        return None

    record = bucket.popleft()
    record.used = True
    return record


def find_subset_name_record(
    simplified_key: str,
    records_by_simplified: defaultdict[str, deque[BlackboardRecord]],
) -> BlackboardRecord | None:
    desired_tokens = set(simplified_key.split())
    if len(desired_tokens) < 2:
        return None

    best_candidate_key = ""
    best_score = 0

    for candidate_key, bucket in records_by_simplified.items():
        candidate_record = next((record for record in bucket if not record.used), None)
        if candidate_record is None:
            continue

        candidate_tokens = set(candidate_key.split())
        if len(candidate_tokens) < 2:
            continue

        if candidate_tokens.issubset(desired_tokens) or desired_tokens.issubset(candidate_tokens):
            score = len(candidate_tokens & desired_tokens)
            if score > best_score:
                best_candidate_key = candidate_key
                best_score = score

    if not best_candidate_key:
        return None

    return pop_unused_record(records_by_simplified[best_candidate_key])


def build_unmatched_search_text(raw_id_value: object, raw_name_value: object) -> str:
    id_key, digits_key = build_id_keys(raw_id_value)
    _, simplified_key = build_name_keys(raw_name_value)

    parts: list[str] = []
    if digits_key:
        parts.append(f"Rut/ID {digits_key}")
    elif id_key:
        parts.append(f"identificador {id_key}")

    if simplified_key:
        parts.append(f"nombre {simplified_key}")

    return " / ".join(parts) if parts else "Sin claves de busqueda"


def build_result_dataframe(docente_df: pd.DataFrame, blackboard_df: pd.DataFrame) -> ProcessedResult:
    if docente_df.empty:
        raise ProcessingError("El archivo de Sistema Notas Docente no tiene filas.")

    if len(docente_df.columns) < 3:
        raise ProcessingError("El archivo de Sistema Notas Docente debe tener al menos 3 columnas.")

    blackboard_indexes = build_blackboard_records(blackboard_df)
    selected_columns = list(docente_df.columns[:3])
    output_df = docente_df.loc[:, selected_columns].copy()
    docente_name_column = detect_docente_name_column(selected_columns)
    docente_id_column = detect_docente_id_column(selected_columns)
    result_columns = [str(column) for column in selected_columns] + ["nota"]

    notes: list[int | str] = []
    table_rows: list[dict[str, object]] = []
    unmatched_rows: list[dict[str, str]] = []
    matched_count = 0
    unmatched_count = 0
    skipped_count = 0

    for _, row in output_df.iterrows():
        name_value = row[docente_name_column]
        full_key, simplified_key = build_name_keys(name_value)
        id_key, digits_key = build_id_keys(row[docente_id_column]) if docente_id_column is not None else ("", "")
        base_row = {str(column): serialize_value(row[column]) for column in selected_columns}

        if is_non_student_row(id_key, digits_key, simplified_key):
            notes.append("")
            skipped_count += 1
            table_rows.append({**base_row, "nota": "", "is_unmatched": False, "is_summary": True})
            continue

        matched_record = None

        if id_key:
            matched_record = pop_unused_record(blackboard_indexes.by_id[id_key])

        if matched_record is None and digits_key:
            matched_record = pop_unused_record(blackboard_indexes.by_digits[digits_key])

        if matched_record is None and full_key:
            matched_record = pop_unused_record(blackboard_indexes.by_full_name[full_key])

        if matched_record is None and simplified_key:
            matched_record = pop_unused_record(blackboard_indexes.by_simplified_name[simplified_key])

        if matched_record is None and simplified_key:
            matched_record = find_subset_name_record(simplified_key, blackboard_indexes.by_simplified_name)

        if matched_record is not None:
            note_value: int | str = matched_record.grade
            matched_count += 1
            table_rows.append(
                {**base_row, "nota": serialize_value(note_value), "is_unmatched": False, "is_summary": False}
            )
        else:
            note_value = 10
            unmatched_count += 1
            table_rows.append({**base_row, "nota": "10", "is_unmatched": True, "is_summary": False})
            unmatched_rows.append(
                {
                    **base_row,
                    "detalle": "No se encontro coincidencia en Blackboard.",
                    "buscado": build_unmatched_search_text(
                        row[docente_id_column] if docente_id_column is not None else "",
                        name_value,
                    ),
                }
            )

        notes.append(note_value)

    output_df["nota"] = notes
    return ProcessedResult(
        dataframe=output_df,
        columns=result_columns,
        table_rows=table_rows,
        unmatched_rows=unmatched_rows,
        matched_count=matched_count,
        unmatched_count=unmatched_count,
        skipped_count=skipped_count,
    )


def generate_result_file(docente_path: Path, blackboard_path: Path) -> str:
    docente_df = read_table(docente_path)
    blackboard_df = read_table(blackboard_path)
    processed_result = build_result_dataframe(docente_df, blackboard_df)

    ensure_runtime_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_name = f"{timestamp}_notas_preparadas.xlsx"
    result_path = RESULT_DIR / result_name
    processed_result.dataframe.to_excel(result_path, index=False)
    write_result_metadata(result_name, build_result_metadata(processed_result))
    return result_name


def refresh_result_if_possible() -> bool:
    docente_path = get_slot_path("docente")
    blackboard_path = get_slot_path("blackboard")
    if not docente_path or not blackboard_path:
        return False

    remove_result_file()
    result_name = generate_result_file(docente_path, blackboard_path)
    session["result_file"] = result_name
    return True


@app.route("/")
def index():
    return render_template("index.html", state=get_upload_state())


def validate_uploaded_file(uploaded_file, slot_name: str) -> None:
    slot = UPLOAD_SLOTS[slot_name]
    if uploaded_file is None or uploaded_file.filename == "":
        raise ProcessingError(f"Selecciona un archivo para {slot['label']}.")

    if not allowed_file(uploaded_file.filename):
        raise ProcessingError("Solo se permiten archivos Excel o CSV.")


def save_uploaded_file(slot_name: str, uploaded_file) -> Path:
    ensure_runtime_dirs()
    old_path = get_slot_path(slot_name)
    saved_name = build_saved_name(uploaded_file.filename)
    target_path = UPLOAD_SLOTS[slot_name]["folder"] / saved_name
    uploaded_file.save(target_path)
    session[UPLOAD_SLOTS[slot_name]["session_key"]] = saved_name

    if old_path is not None and old_path != target_path and old_path.exists():
        old_path.unlink()

    return target_path


@app.post("/clear/<slot_name>")
def clear_slot(slot_name: str):
    if slot_name not in UPLOAD_SLOTS:
        flash("Tipo de archivo no reconocido.", "error")
        return redirect(url_for("index"))

    remove_result_file()
    remove_slot_file(slot_name)
    flash(f"Se elimino el archivo de {UPLOAD_SLOTS[slot_name]['label']}.", "success")
    return redirect(url_for("index"))


@app.post("/clear-all")
def clear_all():
    remove_result_file()
    for slot_name in UPLOAD_SLOTS:
        remove_slot_file(slot_name)

    flash("Se eliminaron los archivos cargados y el resultado generado.", "success")
    return redirect(url_for("index"))


@app.post("/process")
def process_files():
    docente_upload = request.files.get("docente_file")
    blackboard_upload = request.files.get("blackboard_file")
    docente_has_new_file = bool(docente_upload and docente_upload.filename)
    blackboard_has_new_file = bool(blackboard_upload and blackboard_upload.filename)

    try:
        if docente_has_new_file:
            validate_uploaded_file(docente_upload, "docente")
        elif get_slot_path("docente") is None:
            raise ProcessingError(f"Selecciona un archivo para {UPLOAD_SLOTS['docente']['label']}.")

        if blackboard_has_new_file:
            validate_uploaded_file(blackboard_upload, "blackboard")
        elif get_slot_path("blackboard") is None:
            raise ProcessingError(f"Selecciona un archivo para {UPLOAD_SLOTS['blackboard']['label']}.")
    except ProcessingError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))

    docente_path = save_uploaded_file("docente", docente_upload) if docente_has_new_file else get_slot_path("docente")
    blackboard_path = (
        save_uploaded_file("blackboard", blackboard_upload)
        if blackboard_has_new_file
        else get_slot_path("blackboard")
    )

    try:
        remove_result_file()
        result_name = generate_result_file(docente_path, blackboard_path)
        session["result_file"] = result_name
        flash("Archivo final generado correctamente.", "success")
    except ProcessingError as exc:
        remove_result_file()
        flash(str(exc), "error")

    return redirect(url_for("index"))


@app.get("/download-result")
def download_result():
    result_name = session.get("result_file")
    result_path = RESULT_DIR / result_name if result_name else None

    if result_path is None or not result_path.exists():
        try:
            if not refresh_result_if_possible():
                flash("Carga ambos archivos antes de descargar el resultado.", "error")
                return redirect(url_for("index"))
        except ProcessingError as exc:
            flash(str(exc), "error")
            return redirect(url_for("index"))

        result_name = session.get("result_file")
        result_path = RESULT_DIR / result_name if result_name else None

    if result_path is None or not result_path.exists():
        flash("No pude generar el archivo final.", "error")
        return redirect(url_for("index"))

    return send_file(
        result_path,
        as_attachment=True,
        download_name=result_path.name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    ensure_runtime_dirs()
    app.run(debug=True)
