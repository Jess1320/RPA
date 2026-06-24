# RPA_CEXT_PROD_DIARIO.py
# Descarga diaria (HOY/AYER con offset) desde ExplotaDatos usando checks por mes (2 tabs),
# dedupe global, limpieza por TAG (mismo día) + NUEVO: mantener SOLO el día actual (borra históricos de otros días).
#
# Ejecuta con:
#   .\.venv\Scripts\python.exe .\RPA_CEXT_PROD_DIARIO.py

import csv
import hashlib
import json
import unicodedata
import socket
from db_pg import PgRPAControl, parse_file_metadata
import os
import sys
import time
import datetime
import subprocess
import psycopg2
from psycopg2.extras import RealDictCursor
import threading
import signal
import platform
from typing import List, Tuple, Dict, Optional, Callable
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
import shutil
from pathlib import Path
import re
import random

_CSV_FIELD_LIMIT = sys.maxsize
while True:
    try:
        csv.field_size_limit(_CSV_FIELD_LIMIT)
        break
    except OverflowError:
        _CSV_FIELD_LIMIT //= 10

from mailer import send_smtp_mail
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import TimeoutException, WebDriverException

from dotenv import load_dotenv

import gspread
from gspread.exceptions import APIError
from oauth2client.service_account import ServiceAccountCredentials


# =========================
# Señales / Cancelación
# =========================
STOP_EVENT = threading.Event()
ACTIVE_BROWSER_LOCK = threading.Lock()
ACTIVE_DRIVERS: Dict[int, object] = {}
ACTIVE_PROFILE_DIRS: set[str] = set()
DRIVER_START_SEMAPHORE = threading.BoundedSemaphore(2)
DRIVER_START_LIMIT = 2


def set_driver_start_limit(limit: int) -> None:
    global DRIVER_START_SEMAPHORE, DRIVER_START_LIMIT
    try:
        limit = int(limit)
    except Exception:
        limit = 2
    if limit <= 0:
        limit = 1
    DRIVER_START_LIMIT = limit
    DRIVER_START_SEMAPHORE = threading.BoundedSemaphore(limit)


def register_active_driver(driver) -> None:
    if driver is None:
        return
    try:
        with ACTIVE_BROWSER_LOCK:
            ACTIVE_DRIVERS[id(driver)] = driver
    except Exception:
        pass


def unregister_active_driver(driver) -> None:
    if driver is None:
        return
    try:
        with ACTIVE_BROWSER_LOCK:
            ACTIVE_DRIVERS.pop(id(driver), None)
    except Exception:
        pass


def register_active_profile_dir(profile_dir: str) -> None:
    if not profile_dir:
        return
    try:
        with ACTIVE_BROWSER_LOCK:
            ACTIVE_PROFILE_DIRS.add(profile_dir)
    except Exception:
        pass


def unregister_active_profile_dir(profile_dir: str) -> None:
    if not profile_dir:
        return
    try:
        with ACTIVE_BROWSER_LOCK:
            ACTIVE_PROFILE_DIRS.discard(profile_dir)
    except Exception:
        pass


def safe_rmtree(path: str, retries: int = 3, delay: float = 1.0) -> bool:
    if not path or not os.path.exists(path):
        return True

    for intento in range(1, retries + 1):
        try:
            shutil.rmtree(path, ignore_errors=False)
            return True
        except FileNotFoundError:
            return True
        except Exception as e:
            if intento == retries:
                print(f"WARN | TMP_PROFILE_DELETE_FAIL | {path} | {type(e).__name__}:{e}", flush=True)
            else:
                time.sleep(delay)

    return not os.path.exists(path)


def cleanup_active_browser_resources() -> None:
    try:
        with ACTIVE_BROWSER_LOCK:
            drivers = list(ACTIVE_DRIVERS.values())
            profiles = list(ACTIVE_PROFILE_DIRS)
            ACTIVE_DRIVERS.clear()
            ACTIVE_PROFILE_DIRS.clear()
    except Exception:
        drivers = []
        profiles = []

    for driver in drivers:
        try:
            driver.quit()
        except Exception as e:
            print(f"WARN | ACTIVE_DRIVER_QUIT_FAIL | {type(e).__name__}:{e}", flush=True)

    for profile_dir in profiles:
        safe_rmtree(profile_dir)


def handle_signal(signum, frame):
    STOP_EVENT.set()
    print(f"WARN | SIGNAL_RECEIVED | signum={signum}", flush=True)
    cleanup_active_browser_resources()


signal.signal(signal.SIGINT, handle_signal)
try:
    signal.signal(signal.SIGTERM, handle_signal)
except Exception:
    pass


def kill_chromedrivers():
    if platform.system() == "Windows":
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "chromedriver.exe", "/T"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception:
            pass


# =========================
# Env helpers (robusto)
# =========================
def _clean_env(v: Optional[str], default: str = "") -> str:
    if v is None:
        v = default
    v = v.split("#", 1)[0].strip()  # quita comentario inline
    v = v.strip().strip('"').strip("'")
    return v


def _strip_key_prefix(v: str, key: str) -> str:
    pref = f"{key}="
    vv = (v or "").strip()
    if vv.upper().startswith(pref.upper()):
        return vv[len(pref):].strip()
    return vv


def _env_int(name: str, default: str = "0") -> int:
    s = _clean_env(os.getenv(name), default)
    s = _strip_key_prefix(s, name)
    return int(s) if s else int(default)


def _env_bool(name: str, default: str = "false") -> bool:
    s = _clean_env(os.getenv(name), default).lower()
    s = _strip_key_prefix(s, name).lower()
    return s in ("1", "true", "yes", "y", "si", "sí")


def _env_str(name: str, default: str = "") -> str:
    s = _clean_env(os.getenv(name), default)
    return _strip_key_prefix(s, name)


def should_send_preflight_mail() -> bool:
    try:
        attempt = _env_int("RPA_ORCH_ATTEMPT", "1")
        max_attempts = _env_int("RPA_ORCH_MAX_ATTEMPTS", "1")
    except Exception:
        return True

    return attempt >= max_attempts


# =========================
# Log por corrida + retención
# =========================
def ensure_dir(p: str) -> None:
    Path(p).mkdir(parents=True, exist_ok=True)


def ts_now() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


class TeeWriter:
    """Duplica stdout/stderr hacia un archivo (run.log) sin reescribir todos los print()."""
    def __init__(self, original_stream, file_stream):
        self.original = original_stream
        self.file = file_stream

    def write(self, s):
        try:
            self.original.write(s)
        except Exception:
            pass
        try:
            self.file.write(s)
        except Exception:
            pass

    def flush(self):
        try:
            self.original.flush()
        except Exception:
            pass
        try:
            self.file.flush()
        except Exception:
            pass


def cleanup_old_run_dirs(base_dir: str, run_prefix: str, retention_days: int) -> int:
    if retention_days <= 0 or not os.path.isdir(base_dir):
        return 0

    now = time.time()
    cutoff = now - (retention_days * 86400)
    removed = 0

    for name in os.listdir(base_dir):
        if not name.startswith(run_prefix):
            continue
        p = os.path.join(base_dir, name)
        if not os.path.isdir(p):
            continue
        try:
            if os.path.getmtime(p) < cutoff:
                shutil.rmtree(p, ignore_errors=True)
                removed += 1
        except Exception:
            pass

    return removed


def write_summary_line(summary_path: str, line: str) -> None:
    try:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")
    except Exception:
        pass


def summary(summary_path: str, msg: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | INFO | SUMMARY | {msg}"
    print(line, flush=True)
    write_summary_line(summary_path, line)


def emit_event(summary_path: str, db, run_db_id: Optional[int], level: str, event_type: str, message: str) -> None:
    summary(summary_path, f"{event_type} | {message}")
    if db and run_db_id:
        try:
            db.log_event(run_db_id, level, event_type, message)
        except Exception as e:
            print(f"DB_LOG_WARN | {event_type} | {type(e).__name__}: {e}", flush=True)

STG_CEXT_COLUMNS = [
    "centro", "periodo", "cod_servicio", "servicio", "codactividad", "actividad", "codsubacti", "subactividad",
    "fecha_solic", "fecha_cita", "hora_cita", "condicion_cita", "codestcita", "estado_cita", "codtipcita", "tipo_cita",
    "h_c", "ubicacion_hc", "acto_med", "dni_medico", "cmp", "codgrupocup", "grupo_ocupacional", "profesional",
    "tipo_paciente", "doc_paciente", "autogenerado", "paciente", "fecnacimpaciente", "edad", "sexo",
    "tel_fijo", "tel_movil", "cod_tipseguro", "tipo_seguro", "codtiparent", "tiparentesco",
    "codprecedencia", "descprecedencia", "cas_adscripcion", "nombadscripcion", "n_r_c_ser", "n_r_c_est",
    "horainicio", "horafinal", "codubigdomic", "ubigeodomic", "turno", "codtipprogramac", "tip_programacion",
    "useregistro", "fecha_reg", "hora_reg", "usermodifica", "fecha_modifica", "hora_modifica",
    "useranula", "fecha_anula", "hora_anula", "orden_atencion", "codmotdeser", "motivo_desercion",
    "codmodotorcita", "modalidadotorcita", "motivelimcita", "numreferorigen", "codconsultorio",
    "desconsultorio", "ultcie10aten", "estado_programacion", "motivo_suspension", "fechreferencia",
    "usuaregistro", "estadreferencia", "observacion"
]


def sync_medicos_cenate_from_241(
    db,
    src_host: str,
    src_port: int,
    src_database: str,
    src_user: str,
    src_password: str,
    summary_path: str,
    run_db_id: Optional[int] = None
) -> int:
    sql = """
    select
        trim(num_doc_pers) as dni_medico,
        nombre_completo,
        area,
        id_servicio,
        cod_servicio,
        servicio,
        tipo_personal,
        id_reg_lab,
        regimen_laboral
    from public.vw_personal_asistencial_activo;
    """

    conn = None
    try:
        conn = psycopg2.connect(
            host=src_host,
            port=src_port,
            dbname=src_database,
            user=src_user,
            password=src_password
        )

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            data = cur.fetchall()

        rows = []
        ts_now = datetime.datetime.now()
        for r in data:
            rows.append((
                (r.get("dni_medico") or "").strip(),
                r.get("nombre_completo"),
                r.get("area"),
                r.get("id_servicio"),
                r.get("cod_servicio"),
                r.get("servicio"),
                r.get("tipo_personal"),
                r.get("id_reg_lab"),
                r.get("regimen_laboral"),
                ts_now
            ))

        db.refresh_medicos_cenate_current(rows)

        emit_event(
            summary_path,
            db,
            run_db_id,
            "INFO",
            "SYNC_MEDICOS_241",
            f"rows={len(rows)}"
        )

        return len(rows)

    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def mark_reportes_diario_en_ejecucion(
    db,
    run_uuid: str,
    fecha_operativa: datetime.date,
    fecha_futuro_fin: datetime.date
) -> None:
    db.set_report_status(
        report_code="REP_DIARIO_PENDIENTES_DIA",
        report_name="Reporte Diario - Pendientes del Día",
        rpa_job_code="CEXT_PROD_DIARIO",
        status="EN_EJECUCION",
        message="Actualizando reporte",
        target_date_start=fecha_operativa,
        target_date_end=fecha_operativa,
        last_run_uuid=run_uuid,
        started_at=datetime.datetime.now(),
        finished_at=None,
        last_success_at=None,
        row_count=None
    )

    db.set_report_status(
        report_code="REP_DIARIO_CITADOS_FUTURO",
        report_name="Reporte Diario - Citados a Futuro",
        rpa_job_code="CEXT_PROD_DIARIO",
        status="EN_EJECUCION",
        message="Actualizando reporte",
        target_date_start=fecha_operativa + datetime.timedelta(days=1),
        target_date_end=fecha_futuro_fin,
        last_run_uuid=run_uuid,
        started_at=datetime.datetime.now(),
        finished_at=None,
        last_success_at=None,
        row_count=None
    )


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def normalize_header_name(s: str) -> str:
    s = strip_accents((s or "").strip()).upper()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^A-Z0-9_]", "", s)
    return s


def detect_delimiter(header_line: str) -> str:
    if "\t" in header_line:
        return "\t"
    if "|" in header_line:
        return "|"
    if ";" in header_line:
        return ";"
    return ","


def header_status_from_lists(unknown_columns: list, missing_required: list, alias_used: bool) -> str:
    if missing_required and unknown_columns:
        return "MIXED"
    if missing_required:
        return "MISSING_CRITICAL_COLUMNS"
    if unknown_columns:
        return "NEW_COLUMNS_DETECTED"
    if alias_used:
        return "HEADER_ALIAS_USED"
    return "OK"

def month_range_list(start_date: datetime.date, end_date: datetime.date) -> List[int]:
    months = []
    y, m = start_date.year, start_date.month
    end_y, end_m = end_date.year, end_date.month

    while (y, m) <= (end_y, end_m):
        months.append(m)
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1

    return months


def merge_centros_meta_items(items: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], int, int]:
    centros_map: Dict[str, Dict[str, str]] = {}
    dup_global = 0
    macro_conflict = 0

    for item in items:
        canon = _canon_code(item["centro"])
        if canon in centros_map:
            dup_global += 1
            if centros_map[canon]["macro"] != item["macro"]:
                macro_conflict += 1
            continue
        centros_map[canon] = item

    return list(centros_map.values()), dup_global, macro_conflict


def procesar_txt_a_staging(
    db,
    id_run: int,
    run_uuid: str,
    id_archivo: int,
    file_name: str,
    file_path: str,
    summary_path: str
) -> None:
    expected = db.get_expected_columns()
    aliases_raw = db.get_column_aliases()

    aliases = {normalize_header_name(k): v for k, v in aliases_raw.items()}
    expected_set = set(expected.keys())

    with open(file_path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        first_line = f.readline()
        if not first_line:
            raise RuntimeError(f"Archivo vacío: {file_name}")

        delimiter = detect_delimiter(first_line)
        f.seek(0)
        reader = csv.reader(f, delimiter=delimiter, quoting=csv.QUOTE_NONE)

        header_original = next(reader)
        header_normalized = [normalize_header_name(h) for h in header_original]

        header_map = []
        matched_columns = []
        unknown_columns = []
        alias_used = False

        for h_norm in header_normalized:
            if h_norm in expected_set:
                canonical = h_norm
            elif h_norm in aliases:
                canonical = aliases[h_norm]
                alias_used = True
            else:
                canonical = None

            header_map.append(canonical)
            if canonical:
                matched_columns.append(canonical)
            else:
                unknown_columns.append(h_norm)

        required_columns = [k for k, v in expected.items() if v["required"]]
        missing_required = [c for c in required_columns if c not in matched_columns]

        status = header_status_from_lists(unknown_columns, missing_required, alias_used)
        header_signature = hashlib.sha256("|".join(header_normalized).encode("utf-8")).hexdigest()

        _, _, _, tipo_descarga_archivo, _ = parse_file_metadata(file_name)
        db.insert_file_header_version(
            id_run=id_run,
            id_archivo=id_archivo,
            tipo_descarga_archivo=tipo_descarga_archivo or "",
            header_signature=header_signature,
            header_original=header_original,
            header_normalized=header_normalized,
            matched_columns=matched_columns,
            unknown_columns=unknown_columns,
            missing_required=missing_required,
            status=status
        )

        emit_event(
            summary_path,
            db,
            id_run,
            "INFO" if status in ("OK", "HEADER_ALIAS_USED") else "WARN",
            "SCHEMA_DRIFT",
            f"file={file_name} | status={status} | unknown={unknown_columns} | missing_required={missing_required}"
        )

        if status in ("MISSING_CRITICAL_COLUMNS", "MIXED"):
            db.mark_file_loaded_to_staging(id_archivo, loaded=False, estado=f"HEADER_{status}")
            db.create_alert_event(
                id_run=id_run,
                channel="EMAIL",
                alert_type="SCHEMA_DRIFT",
                severity="HIGH",
                title=f"Cabecera crítica afectada: {file_name}",
                message=f"status={status} | missing_required={missing_required} | unknown={unknown_columns}",
                payload={
                    "file_name": file_name,
                    "status": status,
                    "missing_required": missing_required,
                    "unknown_columns": unknown_columns
                }
            )
            return

        rows_to_insert = []
        row_num = 0

        for row in reader:
            row_num += 1

            if len(row) < len(header_map):
                row = row + [""] * (len(header_map) - len(row))
            elif len(row) > len(header_map):
                row = row[:len(header_map)]

            base = {c: None for c in STG_CEXT_COLUMNS}
            extra = {}

            for idx, raw_value in enumerate(row):
                canonical = header_map[idx]
                value = (raw_value or "").strip()

                if not canonical:
                    extra[header_normalized[idx]] = value
                    continue

                stg_col = canonical.lower()
                if stg_col in base:
                    base[stg_col] = value
                else:
                    extra[canonical] = value

            hash_payload = json.dumps(
                {"base": base, "extra": extra},
                ensure_ascii=False,
                sort_keys=True
            )
            row_hash = hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()

            rows_to_insert.append((
                id_run, id_archivo, row_num,
                base["centro"], base["periodo"], base["cod_servicio"], base["servicio"], base["codactividad"], base["actividad"], base["codsubacti"], base["subactividad"],
                base["fecha_solic"], base["fecha_cita"], base["hora_cita"], base["condicion_cita"], base["codestcita"], base["estado_cita"], base["codtipcita"], base["tipo_cita"],
                base["h_c"], base["ubicacion_hc"], base["acto_med"], base["dni_medico"], base["cmp"], base["codgrupocup"], base["grupo_ocupacional"], base["profesional"],
                base["tipo_paciente"], base["doc_paciente"], base["autogenerado"], base["paciente"], base["fecnacimpaciente"], base["edad"], base["sexo"],
                base["tel_fijo"], base["tel_movil"], base["cod_tipseguro"], base["tipo_seguro"], base["codtiparent"], base["tiparentesco"],
                base["codprecedencia"], base["descprecedencia"], base["cas_adscripcion"], base["nombadscripcion"], base["n_r_c_ser"], base["n_r_c_est"],
                base["horainicio"], base["horafinal"], base["codubigdomic"], base["ubigeodomic"], base["turno"], base["codtipprogramac"], base["tip_programacion"],
                base["useregistro"], base["fecha_reg"], base["hora_reg"], base["usermodifica"], base["fecha_modifica"], base["hora_modifica"],
                base["useranula"], base["fecha_anula"], base["hora_anula"], base["orden_atencion"], base["codmotdeser"], base["motivo_desercion"],
                base["codmodotorcita"], base["modalidadotorcita"], base["motivelimcita"], base["numreferorigen"], base["codconsultorio"],
                base["desconsultorio"], base["ultcie10aten"], base["estado_programacion"], base["motivo_suspension"], base["fechreferencia"],
                base["usuaregistro"], base["estadreferencia"], base["observacion"],
                json.dumps(extra, ensure_ascii=False),
                row_hash
            ))

        db.bulk_insert_cext_prod_diario(rows_to_insert)
        db.mark_file_loaded_to_staging(id_archivo, loaded=True, estado="LOADED_TO_STG")

        emit_event(
            summary_path,
            db,
            id_run,
            "INFO",
            "STAGING_LOAD",
            f"file={file_name} | rows={len(rows_to_insert)} | status={status}"
        )


# =========================
# Utilidades (descarga / archivos)
# =========================
def files_with_prefix(download_dir: str, prefix: str) -> List[str]:
    try:
        return [f for f in os.listdir(download_dir) if f.startswith(prefix)]
    except Exception:
        return []


def file_is_stable(path: str, stable_secs: int = 4) -> bool:
    if not os.path.exists(path):
        return False
    s1 = os.path.getsize(path)
    time.sleep(stable_secs)
    if not os.path.exists(path):
        return False
    s2 = os.path.getsize(path)
    return s1 == s2 and s2 > 0


def purge_old_partials(download_dirs: List[str], max_age_minutes: int = 30):
    now = time.time()
    for d in download_dirs:
        try:
            for f in os.listdir(d):
                low = f.lower()
                if low.endswith((".crdownload", ".tmp", ".part")):
                    p = os.path.join(d, f)
                    try:
                        if now - os.path.getmtime(p) > max_age_minutes * 60:
                            os.remove(p)
                            print(f"PURGE_PARTIAL | {d} | {f}", flush=True)
                    except Exception as e:
                        print(f"PURGE_ERR | {d} | {f} | {type(e).__name__}:{e}", flush=True)
        except Exception as e:
            print(f"PURGE_LIST_ERR | {d} | {type(e).__name__}:{e}", flush=True)


def archivo_esta_vacio(filepath: str) -> bool:
    return os.path.exists(filepath) and os.path.getsize(filepath) == 0


def _prefix_centro_tag(center_code: str, tag: str) -> str:
    return f"{center_code.strip()}_{tag}_"


def find_latest_final_by_tag(download_dir: str, center_code: str, tag: str, file_suffix: str = "") -> str:
    prefix = _prefix_centro_tag(center_code, tag)
    candidates = [f for f in files_with_prefix(download_dir, prefix)
                  if f.lower().endswith(".txt") and " (" not in f]
    if file_suffix:
        candidates = [f for f in candidates if f.lower().endswith(file_suffix.lower())]
    if not candidates:
        return ""
    candidates.sort(key=lambda f: os.path.getmtime(os.path.join(download_dir, f)), reverse=True)
    return candidates[0]


def esperar_descarga_por_prefijo(download_dir: str, prefix: str, timeout: int, file_suffix: str = "") -> str:
    start = time.time()
    suf_low = (file_suffix or "").lower()

    while time.time() - start <= timeout:
        if STOP_EVENT.is_set():
            return ""
        try:
            files = [f for f in os.listdir(download_dir) if f.startswith(prefix)]
        except Exception:
            time.sleep(2)
            continue

        partials = [f for f in files if f.lower().endswith((".crdownload", ".tmp", ".part"))]
        finals = [f for f in files if f.lower().endswith(".txt") and " (" not in f]

        if suf_low:
            finals = [f for f in finals if f.lower().endswith(suf_low)]

        if finals and not partials:
            finals.sort(key=lambda f: os.path.getmtime(os.path.join(download_dir, f)), reverse=True)
            cand = finals[0]
            cand_path = os.path.join(download_dir, cand)
            if file_is_stable(cand_path, 3):
                return cand

        time.sleep(2)

    return ""


def remove_partial_with_prefix(download_dir: str, prefix: str, global_max_age_min: int = 10) -> int:
    removed = 0
    now = time.time()

    # parciales/duplicados ligados al prefijo
    for f in files_with_prefix(download_dir, prefix):
        low = f.lower()
        if low.endswith((".crdownload", ".tmp", ".part")) or " (1)." in low or " (2)." in low or " (3)." in low:
            try:
                os.remove(os.path.join(download_dir, f))
                removed += 1
                print(f"PRETRY_CLEAN | {download_dir} | {f}", flush=True)
            except Exception as e:
                print(f"PRETRY_CLEAN_ERR | {download_dir} | {f} | {type(e).__name__}:{e}", flush=True)

    # unconfirmed viejos
    try:
        for f in os.listdir(download_dir):
            low = f.lower()
            if low.endswith(".crdownload") and ("unconfirmed" in low or "sin confirmar" in low):
                p = os.path.join(download_dir, f)
                try:
                    if now - os.path.getmtime(p) > global_max_age_min * 60:
                        os.remove(p)
                        removed += 1
                        print(f"PRETRY_CLEAN_UNCONF | {download_dir} | {f}", flush=True)
                except Exception as e:
                    print(f"PRETRY_CLEAN_UNCONF_ERR | {download_dir} | {f} | {type(e).__name__}:{e}", flush=True)
    except Exception as e:
        print(f"PRETRY_LIST_ERR | {download_dir} | {type(e).__name__}:{e}", flush=True)

    return removed


def delete_finals_with_prefix(download_dir: str, prefix: str, file_suffix: str = "") -> int:
    deleted = 0
    suf_low = (file_suffix or "").lower()

    try:
        for f in os.listdir(download_dir):
            if not f.startswith(prefix):
                continue
            low = f.lower()
            if not low.endswith(".txt"):
                continue
            if " (" in f:
                continue
            if suf_low and not low.endswith(suf_low):
                continue
            try:
                os.remove(os.path.join(download_dir, f))
                deleted += 1
            except Exception:
                pass
    except Exception:
        pass
    return deleted


# =========================
# NUEVO: mantener SOLO el día actual (TAG)
# =========================
_RE_TAG_IN_NAME = re.compile(r"^(?P<center>\d+?)_(?P<d1>\d{8})_(?P<d2>\d{8})_")


def _extract_tag_from_filename(name: str) -> str:
    m = _RE_TAG_IN_NAME.match(name or "")
    if not m:
        return ""
    return f"{m.group('d1')}_{m.group('d2')}"


def _matches_rpa_suffix(fname: str, file_suffix: str) -> bool:
    low = (fname or "").lower()

    if not file_suffix:
        return low.endswith(".txt") or low.endswith((".crdownload", ".tmp", ".part"))

    suf = file_suffix.lower()
    base = suf[:-4] if suf.endswith(".txt") else suf

    if low.endswith(".txt"):
        return low.endswith(suf) or (base and base in low)

    if low.endswith((".crdownload", ".tmp", ".part")):
        return base and base in low

    return False


def cleanup_keep_only_tag(
    download_dirs: List[str],
    keep_tag: str,
    file_suffix: str,
    log_fn: Optional[Callable[[str], None]] = None
) -> None:
    """
    Borra archivos del RPA (por FILE_SUFFIX/base) que tengan TAG != keep_tag.
    Mantiene SOLO el día objetivo.
    """
    log = log_fn or (lambda m: print(m, flush=True))

    for d in download_dirs:
        removed_final = 0
        removed_partial = 0
        errors = 0

        try:
            files = os.listdir(d)
        except Exception as e:
            log(f"KEEP_ONLY_TAG_ERR | dir={d} | {type(e).__name__}:{e}")
            continue

        for f in files:
            if not _matches_rpa_suffix(f, file_suffix):
                continue

            tag = _extract_tag_from_filename(f)
            if not tag:
                continue  # no tocar cosas raras

            if tag == keep_tag:
                continue

            try:
                os.remove(os.path.join(d, f))
                if f.lower().endswith(".txt"):
                    removed_final += 1
                elif f.lower().endswith((".crdownload", ".tmp", ".part")):
                    removed_partial += 1
            except Exception:
                errors += 1

        log(
            f"KEEP_ONLY_TAG | keep={keep_tag} | dir={d} | "
            f"removed_final={removed_final} | removed_partials={removed_partial} | errors={errors}"
        )


# =========================
# Google Sheets: 2 tabs + checks por mes + dedupe
# + RETRY/BACKOFF para 503/429/5xx
# =========================
MONTHS_ES = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL", 5: "MAYO", 6: "JUNIO",
    7: "JULIO", 8: "AGOSTO", 9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE",
}
MONTH_ALIASES = {"SEPTIEMBRE": ["SEPTIEMBRE", "SETIEMBRE"]}


VALID_MACROS = ("CENTRO", "NORTE", "SUR", "LIMA ORIENTE")
INVALID_MACRO_LABEL = "SIN_MACRO"


def _norm_macro(v: str) -> str:
    s = _norm_cell(v)
    aliases = {
        "LIMAORIENTE": "LIMA ORIENTE",
        "LIMA_ORIENTE": "LIMA ORIENTE",
        "LIMA-ORIENTE": "LIMA ORIENTE",
        "LIMA ESTE": "LIMA ORIENTE",
        "LIMA  ORIENTE": "LIMA ORIENTE",
    }
    s = aliases.get(s, s)
    return s


def read_checked_centros_with_macro_from_tab(
    client,
    gsheet_url: str,
    tab_name: str,
    month_num: int,
    log_fn: Optional[Callable[[str], None]] = None
):
    month_header = MONTHS_ES.get(month_num, "")

    ws = _gsheet_call_with_retry(
        lambda: client.open_by_url(gsheet_url).worksheet(tab_name),
        log_fn=log_fn
    )
    values = _gsheet_call_with_retry(lambda: ws.get_all_values(), log_fn=log_fn)

    if not values:
        return [], {"selected": 0, "dup": 0, "unchecked": 0, "empty": 0, "invalid_macro": 0}, month_header

    header = values[0]
    headers_norm = [_norm_cell(h) for h in header]

    idx_cod = _find_col(headers_norm, ["COD_IPRESS", "COD IPRESS", "CODIGO IPRESS", "CODIGO DE IPRESS"])
    if idx_cod < 0:
        for i, h in enumerate(headers_norm):
            if ("COD" in h and "IPRESS" in h) or h == "COD":
                idx_cod = i
                break
    if idx_cod < 0:
        raise RuntimeError(f"GSHEET | No se encontró columna COD_IPRESS en tab={tab_name}")

    idx_macro = _find_col(headers_norm, ["MACRO", "MACROREGION", "MACRO REGIÓN", "MACRO REGION"])
    if idx_macro < 0:
        raise RuntimeError(f"GSHEET | No se encontró columna MACRO en tab={tab_name}")

    month_candidates = MONTH_ALIASES.get(month_header, [month_header])
    idx_month = _find_col(headers_norm, [_norm_cell(x) for x in month_candidates])
    if idx_month < 0:
        raise RuntimeError(f"GSHEET | No se encontró columna mes '{month_header}' en tab={tab_name}")

    selected = []
    seen = set()
    dup = 0
    unchecked = 0
    empty = 0
    invalid_macro = 0

    for row in values[1:]:
        cod = (row[idx_cod] if idx_cod < len(row) else "").strip()
        if not cod:
            empty += 1
            continue

        month_val = (row[idx_month] if idx_month < len(row) else "")
        if not _is_checked(month_val):
            unchecked += 1
            continue

        macro = _norm_macro(row[idx_macro] if idx_macro < len(row) else "")
        if macro not in VALID_MACROS:
            invalid_macro += 1
            macro = INVALID_MACRO_LABEL

        canon = _canon_code(cod)
        if canon in seen:
            dup += 1
            continue

        seen.add(canon)
        selected.append({
            "centro": cod.strip(),
            "macro": macro,
            "tab": tab_name
        })

    return selected, {
        "selected": len(selected),
        "dup": dup,
        "unchecked": unchecked,
        "empty": empty,
        "invalid_macro": invalid_macro
    }, month_header


def get_centros_merged_from_tabs_checked_with_macro(
    creds_json: str,
    gsheet_url: str,
    tabs: List[str],
    month_num: int,
    log_fn: Optional[Callable[[str], None]] = None
):
    client = _gsheet_call_with_retry(lambda: _get_gspread_client(creds_json), log_fn=log_fn)

    all_items = []
    stats_by_tab = {}
    month_header_used = MONTHS_ES.get(month_num, "")

    for t in tabs:
        items, st, mh = read_checked_centros_with_macro_from_tab(
            client, gsheet_url, t, month_num, log_fn=log_fn
        )
        stats_by_tab[t] = st
        month_header_used = mh or month_header_used
        all_items.extend(items)

    centros_map = {}
    dup_global = 0
    macro_conflict = 0

    for item in all_items:
        canon = _canon_code(item["centro"])
        if canon in centros_map:
            dup_global += 1
            if centros_map[canon]["macro"] != item["macro"]:
                macro_conflict += 1
            continue
        centros_map[canon] = item

    centros = list(centros_map.values())
    return centros, stats_by_tab, dup_global, macro_conflict, month_header_used




def _norm_cell(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().upper())


def _is_checked(v: str) -> bool:
    vv = _norm_cell(v)
    return vv in ("TRUE", "VERDADERO", "SI", "SÍ", "1", "X", "✔", "✅", "V")


def _find_col(headers_norm: List[str], candidates_norm: List[str]) -> int:
    cset = set(candidates_norm)
    for i, h in enumerate(headers_norm):
        if h in cset:
            return i
    return -1


def _canon_code(cod: str) -> str:
    cod = (cod or "").strip()
    if cod.isdigit():
        try:
            return str(int(cod))  # 039 y 39 => "39"
        except Exception:
            return cod
    return cod


def get_download_timeout_for_center(center_code: str, default_timeout: int) -> int:
    canon = _canon_code(center_code)

    # Centro pesado: 001
    if canon == "1":
        return max(default_timeout, 360)   # 6 minutos

    return default_timeout


def get_future_timeout_for_center(center_code: str, default_timeout: int) -> int:
    # colchón adicional para login, navegación, descarga y validación final
    return get_download_timeout_for_center(center_code, default_timeout) + 120


def format_exception_detail(e: Exception, max_len: int = 400) -> str:
    try:
        msg = " ".join(str(e).split())
    except Exception:
        msg = ""
    if not msg:
        return f"EXCEPTION:{type(e).__name__}"
    if len(msg) > max_len:
        msg = msg[:max_len] + "..."
    return f"EXCEPTION:{type(e).__name__}:{msg}"


def apply_driver_timeouts(driver, center_timeout: int, user: str, center_code: str) -> None:
    page_timeout = max(60, min(center_timeout, 180))
    script_timeout = max(30, min(center_timeout // 2 if center_timeout else 30, 90))
    try:
        driver.set_page_load_timeout(page_timeout)
        driver.set_script_timeout(script_timeout)
        print(
            f"INFO | DRIVER_TIMEOUTS | {user} | {center_code} | page={page_timeout} | script={script_timeout}",
            flush=True
        )
    except Exception as e:
        print(
            f"WARN | DRIVER_TIMEOUTS | {user} | {center_code} | {format_exception_detail(e)}",
            flush=True
        )


def _safe_log_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "unknown"))[:80]


def _tail_text(path: str, max_chars: int = 1200) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read()
        data = " ".join(data.split())
        if len(data) > max_chars:
            return "..." + data[-max_chars:]
        return data
    except Exception:
        return ""


def _chromedriver_log_path(user: str, center_code: str, startup_attempt: int) -> str:
    log_dir = os.path.join(get_chrome_tmp_root(), "chromedriver_logs")
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return os.path.join(
        log_dir,
        f"chromedriver_{ts}_{_safe_log_token(user)}_{_safe_log_token(center_code)}_{startup_attempt}.log"
    )


def create_webdriver_with_retry(chrome_options, user: str, center_code: str, startup_tries: int = 3):
    last_exc = None
    for startup_attempt in range(1, startup_tries + 1):
        if STOP_EVENT.is_set():
            raise RuntimeError("CANCELADO")

        log_path = _chromedriver_log_path(user, center_code, startup_attempt)

        with DRIVER_START_SEMAPHORE:
            try:
                driver = webdriver.Chrome(
                    options=chrome_options,
                    service=build_chrome_service(log_path=log_path)
                )
                if startup_attempt > 1:
                    print(
                        f"INFO | DRIVER_START_OK_AFTER_RETRY | {user} | {center_code} | startup_attempt={startup_attempt}",
                        flush=True
                    )
                return driver
            except Exception as e:
                last_exc = e
                detail = format_exception_detail(e)
                driver_log_tail = _tail_text(log_path)
                if driver_log_tail:
                    detail = f"{detail} | chromedriver_log={log_path} | tail={driver_log_tail}"
                else:
                    detail = f"{detail} | chromedriver_log={log_path}"
                print(
                    f"WARN | DRIVER_START_FAIL | {user} | {center_code} | startup_attempt={startup_attempt}/{startup_tries} | {detail}",
                    flush=True
                )

        if startup_attempt < startup_tries:
            time.sleep(min(10.0, 2.0 * startup_attempt + random.random()))

    if last_exc:
        raise last_exc
    raise RuntimeError("No se pudo iniciar ChromeDriver")


def preflight_chromedriver(download_dir_primary: str, headless: bool, summary_path: str) -> bool:
    profile_dir = ""
    driver = None
    try:
        chrome_options, profile_dir = build_chrome_options(
            download_dir_primary,
            headless=headless,
            worker_id="preflight"
        )
        driver = create_webdriver_with_retry(
            chrome_options=chrome_options,
            user="PREFLIGHT",
            center_code="CHROMEDRIVER",
            startup_tries=5
        )
        driver.get("about:blank")
        summary(summary_path, "CHROMEDRIVER_PREFLIGHT_OK")
        return True
    except Exception as e:
        summary(summary_path, f"CHROMEDRIVER_PREFLIGHT_FAIL | {format_exception_detail(e, max_len=1200)}")
        return False
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        unregister_active_driver(driver)
        try:
            if profile_dir:
                safe_rmtree(profile_dir)
                unregister_active_profile_dir(profile_dir)
        except Exception:
            pass


def _should_retry_gsheets(err: Exception) -> bool:
    msg = str(err)
    if isinstance(err, APIError):
        if any(code in msg for code in ("[429]", "[500]", "[502]", "[503]", "[504]")):
            return True
    if any(code in msg for code in (" 429", " 500", " 502", " 503", " 504", "429", "503")):
        return True
    return False


def _gsheet_call_with_retry(
    fn,
    log_fn: Optional[Callable[[str], None]] = None,
    max_tries: int = 8,
    base_sleep: float = 2.0,
    max_sleep: float = 60.0
):
    last = None
    for i in range(1, max_tries + 1):
        try:
            return fn()
        except Exception as e:
            last = e
            if not _should_retry_gsheets(e) or i == max_tries:
                raise
            sleep = min(max_sleep, base_sleep * (2 ** (i - 1)))
            sleep = sleep * (0.8 + random.random() * 0.4)  # jitter
            msg = f"GSHEET_RETRY | attempt={i}/{max_tries} | sleep={sleep:.1f}s | err={type(e).__name__}: {e}"
            if log_fn:
                log_fn(msg)
            else:
                print(msg, flush=True)
            time.sleep(sleep)
    raise last


def _get_gspread_client(creds_json: str):
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_json, scope)
    return gspread.authorize(creds)


def read_checked_codes_from_tab(
    client,
    gsheet_url: str,
    tab_name: str,
    month_num: int,
    log_fn: Optional[Callable[[str], None]] = None
) -> tuple[List[str], Dict[str, int], str]:
    month_header = MONTHS_ES.get(month_num, "")

    ws = _gsheet_call_with_retry(
        lambda: client.open_by_url(gsheet_url).worksheet(tab_name),
        log_fn=log_fn
    )
    values = _gsheet_call_with_retry(lambda: ws.get_all_values(), log_fn=log_fn)

    if not values:
        return [], {"selected": 0, "dup": 0, "unchecked": 0, "empty": 0}, month_header

    header = values[0]
    headers_norm = [_norm_cell(h) for h in header]

    idx_cod = _find_col(headers_norm, ["COD_IPRESS", "COD IPRESS", "CODIGO IPRESS", "CODIGO DE IPRESS"])
    if idx_cod < 0:
        for i, h in enumerate(headers_norm):
            if ("COD" in h and "IPRESS" in h) or h == "COD":
                idx_cod = i
                break
    if idx_cod < 0:
        raise RuntimeError(f"GSHEET | No se encontró columna COD_IPRESS en tab={tab_name}")

    month_candidates = MONTH_ALIASES.get(month_header, [month_header])
    idx_month = _find_col(headers_norm, [_norm_cell(x) for x in month_candidates])
    if idx_month < 0:
        raise RuntimeError(f"GSHEET | No se encontró columna mes '{month_header}' en tab={tab_name}")

    selected: List[str] = []
    seen: set = set()
    dup = 0
    unchecked = 0
    empty = 0

    for row in values[1:]:
        cod = (row[idx_cod] if idx_cod < len(row) else "").strip()
        if not cod:
            empty += 1
            continue

        month_val = (row[idx_month] if idx_month < len(row) else "")
        if not _is_checked(month_val):
            unchecked += 1
            continue

        canon = _canon_code(cod)
        if canon in seen:
            dup += 1
            continue

        seen.add(canon)
        selected.append(cod)

    return selected, {"selected": len(selected), "dup": dup, "unchecked": unchecked, "empty": empty}, month_header


def get_centros_merged_from_tabs_checked(
    creds_json: str,
    gsheet_url: str,
    tabs: List[str],
    month_num: int,
    log_fn: Optional[Callable[[str], None]] = None
) -> tuple[List[str], Dict[str, Dict[str, int]], int, str]:
    client = _gsheet_call_with_retry(lambda: _get_gspread_client(creds_json), log_fn=log_fn)

    all_codes: List[str] = []
    stats_by_tab: Dict[str, Dict[str, int]] = {}
    month_header_used = MONTHS_ES.get(month_num, "")

    for t in tabs:
        codes, st, mh = read_checked_codes_from_tab(client, gsheet_url, t, month_num, log_fn=log_fn)
        stats_by_tab[t] = st
        month_header_used = mh or month_header_used
        all_codes.extend(codes)

    centros_unicos: List[str] = []
    seen_global: set = set()
    dup_global = 0

    for c in all_codes:
        canon = _canon_code(c)
        if canon in seen_global:
            dup_global += 1
            continue
        seen_global.add(canon)
        centros_unicos.append(c.strip())

    return centros_unicos, stats_by_tab, dup_global, month_header_used


# =========================
# Limpieza previa (por TAG del día)
# =========================
def limpieza_previa_en_varias_rutas(
    download_dirs: List[str],
    centros_lista: List[str],
    tag: str,
    file_suffix: str = ""
) -> None:
    centros_unicos: List[str] = []
    seen = set()
    for c in (c.strip() for c in centros_lista if c and c.strip()):
        canon = _canon_code(c)
        if canon not in seen:
            centros_unicos.append(c)
            seen.add(canon)

    suf_low = (file_suffix or "").lower()

    for download_dir in download_dirs:
        deleted = 0
        errors = 0
        print(f"CLEAN_START | dir:{download_dir} | TAG:{tag} | total_centros:{len(centros_unicos)}", flush=True)
        try:
            files = [f for f in os.listdir(download_dir) if f.lower().endswith(".txt")]
        except Exception as e:
            print(f"CLEAN_ERR | READ_DIR | {download_dir} | {type(e).__name__}:{e}", flush=True)
            continue

        for centro in centros_unicos:
            prefix = f"{centro}_{tag}_"
            candidates = [f for f in files if f.startswith(prefix)]
            if suf_low:
                candidates = [f for f in candidates if f.lower().endswith(suf_low)]
            if not candidates:
                continue

            for fname in candidates:
                fpath = os.path.join(download_dir, fname)
                try:
                    os.remove(fpath)
                    deleted += 1
                    print(f"CLEAN_DELETE | dir:{download_dir} | {centro} | {fname}", flush=True)
                except Exception as e:
                    errors += 1
                    print(f"CLEAN_ERR | dir:{download_dir} | {centro} | {fname} | {type(e).__name__}:{e}", flush=True)

            files = [f for f in files if not f.startswith(prefix)]

        print(f"CLEAN_SUMMARY | dir:{download_dir} | deleted:{deleted} | errors:{errors}", flush=True)


# =========================
# Chrome options/service
# =========================
def get_chrome_tmp_root() -> str:
    tmp_root = os.getenv("CHROME_TMP_ROOT", "/home/cenate/rpa_cext_diario/tmp_chrome").strip()
    if not tmp_root:
        tmp_root = "/home/cenate/rpa_cext_diario/tmp_chrome"
    ensure_dir(tmp_root)
    return tmp_root


def cleanup_old_chrome_profiles(tmp_root: str, max_age_hours: int = 12) -> int:
    if not os.path.isdir(tmp_root):
        return 0

    now = time.time()
    limite = max_age_hours * 3600
    removed = 0

    for nombre in os.listdir(tmp_root):
        if not nombre.startswith("chrome-profile-"):
            continue

        path = os.path.join(tmp_root, nombre)
        if not os.path.isdir(path):
            continue

        try:
            edad = now - os.path.getmtime(path)
            if edad > limite:
                if safe_rmtree(path):
                    removed += 1
                    print(f"CLEANUP | TMP_PROFILE_OLD_REMOVED | {path}", flush=True)
        except Exception as e:
            print(f"WARN | TMP_PROFILE_CLEAN_FAIL | {path} | {type(e).__name__}:{e}", flush=True)

    return removed


def build_chrome_options(download_dir_primary: str, headless: bool, worker_id: str = "worker"):
    import tempfile

    chrome_options = Options()
    chrome_options.page_load_strategy = "eager"
    chrome_options.binary_location = "/usr/bin/chromium-browser"

    tmp_root = get_chrome_tmp_root()

    # perfil único por instancia para evitar choques entre hilos y controlar la limpieza
    profile_dir = tempfile.mkdtemp(prefix=f"chrome-profile-{worker_id}-", dir=tmp_root)
    register_active_profile_dir(profile_dir)
    print(f"INFO | TMP_ROOT | {tmp_root}", flush=True)
    print(f"INFO | TMP_PROFILE_CREATE | {profile_dir}", flush=True)
    chrome_options.add_argument(f"--user-data-dir={profile_dir}")

    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-features=Translate,BackForwardCache,OptimizationHints")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

    prefs = {
        "download.default_directory": download_dir_primary,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)

    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--remote-debugging-port=0")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--mute-audio")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")

    return chrome_options, profile_dir


def build_chrome_service(log_path: Optional[str] = None) -> ChromeService:
    service = ChromeService(executable_path="/usr/bin/chromedriver", log_output=log_path or os.devnull)
    try:
        import subprocess as _sp
        service.creationflags = _sp.CREATE_NO_WINDOW
    except Exception:
        pass
    return service


# =========================
# Replicación a espejos
# =========================
def replicar_a_espejos(src_fullpath: str, mirrors: List[str], nombre_archivo: str, tag: Optional[str] = None) -> None:
    if tag and f"_{tag}_" not in nombre_archivo:
        print(f"REPLICA_SKIP | tag mismatch | {nombre_archivo}", flush=True)
        return
    for mdir in mirrors:
        try:
            Path(mdir).mkdir(parents=True, exist_ok=True)
            dst = os.path.join(mdir, nombre_archivo)
            shutil.copy2(src_fullpath, dst)
            print(f"REPLICA_OK | {mdir} | {nombre_archivo}", flush=True)
        except Exception as e:
            print(f"REPLICA_ERR | {mdir} | {nombre_archivo} | {type(e).__name__}:{e}", flush=True)

def limpiar_publish_dir(final_dir: str, file_suffix: str = "") -> int:
    deleted = 0
    suf_low = (file_suffix or "").lower()

    try:
        for f in os.listdir(final_dir):
            low = f.lower()
            if not low.endswith(".txt"):
                continue
            if suf_low and not low.endswith(suf_low):
                continue
            try:
                os.remove(os.path.join(final_dir, f))
                deleted += 1
            except Exception:
                pass
    except Exception:
        pass

    return deleted


def publish_txts_to_final_dir(
    temp_dir: str,
    final_dir: str,
    tag: str,
    file_suffix: str,
    summary_path: str,
    db=None,
    run_db_id: Optional[int] = None
) -> bool:
    suf_low = (file_suffix or "").lower()

    try:
        if STOP_EVENT.is_set():
            emit_event(
                summary_path, db, run_db_id, "WARN", "FINAL_PUBLISH_SKIP",
                f"tag={tag} | cancelled before publish start"
            )
            return False

        files = []
        for f in os.listdir(temp_dir):
            low = f.lower()
            if not low.endswith(".txt"):
                continue
            if f"_{tag}_" not in f:
                continue
            if suf_low and not low.endswith(suf_low):
                continue
            files.append(f)

        files = sorted(files)

        if not files:
            emit_event(
                summary_path, db, run_db_id, "WARN", "FINAL_PUBLISH_SKIP",
                f"tag={tag} | no files found in temp_dir={temp_dir}"
            )
            return False

        final_dir = os.path.abspath(final_dir)
        parent_dir = os.path.dirname(final_dir)
        base_name = os.path.basename(final_dir.rstrip("/"))

        stage_dir = os.path.join(parent_dir, f".__stage_{base_name}_{tag}")
        backup_dir = os.path.join(parent_dir, f".__backup_{base_name}_{tag}")

        # limpieza previa de stage/backup viejos
        if os.path.isdir(stage_dir):
            shutil.rmtree(stage_dir, ignore_errors=True)
        if os.path.isdir(backup_dir):
            shutil.rmtree(backup_dir, ignore_errors=True)

        os.makedirs(stage_dir, exist_ok=True)

        # 1) copiar TODO al staging del compartido
        copied = 0
        for f in files:
            if STOP_EVENT.is_set():
                shutil.rmtree(stage_dir, ignore_errors=True)
                emit_event(
                    summary_path, db, run_db_id, "WARN", "FINAL_PUBLISH_CANCELLED",
                    f"tag={tag} | cancelled before swap | staged={copied}"
                )
                return False

            src = os.path.join(temp_dir, f)
            dst = os.path.join(stage_dir, f)
            shutil.copy2(src, dst)
            copied += 1

        stage_files = []
        for f in os.listdir(stage_dir):
            low = f.lower()
            if not low.endswith(".txt"):
                continue
            if f"_{tag}_" not in f:
                continue
            if suf_low and not low.endswith(suf_low):
                continue
            stage_files.append(f)

        if len(stage_files) != len(files):
            shutil.rmtree(stage_dir, ignore_errors=True)
            emit_event(
                summary_path, db, run_db_id, "ERROR", "FINAL_PUBLISH_FAIL",
                f"tag={tag} | staged files mismatch | temp_files={len(files)} | stage_files={len(stage_files)}"
            )
            return False

        # 2) swap rápido: final actual -> backup, stage -> final
        if os.path.isdir(final_dir):
            os.rename(final_dir, backup_dir)

        os.rename(stage_dir, final_dir)

        # 3) validar resultado final
        final_files = []
        for f in os.listdir(final_dir):
            low = f.lower()
            if not low.endswith(".txt"):
                continue
            if f"_{tag}_" not in f:
                continue
            if suf_low and not low.endswith(suf_low):
                continue
            final_files.append(f)

        ok = len(final_files) == len(files)

        emit_event(
            summary_path, db, run_db_id,
            "INFO" if ok else "WARN",
            "FINAL_PUBLISH_RESULT",
            f"tag={tag} | temp_files={len(files)} | staged={len(stage_files)} | final_files={len(final_files)} | dir={final_dir}"
        )

        # 4) si todo salió bien, borramos backup
        if ok and os.path.isdir(backup_dir):
            shutil.rmtree(backup_dir, ignore_errors=True)

        # 5) si salió mal, intentamos rollback
        if not ok:
            if os.path.isdir(final_dir):
                shutil.rmtree(final_dir, ignore_errors=True)
            if os.path.isdir(backup_dir):
                os.rename(backup_dir, final_dir)

        return ok

    except Exception as e:
        emit_event(
            summary_path, db, run_db_id, "ERROR", "FINAL_PUBLISH_FAIL",
            f"tag={tag} | dir={final_dir} | {type(e).__name__}: {e}"
        )
        return False

# =========================
# Descarga por centro (con force_redownload + suffix)
# =========================
def descargar_centro(
    center_code: str,
    user: str,
    password: str,
    fecha_ini_dmy: str,
    fecha_fin_dmy: str,
    tag: str,
    URL_HOME: str,
    URL_MASIVAS: str,
    DOWNLOAD_TIMEOUT: int,
    BETWEEN_CENTERS_DELAY: int,
    RETRY_PER_CENTER: int,
    DOWNLOAD_DIR_PRIMARY: str,
    DOWNLOAD_DIR_MIRRORS: List[str],
    headless: bool,
    force_redownload: bool,
    file_suffix: str
) -> Dict[str, str]:
    center_code = (center_code or "").strip()
    center_timeout = get_download_timeout_for_center(center_code, DOWNLOAD_TIMEOUT)

    res = {
        "centro": center_code,
        "status": "FAIL",
        "motivo": "DESCONOCIDO",
        "usuario": user,
        "archivo": "",
        "archivo_path": "",
        "archivo_size": 0
    }

    if STOP_EVENT.is_set():
        res["motivo"] = "CANCELADO"
        return res

    if not center_code:
        res["motivo"] = "VACIO"
        print(f"FAIL | {user} | {center_code or '-'} | {res['motivo']}", flush=True)
        return res

    if center_timeout != DOWNLOAD_TIMEOUT:
        print(f"SPECIAL_TIMEOUT | {user} | {center_code} | timeout={center_timeout}", flush=True)

    attempt_started_global = time.time()
    intentos = 0
    while intentos <= RETRY_PER_CENTER and not STOP_EVENT.is_set():
        intentos += 1
        attempt_started = time.time()
        driver = None
        profile_dir = ""

        try:
            worker_id = f"{user}_{center_code}".replace(" ", "_").replace("/", "_")
            chrome_options, profile_dir = build_chrome_options(
                DOWNLOAD_DIR_PRIMARY,
                headless=headless,
                worker_id=worker_id
            )
            driver = create_webdriver_with_retry(
                chrome_options=chrome_options,
                user=user,
                center_code=center_code,
                startup_tries=3
            )
            register_active_driver(driver)
            apply_driver_timeouts(driver, center_timeout, user, center_code)

            driver.get(URL_HOME)
            wait = WebDriverWait(driver, 20)

            # Login
            wait.until(EC.frame_to_be_available_and_switch_to_it("cuerpo"))
            wait.until(EC.presence_of_element_located((By.NAME, "USER"))).send_keys(user)
            driver.find_element(By.NAME, "PASS").send_keys(password)
            driver.find_element(By.NAME, "Submit").click()

            if STOP_EVENT.is_set():
                res["motivo"] = "CANCELADO"
                break

            # Centro
            wait.until(EC.frame_to_be_available_and_switch_to_it("cuerpo"))
            try:
                select = Select(wait.until(EC.presence_of_element_located((By.NAME, "centroAsistencial"))))
                select.select_by_value(center_code)
            except Exception:
                res["motivo"] = "NO_ENCONTRADO_EN_WEB"
                break

            wait.until(EC.element_to_be_clickable((By.NAME, "Submit"))).click()
            time.sleep(1)

            # Formulario
            driver.get(URL_MASIVAS)

            wait2 = WebDriverWait(driver, 25)
            wait2.until(EC.presence_of_element_located((By.ID, "fe_ini")))
            wait2.until(EC.presence_of_element_located((By.ID, "fechaFin")))

            driver.find_element(By.ID, "fe_ini").clear()
            driver.find_element(By.ID, "fe_ini").send_keys(fecha_ini_dmy)
            driver.find_element(By.ID, "fechaFin").clear()
            driver.find_element(By.ID, "fechaFin").send_keys(fecha_fin_dmy)

            wait2.until(EC.presence_of_element_located((By.ID, "formatoArchivo")))
            Select(driver.find_element(By.ID, "formatoArchivo")).select_by_value("xls")

            if STOP_EVENT.is_set():
                res["motivo"] = "CANCELADO"
                break

            prefix = _prefix_centro_tag(center_code, tag)

            if not force_redownload:
                ya = find_latest_final_by_tag(DOWNLOAD_DIR_PRIMARY, center_code, tag, file_suffix=file_suffix)
                if ya:
                    ya_path = os.path.join(DOWNLOAD_DIR_PRIMARY, ya)
                    parciales = [f for f in files_with_prefix(DOWNLOAD_DIR_PRIMARY, prefix)
                                 if f.lower().endswith((".crdownload", ".tmp", ".part"))]
                    if not parciales and file_is_stable(ya_path, 3) and f"_{tag}_" in ya:
                        if DOWNLOAD_DIR_MIRRORS:
                            replicar_a_espejos(ya_path, DOWNLOAD_DIR_MIRRORS, ya, tag)
                        res["status"] = "OK"
                        res["motivo"] = ""
                        res["archivo"] = ya
                        res["archivo_path"] = ya_path
                        try:
                            res["archivo_size"] = os.path.getsize(ya_path)
                        except Exception:
                            res["archivo_size"] = 0
                        break
            else:
                _ = delete_finals_with_prefix(DOWNLOAD_DIR_PRIMARY, prefix, file_suffix=file_suffix)
                for mdir in DOWNLOAD_DIR_MIRRORS:
                    _ = delete_finals_with_prefix(mdir, prefix, file_suffix=file_suffix)

            removed = remove_partial_with_prefix(DOWNLOAD_DIR_PRIMARY, prefix)
            if removed:
                print(f"PRETRY_SUM | removed:{removed} | {center_code} | {tag}", flush=True)

            wait2.until(EC.element_to_be_clickable((By.ID, "boton"))).click()

            archivo = esperar_descarga_por_prefijo(DOWNLOAD_DIR_PRIMARY, prefix, center_timeout, file_suffix=file_suffix)
            if not archivo:
                res["motivo"] = "TIMEOUT_DESCARGA_PREFIJO"
                continue

            if f"_{tag}_" not in archivo:
                res["motivo"] = "TAG_MISMATCH"
                continue
            if file_suffix and not archivo.lower().endswith(file_suffix.lower()):
                res["motivo"] = "SUFIJO_MISMATCH"
                continue

            archivo_path = os.path.join(DOWNLOAD_DIR_PRIMARY, archivo)
            if not file_is_stable(archivo_path, 3):
                res["motivo"] = "ARCHIVO_NO_ESTABLE"
                continue
            if archivo_esta_vacio(archivo_path):
                res["motivo"] = "ARCHIVO_VACIO"
                continue

            if DOWNLOAD_DIR_MIRRORS:
                replicar_a_espejos(archivo_path, DOWNLOAD_DIR_MIRRORS, archivo, tag)

            res["status"] = "OK"
            res["motivo"] = ""
            res["archivo"] = archivo
            res["archivo_path"] = archivo_path
            try:
                res["archivo_size"] = os.path.getsize(archivo_path)
            except Exception:
                res["archivo_size"] = 0
            break

        except Exception as e:
            res["motivo"] = format_exception_detail(e)

        finally:
            try:
                elapsed = round(time.time() - attempt_started, 1)
                print(
                    f"INFO | ATTEMPT_END | {user} | {center_code} | intento={intentos} | seconds={elapsed} | status={res.get('status')} | motivo={res.get('motivo','')}",
                    flush=True
                )
            except Exception:
                pass
            try:
                if driver:
                    driver.quit()
            except Exception as e:
                print(f"WARN | driver.quit falló | user:{user} | centro:{center_code} | {type(e).__name__}:{e}", flush=True)
            finally:
                unregister_active_driver(driver)

            try:
                if profile_dir:
                    deleted = safe_rmtree(profile_dir)
                    unregister_active_profile_dir(profile_dir)
                    if deleted:
                        print(f"INFO | TMP_PROFILE_DELETE | {profile_dir}", flush=True)
            except Exception as e:
                print(f"WARN | TMP_PROFILE_DELETE_UNEXPECTED | {profile_dir} | {type(e).__name__}:{e}", flush=True)

            for _ in range(BETWEEN_CENTERS_DELAY):
                if STOP_EVENT.is_set():
                    break
                time.sleep(1)

    try:
        total_elapsed = round(time.time() - attempt_started_global, 1)
        print(
            f"INFO | CENTER_END | {user} | {center_code} | seconds={total_elapsed} | status={res.get('status')} | motivo={res.get('motivo','')}",
            flush=True
        )
    except Exception:
        pass

    if res["status"] == "OK":
        print(f"OK | {res['usuario']} | {res['centro']} | {res['archivo']}", flush=True)
    else:
        print(f"FAIL | {res['usuario']} | {res['centro']} | {res['motivo']}", flush=True)

    return res



# =========================
# Ejecución por usuario (paralela) con timeout externo
# =========================

def ejecutar_descargas_por_usuario(
    centros_input: List[str],
    usuario_id: int,
    usuario: str,
    password: str,
    fecha_ini_dmy: str,
    fecha_fin_dmy: str,
    tag: str,
    URL_HOME: str,
    URL_MASIVAS: str,
    DOWNLOAD_TIMEOUT: int,
    BETWEEN_CENTERS_DELAY: int,
    RETRY_PER_CENTER: int,
    MAX_THREADS: int,
    DOWNLOAD_DIR_PRIMARY: str,
    DOWNLOAD_DIR_MIRRORS: List[str],
    headless: bool,
    force_redownload: bool,
    file_suffix: str
):
    print(f"\nUSER_START | {usuario_id} | {usuario} | total:{len(centros_input)}", flush=True)

    ok_centros: List[str] = []
    fail_centros: List[str] = []
    fail_motivo: Dict[str, List[str]] = defaultdict(list)
    resultados: List[Dict[str, str]] = []

    def task(code: str):
        if STOP_EVENT.is_set():
            return {
                "centro": code,
                "status": "FAIL",
                "motivo": "CANCELADO",
                "usuario": usuario,
                "archivo": "",
                "archivo_path": "",
                "archivo_size": 0
            }
        return descargar_centro(
            code, usuario, password,
            fecha_ini_dmy, fecha_fin_dmy, tag,
            URL_HOME, URL_MASIVAS,
            DOWNLOAD_TIMEOUT, BETWEEN_CENTERS_DELAY, RETRY_PER_CENTER,
            DOWNLOAD_DIR_PRIMARY, DOWNLOAD_DIR_MIRRORS,
            headless=headless,
            force_redownload=force_redownload,
            file_suffix=file_suffix
        )

    try:
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            future_to_code = {executor.submit(task, code): code for code in centros_input}

            for future in as_completed(future_to_code):
                if STOP_EVENT.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                code = future_to_code[future]
                try:
                    result = future.result(timeout=get_future_timeout_for_center(code, DOWNLOAD_TIMEOUT))
                except FutureTimeoutError:
                    result = {
                        "centro": code,
                        "status": "FAIL",
                        "motivo": "TIMEOUT",
                        "usuario": usuario,
                        "archivo": "",
                        "archivo_path": "",
                        "archivo_size": 0
                    }

                resultados.append(result)
                if result["status"] == "OK":
                    ok_centros.append(result["centro"])
                else:
                    fail_centros.append(result["centro"])
                    fail_motivo[result["motivo"]].append(result["centro"])

    except KeyboardInterrupt:
        STOP_EVENT.set()
        print("↩️  Interrupción detectada. Cancelando tareas pendientes…", flush=True)
        raise

    print(f"USER_SUMMARY | {usuario_id} | {usuario} | OK:{len(ok_centros)} | FAIL:{len(fail_centros)}", flush=True)
    if fail_centros:
        for motivo, lista in fail_motivo.items():
            print(f"USER_FAIL_DETAIL | {usuario_id} | {motivo} | {sorted(set(lista))}", flush=True)

    return ok_centros, fail_centros, resultados



def detect_login_status(page_source: str) -> tuple[str, str]:
    html = _norm_cell(page_source or "")

    patterns = [
        ("INVALID_PASSWORD", ["CONTRASEÑA INCORRECTA", "CLAVE INCORRECTA", "PASSWORD INCORRECT", "CREDENCIALES INVALIDAS", "CREDENCIALES INVÁLIDAS"]),
        ("USER_DISABLED", ["USUARIO DESACTIVADO", "USUARIO INACTIVO", "USUARIO BLOQUEADO", "USUARIO NO ACTIVO", "CUENTA DESHABILITADA"]),
        ("PASSWORD_EXPIRED", ["CAMBIAR SU CONTRASEÑA", "CLAVE EXPIRADA", "PASSWORD EXPIRED"]),
    ]

    for status, keys in patterns:
        for key in keys:
            if key in html:
                return status, key

    return "LOGIN_FAILED", "No se identificó mensaje específico"

def check_user_health(
    user: str,
    password: str,
    URL_HOME: str,
    DOWNLOAD_DIR_PRIMARY: str,
    headless: bool
) -> dict:
    driver = None
    profile_dir = ""

    try:
        worker_id = f"health_{user}".replace(" ", "_").replace("/", "_")
        chrome_options, profile_dir = build_chrome_options(
            DOWNLOAD_DIR_PRIMARY,
            headless=headless,
            worker_id=worker_id
        )
        driver = create_webdriver_with_retry(
            chrome_options=chrome_options,
            user=user,
            center_code="HEALTHCHECK",
            startup_tries=2
        )
        register_active_driver(driver)

        driver.get(URL_HOME)
        wait = WebDriverWait(driver, 20)

        wait.until(EC.frame_to_be_available_and_switch_to_it("cuerpo"))
        wait.until(EC.presence_of_element_located((By.NAME, "USER"))).send_keys(user)
        driver.find_element(By.NAME, "PASS").send_keys(password)
        driver.find_element(By.NAME, "Submit").click()

        try:
            driver.switch_to.default_content()
        except Exception:
            pass

        try:
            wait2 = WebDriverWait(driver, 10)
            wait2.until(EC.frame_to_be_available_and_switch_to_it("cuerpo"))
            wait2.until(EC.presence_of_element_located((By.NAME, "centroAsistencial")))
            return {"status": "OK", "detail": "Login correcto"}
        except Exception:
            pass

        try:
            html = driver.page_source
        except Exception:
            html = ""

        status, detail = detect_login_status(html)
        return {"status": status, "detail": detail}

    except Exception as e:
        return {"status": "LOGIN_FAILED_EXCEPTION", "detail": f"{type(e).__name__}:{e}"}

    finally:
        try:
            if driver:
                driver.quit()
        except Exception as e:
            print(f"WARN | driver.quit falló | healthcheck:{user} | {type(e).__name__}:{e}", flush=True)
        finally:
            unregister_active_driver(driver)

        try:
            if profile_dir:
                deleted = safe_rmtree(profile_dir)
                unregister_active_profile_dir(profile_dir)
                if deleted:
                    print(f"INFO | TMP_PROFILE_DELETE | {profile_dir}", flush=True)
        except Exception as e:
            print(f"WARN | TMP_PROFILE_DELETE_UNEXPECTED | {profile_dir} | {type(e).__name__}:{e}", flush=True)


def ejecutar_descargas_por_macro(
    centros_meta: List[Dict[str, str]],
    macro_users: Dict[str, Tuple[str, str]],
    fecha_ini_dmy: str,
    fecha_fin_dmy: str,
    tag: str,
    URL_HOME: str,
    URL_MASIVAS: str,
    DOWNLOAD_TIMEOUT: int,
    BETWEEN_CENTERS_DELAY: int,
    RETRY_PER_CENTER: int,
    MAX_THREADS: int,
    DOWNLOAD_DIR_PRIMARY: str,
    DOWNLOAD_DIR_MIRRORS: List[str],
    headless: bool,
    force_redownload: bool,
    file_suffix: str,
    summary_path: str,
    override_map: Optional[Dict[str, Dict[str, str]]] = None,
    db=None,
    run_uuid: str = "",
    run_db_id: Optional[int] = None
):
    override_map = override_map or {}

    resultados_todos: List[Dict[str, str]] = []
    ok_final: set = set()
    pendientes_fallback: List[Dict[str, str]] = []
    pendientes_primaria: List[Dict[str, str]] = []

    # Fase 0: overrides aprendidos
    for item in centros_meta:
        centro = item["centro"]
        macro_decl = item["macro"]
        ov = override_map.get(centro)

        if not ov:
            pendientes_primaria.append(item)
            continue

        macro_real = ov.get("macro_efectiva", "")
        if macro_real not in macro_users:
            summary(
                summary_path,
                f"OVERRIDE_INVALID | centro={centro} | macro_decl={macro_decl} | macro_real={macro_real} | vuelve_flujo_normal"
            )
            pendientes_primaria.append(item)
            continue

        user, password = macro_users[macro_real]

        summary(
            summary_path,
            f"OVERRIDE_START | centro={centro} | macro_decl={macro_decl} | macro_real={macro_real} | user={user}"
        )

        res = descargar_centro(
            center_code=centro,
            user=user,
            password=password,
            fecha_ini_dmy=fecha_ini_dmy,
            fecha_fin_dmy=fecha_fin_dmy,
            tag=tag,
            URL_HOME=URL_HOME,
            URL_MASIVAS=URL_MASIVAS,
            DOWNLOAD_TIMEOUT=DOWNLOAD_TIMEOUT,
            BETWEEN_CENTERS_DELAY=BETWEEN_CENTERS_DELAY,
            RETRY_PER_CENTER=RETRY_PER_CENTER,
            DOWNLOAD_DIR_PRIMARY=DOWNLOAD_DIR_PRIMARY,
            DOWNLOAD_DIR_MIRRORS=DOWNLOAD_DIR_MIRRORS,
            headless=headless,
            force_redownload=force_redownload,
            file_suffix=file_suffix
        )

        res["fase"] = "OVERRIDE"
        res["macro_objetivo"] = macro_decl
        res["macro_revalidacion"] = macro_real
        resultados_todos.append(res)

        if res["status"] == "OK":
            ok_final.add(centro)
            summary(
                summary_path,
                f"OVERRIDE_OK | centro={centro} | macro_decl={macro_decl} | macro_real={macro_real} | user={user}"
            )

            if db:
                try:
                    db.upsert_override(
                        codigo_centro=centro,
                        macro_declarada=macro_decl,
                        macro_efectiva=macro_real,
                        usuario_efectivo=user,
                        run_uuid=run_uuid,
                        fuente="AUTO"
                    )
                except Exception as e:
                    summary(summary_path, f"OVERRIDE_UPSERT_WARN | centro={centro} | {type(e).__name__}: {e}")
        else:
            summary(
                summary_path,
                f"OVERRIDE_FAIL | centro={centro} | motivo={res.get('motivo')} | vuelve_flujo_normal"
            )

            if db:
                try:
                    db.mark_override_failure(centro, str(res.get("motivo", "")))
                except Exception as e:
                    summary(summary_path, f"OVERRIDE_FAIL_WARN | centro={centro} | {type(e).__name__}: {e}")

            pendientes_primaria.append(item)

    # Primera pasada: cada macro con su usuario principal
    for macro in VALID_MACROS:
        centros_macro = [x["centro"] for x in pendientes_primaria if x["macro"] == macro]

        if not centros_macro:
            continue

        user, password = macro_users[macro]

        # Health check temporalmente desactivado para no bloquear la macro.
        health = {"status": "SKIPPED", "detail": "Health check temporalmente desactivado"}

        emit_event(
            summary_path,
            db,
            run_db_id,
            "INFO",
            "USER_HEALTH",
            f"macro={macro} | user={user} | status={health['status']} | detail={health['detail']}"
        )

        if db and run_db_id:
            try:
                db.upsert_user_health(
                    id_run=run_db_id,
                    run_uuid=run_uuid,
                    username=user,
                    macro_asignada=macro,
                    status=health["status"],
                    detail=health["detail"]
                )
            except Exception as e:
                summary(summary_path, f"USER_HEALTH_WARN | user={user} | {type(e).__name__}: {e}")

        summary(summary_path, f"MACRO_START | {macro} | user={user} | total={len(centros_macro)}")

        ok, fail, rep = ejecutar_descargas_por_usuario(
            centros_input=centros_macro,
            usuario_id=100 + VALID_MACROS.index(macro),
            usuario=user,
            password=password,
            fecha_ini_dmy=fecha_ini_dmy,
            fecha_fin_dmy=fecha_fin_dmy,
            tag=tag,
            URL_HOME=URL_HOME,
            URL_MASIVAS=URL_MASIVAS,
            DOWNLOAD_TIMEOUT=DOWNLOAD_TIMEOUT,
            BETWEEN_CENTERS_DELAY=BETWEEN_CENTERS_DELAY,
            RETRY_PER_CENTER=RETRY_PER_CENTER,
            MAX_THREADS=MAX_THREADS,
            DOWNLOAD_DIR_PRIMARY=DOWNLOAD_DIR_PRIMARY,
            DOWNLOAD_DIR_MIRRORS=DOWNLOAD_DIR_MIRRORS,
            headless=headless,
            force_redownload=force_redownload,
            file_suffix=file_suffix
        )

        for r in rep:
            r["fase"] = "PRIMARIA"
            r["macro_objetivo"] = macro

        resultados_todos.extend(rep)
        ok_final.update(ok)

        for r in rep:
            motivo = str(r.get("motivo", ""))

            if r.get("status") != "OK":
                if motivo == "NO_ENCONTRADO_EN_WEB":
                    pendientes_fallback.append({
                        "centro": r["centro"],
                        "macro_objetivo": macro,
                        "motivo_original": motivo,
                        "retry_same_macro": False,
                        "allow_override_learn": True
                    })

                elif (
                    motivo in ("TIMEOUT_DESCARGA_PREFIJO", "ARCHIVO_NO_ESTABLE", "ARCHIVO_VACIO")
                    or motivo.startswith("EXCEPTION:")
                ):
                    pendientes_fallback.append({
                        "centro": r["centro"],
                        "macro_objetivo": macro,
                        "motivo_original": motivo,
                        "retry_same_macro": True,
                        "allow_override_learn": False
                    })

        summary(summary_path, f"MACRO_END | {macro} | OK={len(ok)} | FAIL={len(fail)}")

    # Centros sin macro válida -> van directo a fallback.
    centros_sin_macro = [x["centro"] for x in pendientes_primaria if x["macro"] == INVALID_MACRO_LABEL]

    for centro in centros_sin_macro:
        if centro not in ok_final:
            pendientes_fallback.append({
                "centro": centro,
                "macro_objetivo": INVALID_MACRO_LABEL,
                "motivo_original": "SIN_MACRO",
                "retry_same_macro": False,
                "allow_override_learn": True
            })

    if centros_sin_macro:
        summary(summary_path, f"SIN_MACRO_QUEUE | total={len(centros_sin_macro)} | centros={centros_sin_macro}")

    # Segunda pasada: fallback controlado
    summary(summary_path, f"FALLBACK_START | total={len(pendientes_fallback)}")

    for item in pendientes_fallback:
        centro = item["centro"]
        macro_origen = item["macro_objetivo"]
        motivo_original = str(item.get("motivo_original", ""))
        retry_same_macro = bool(item.get("retry_same_macro", False))
        allow_override_learn = bool(item.get("allow_override_learn", False))

        if centro in ok_final:
            continue

        # 1) Si el error original fue técnico, reintenta primero con la MISMA macro.
        # Ejemplo: WebDriverException en NORTE debe reintentar NORTE antes de probar otras macros.
        if retry_same_macro and macro_origen in VALID_MACROS:
            user_same, password_same = macro_users[macro_origen]

            summary(
                summary_path,
                f"RETRY_SAME_MACRO_START | centro={centro} | macro={macro_origen} | user={user_same} | motivo_original={motivo_original}"
            )

            try:
                with ThreadPoolExecutor(max_workers=1) as retry_executor:
                    fut_same = retry_executor.submit(
                        descargar_centro,
                        center_code=centro,
                        user=user_same,
                        password=password_same,
                        fecha_ini_dmy=fecha_ini_dmy,
                        fecha_fin_dmy=fecha_fin_dmy,
                        tag=tag,
                        URL_HOME=URL_HOME,
                        URL_MASIVAS=URL_MASIVAS,
                        DOWNLOAD_TIMEOUT=DOWNLOAD_TIMEOUT,
                        BETWEEN_CENTERS_DELAY=BETWEEN_CENTERS_DELAY,
                        RETRY_PER_CENTER=0,
                        DOWNLOAD_DIR_PRIMARY=DOWNLOAD_DIR_PRIMARY,
                        DOWNLOAD_DIR_MIRRORS=DOWNLOAD_DIR_MIRRORS,
                        headless=headless,
                        force_redownload=force_redownload,
                        file_suffix=file_suffix
                    )
                    res_same = fut_same.result(timeout=get_future_timeout_for_center(centro, DOWNLOAD_TIMEOUT))
            except FutureTimeoutError:
                cleanup_active_browser_resources()
                res_same = {
                    "centro": centro,
                    "status": "FAIL",
                    "motivo": "TIMEOUT_RETRY_SAME_MACRO",
                    "usuario": user_same,
                    "archivo": "",
                    "archivo_path": "",
                    "archivo_size": 0
                }

            res_same["fase"] = "RETRY_SAME_MACRO"
            res_same["macro_objetivo"] = macro_origen
            res_same["macro_revalidacion"] = macro_origen
            resultados_todos.append(res_same)

            if res_same["status"] == "OK":
                ok_final.add(centro)
                summary(
                    summary_path,
                    f"RETRY_SAME_MACRO_OK | centro={centro} | macro={macro_origen} | user={user_same} | motivo_original={motivo_original}"
                )
                continue

            summary(
                summary_path,
                f"RETRY_SAME_MACRO_FAIL | centro={centro} | macro={macro_origen} | motivo={res_same.get('motivo')} | motivo_original={motivo_original}"
            )

        # 2) Si no salió con la misma macro, recién probamos otras.
        macros_a_probar = list(VALID_MACROS)

        if macro_origen in VALID_MACROS:
            macros_a_probar = [m for m in VALID_MACROS if m != macro_origen]

        for alt_macro in macros_a_probar:
            user, password = macro_users[alt_macro]

            try:
                with ThreadPoolExecutor(max_workers=1) as fallback_executor:
                    fut = fallback_executor.submit(
                        descargar_centro,
                        center_code=centro,
                        user=user,
                        password=password,
                        fecha_ini_dmy=fecha_ini_dmy,
                        fecha_fin_dmy=fecha_fin_dmy,
                        tag=tag,
                        URL_HOME=URL_HOME,
                        URL_MASIVAS=URL_MASIVAS,
                        DOWNLOAD_TIMEOUT=DOWNLOAD_TIMEOUT,
                        BETWEEN_CENTERS_DELAY=BETWEEN_CENTERS_DELAY,
                        RETRY_PER_CENTER=0,
                        DOWNLOAD_DIR_PRIMARY=DOWNLOAD_DIR_PRIMARY,
                        DOWNLOAD_DIR_MIRRORS=DOWNLOAD_DIR_MIRRORS,
                        headless=headless,
                        force_redownload=force_redownload,
                        file_suffix=file_suffix
                    )
                    res = fut.result(timeout=get_future_timeout_for_center(centro, DOWNLOAD_TIMEOUT))
            except FutureTimeoutError:
                cleanup_active_browser_resources()
                res = {
                    "centro": centro,
                    "status": "FAIL",
                    "motivo": "TIMEOUT_FALLBACK",
                    "usuario": user,
                    "archivo": "",
                    "archivo_path": "",
                    "archivo_size": 0
                }

            res["fase"] = "FALLBACK"
            res["macro_objetivo"] = macro_origen
            res["macro_revalidacion"] = alt_macro
            resultados_todos.append(res)

            if res["status"] == "OK":
                ok_final.add(centro)
                summary(
                    summary_path,
                    f"FALLBACK_OK | centro={centro} | macro_origen={macro_origen} | macro_real={alt_macro} | user={user}"
                )

                if db and allow_override_learn:
                    try:
                        db.upsert_override(
                            codigo_centro=centro,
                            macro_declarada=macro_origen,
                            macro_efectiva=alt_macro,
                            usuario_efectivo=user,
                            run_uuid=run_uuid,
                            fuente="AUTO"
                        )
                        summary(
                            summary_path,
                            f"OVERRIDE_LEARNED | centro={centro} | macro_decl={macro_origen} | macro_real={alt_macro} | user={user}"
                        )
                    except Exception as e:
                        summary(
                            summary_path,
                            f"OVERRIDE_LEARN_WARN | centro={centro} | {type(e).__name__}: {e}"
                        )
                else:
                    summary(
                        summary_path,
                        f"OVERRIDE_SKIP | centro={centro} | motivo_original={motivo_original} | macro_real={alt_macro}"
                    )

                break

    centros_input_ordenado = [x["centro"] for x in centros_meta]
    descargados_total_ordenado = [c for c in centros_input_ordenado if c in ok_final]
    centros_pendientes_ordenado = [c for c in centros_input_ordenado if c not in ok_final]

    summary(
        summary_path,
        f"FALLBACK_END | OK_TOTAL={len(descargados_total_ordenado)} | FAIL_TOTAL={len(centros_pendientes_ordenado)}"
    )

    return descargados_total_ordenado, centros_pendientes_ordenado, resultados_todos


# =========================
# Config desde .env
# =========================
def load_config_from_env() -> dict:
    env_file = os.getenv("ENV_FILE", ".env")
    load_dotenv(env_file)

    # Legacy: se deja por compatibilidad, pero ya no es obligatorio
    usuarios: List[Tuple[int, str, str]] = []
    for i in range(1, 51):
        u = _env_str(f"USER_{i}", "")
        p = _env_str(f"PASSWORD_{i}", "")
        if u and p:
            usuarios.append((i, u, p))

    URL_HOME = _env_str("URL_HOME")
    URL_MASIVAS = _env_str("FRM_MASIVAS")

    DOWNLOAD_DIRS_ENV = _env_str("DOWNLOAD_DIRS", "")
    DOWNLOAD_DIR_LEGACY = _env_str("DOWNLOAD_DIR", "")
    FINAL_PUBLISH_DIR = _env_str("FINAL_PUBLISH_DIR", "")

    GSHEET_URL = _env_str("GSHEET_URL")
    CREDS_JSON = _env_str("CREDS_JSON")

    # Tabs múltiples (mismo spreadsheet) -> aceptamos GSHEET_TABS o GSHEET_TAB
    tabs_raw = _env_str("GSHEET_TABS", "")
    if not tabs_raw:
        tabs_raw = _env_str("GSHEET_TAB", "")
    GSHEET_TABS = [t.strip() for t in tabs_raw.split(",") if t.strip()]

    DOWNLOAD_TIMEOUT = _env_int("DOWNLOAD_TIMEOUT", "1500")
    BETWEEN_CENTERS_DELAY = _env_int("BETWEEN_CENTERS_DELAY", "2")
    RETRY_PER_CENTER = _env_int("RETRY_PER_CENTER", "1")
    MAX_THREADS = _env_int("MAX_THREADS", "6")

    # Logs
    LOGS_DIR = _env_str("LOGS_DIR", "logs")
    RUN_NAME = _env_str("RUN_NAME", "CEXT_PROD_DIARIO")
    LOG_RETENTION_DAYS = _env_int("LOG_RETENTION_DAYS", "14")

    # Diario
    DATE_OFFSET_DAYS = _env_int("DATE_OFFSET_DAYS", "0")          # inicio relativo
    END_OFFSET_DAYS = _env_int("END_OFFSET_DAYS", str(DATE_OFFSET_DAYS))  # fin relativo
    SPECIAL_END_OFFSET_DAYS = _env_int("SPECIAL_END_OFFSET_DAYS", "3")
    SPECIAL_RANGE_WEEKDAYS_RAW = _env_str("SPECIAL_RANGE_WEEKDAYS", "4")
    SPECIAL_RANGE_WEEKDAYS = []
    if SPECIAL_RANGE_WEEKDAYS_RAW:
        for part in SPECIAL_RANGE_WEEKDAYS_RAW.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                n = int(part)
                if 0 <= n <= 6:
                    SPECIAL_RANGE_WEEKDAYS.append(n)
            except Exception:
                pass

    FORCE_REDOWNLOAD = _env_bool("FORCE_REDOWNLOAD", "true")
    FILE_SUFFIX = _env_str("FILE_SUFFIX", "PacCitCExt.txt")
    KEEP_ONLY_CURRENT_TAG = _env_bool("KEEP_ONLY_CURRENT_TAG", "true")

    # Temporales Chrome controlados
    CHROME_TMP_ROOT = _env_str("CHROME_TMP_ROOT", "/home/cenate/rpa_cext_diario/tmp_chrome")
    CHROME_TMP_RETENTION_HOURS = _env_int("CHROME_TMP_RETENTION_HOURS", "12")
    MAX_CONCURRENT_DRIVER_STARTS = _env_int("MAX_CONCURRENT_DRIVER_STARTS", "2")

    # Selenium
    HEADLESS = _env_bool("HEADLESS", "true")

    # Usuarios por macro
    USER_CENTRO = _env_str("USER_CENTRO", "")
    PASSWORD_CENTRO = _env_str("PASSWORD_CENTRO", "")

    USER_NORTE = _env_str("USER_NORTE", "")
    PASSWORD_NORTE = _env_str("PASSWORD_NORTE", "")

    USER_SUR = _env_str("USER_SUR", "")
    PASSWORD_SUR = _env_str("PASSWORD_SUR", "")

    USER_LIMA_ORIENTE = _env_str("USER_LIMA_ORIENTE", "")
    PASSWORD_LIMA_ORIENTE = _env_str("PASSWORD_LIMA_ORIENTE", "")

    # PostgreSQL / control
    PG_HOST = _env_str("PG_HOST", "")
    PG_PORT = _env_int("PG_PORT", "5432")
    PG_DATABASE = _env_str("PG_DATABASE", "")
    PG_USER = _env_str("PG_USER", "")
    PG_PASSWORD = _env_str("PG_PASSWORD", "")

    SRC241_HOST = _env_str("SRC241_HOST", "")
    SRC241_PORT = _env_int("SRC241_PORT", "5432")
    SRC241_DATABASE = _env_str("SRC241_DATABASE", "")
    SRC241_USER = _env_str("SRC241_USER", "")
    SRC241_PASSWORD = _env_str("SRC241_PASSWORD", "")

    RPA_JOB_CODE = _env_str("RPA_JOB_CODE", "CEXT_PROD_DIARIO")
    RPA_JOB_NAME = _env_str("RPA_JOB_NAME", "RPA Consulta Externa Producción Diario")
    RPA_RUN_TYPE = _env_str("RPA_RUN_TYPE", "DIARIO")
    RPA_FAIL_IF_DB_DOWN = _env_bool("RPA_FAIL_IF_DB_DOWN", "true")

    # Envío de correo
    MAIL_ENABLED = _env_bool("MAIL_ENABLED", "false")
    SMTP_HOST = _env_str("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = _env_int("SMTP_PORT", "587")
    SMTP_USER = _env_str("SMTP_USER", "")
    SMTP_PASS = _env_str("SMTP_PASS", "")
    SMTP_FROM = _env_str("SMTP_FROM", SMTP_USER)
    SMTP_TO_RAW = _env_str("SMTP_TO", "")
    SMTP_TO = [x.strip() for x in SMTP_TO_RAW.split(",") if x.strip()]

    def parse_download_dirs() -> List[str]:
        if DOWNLOAD_DIRS_ENV:
            dirs = [d.strip() for d in DOWNLOAD_DIRS_ENV.split(",") if d.strip()]
            if not dirs:
                raise RuntimeError("DOWNLOAD_DIRS está vacío tras parseo.")
            return dirs
        if DOWNLOAD_DIR_LEGACY:
            return [DOWNLOAD_DIR_LEGACY.strip()]
        raise RuntimeError("Falta DOWNLOAD_DIRS o DOWNLOAD_DIR en .env")

    DOWNLOAD_DIR_LIST = parse_download_dirs()
    DOWNLOAD_DIR_PRIMARY = DOWNLOAD_DIR_LIST[0]
    DOWNLOAD_DIR_MIRRORS = DOWNLOAD_DIR_LIST[1:]

    for d in DOWNLOAD_DIR_LIST:
        os.makedirs(d, exist_ok=True)
        os.makedirs(FINAL_PUBLISH_DIR, exist_ok=True)

    os.makedirs(CHROME_TMP_ROOT, exist_ok=True)

    faltan = []
    for k, v in [
        ("URL_HOME", URL_HOME),
        ("FRM_MASIVAS", URL_MASIVAS),
        ("GSHEET_URL", GSHEET_URL),
        ("CREDS_JSON", CREDS_JSON),
    ("FINAL_PUBLISH_DIR", FINAL_PUBLISH_DIR),
        ("PG_HOST", PG_HOST),
        ("PG_DATABASE", PG_DATABASE),
        ("PG_USER", PG_USER),
        ("PG_PASSWORD", PG_PASSWORD),
        ("SRC241_HOST", SRC241_HOST),
        ("SRC241_DATABASE", SRC241_DATABASE),
        ("SRC241_USER", SRC241_USER),
        ("SRC241_PASSWORD", SRC241_PASSWORD),
    ]:
        if not v:
            faltan.append(k)

    if len(GSHEET_TABS) == 0:
        faltan.append("GSHEET_TABS o GSHEET_TAB (con 2 tabs separadas por coma)")

    macro_users = {
        "CENTRO": (USER_CENTRO, PASSWORD_CENTRO),
        "NORTE": (USER_NORTE, PASSWORD_NORTE),
        "SUR": (USER_SUR, PASSWORD_SUR),
        "LIMA ORIENTE": (USER_LIMA_ORIENTE, PASSWORD_LIMA_ORIENTE),
    }

    for macro, creds in macro_users.items():
        if not creds[0] or not creds[1]:
            faltan.append(f"credenciales macro {macro}")

    if faltan:
        raise RuntimeError(f"Faltan variables en .env: {faltan}")

    return {
        "usuarios": usuarios,  # legado
        "MACRO_USERS": macro_users,

        "URL_HOME": URL_HOME,
        "URL_MASIVAS": URL_MASIVAS,

        "DOWNLOAD_DIR_LIST": DOWNLOAD_DIR_LIST,
        "DOWNLOAD_DIR_PRIMARY": DOWNLOAD_DIR_PRIMARY,
        "DOWNLOAD_DIR_MIRRORS": DOWNLOAD_DIR_MIRRORS,

        "GSHEET_URL": GSHEET_URL,
        "CREDS_JSON": CREDS_JSON,
        "FINAL_PUBLISH_DIR": FINAL_PUBLISH_DIR,
        "GSHEET_TABS": GSHEET_TABS,

        "DOWNLOAD_TIMEOUT": int(DOWNLOAD_TIMEOUT),
        "BETWEEN_CENTERS_DELAY": int(BETWEEN_CENTERS_DELAY),
        "RETRY_PER_CENTER": int(RETRY_PER_CENTER),
        "MAX_THREADS": int(MAX_THREADS),

        "LOGS_DIR": LOGS_DIR,
        "RUN_NAME": RUN_NAME,
        "LOG_RETENTION_DAYS": int(LOG_RETENTION_DAYS),

    "DATE_OFFSET_DAYS": int(DATE_OFFSET_DAYS),
    "END_OFFSET_DAYS": int(END_OFFSET_DAYS),
    "SPECIAL_END_OFFSET_DAYS": int(SPECIAL_END_OFFSET_DAYS),
    "SPECIAL_RANGE_WEEKDAYS": SPECIAL_RANGE_WEEKDAYS,
    "FORCE_REDOWNLOAD": bool(FORCE_REDOWNLOAD),
        "FILE_SUFFIX": FILE_SUFFIX,
        "HEADLESS": bool(HEADLESS),
        "KEEP_ONLY_CURRENT_TAG": bool(KEEP_ONLY_CURRENT_TAG),
        "CHROME_TMP_ROOT": CHROME_TMP_ROOT,
        "CHROME_TMP_RETENTION_HOURS": int(CHROME_TMP_RETENTION_HOURS),
        "MAX_CONCURRENT_DRIVER_STARTS": int(MAX_CONCURRENT_DRIVER_STARTS),

        "PG_HOST": PG_HOST,
        "PG_PORT": int(PG_PORT),
        "PG_DATABASE": PG_DATABASE,
        "PG_USER": PG_USER,
        "PG_PASSWORD": PG_PASSWORD,

    "SRC241_HOST": SRC241_HOST,
    "SRC241_PORT": int(SRC241_PORT),
    "SRC241_DATABASE": SRC241_DATABASE,
    "SRC241_USER": SRC241_USER,
    "SRC241_PASSWORD": SRC241_PASSWORD,

        "MAIL_ENABLED": MAIL_ENABLED,
        "SMTP_HOST": SMTP_HOST,
        "SMTP_PORT": SMTP_PORT,
        "SMTP_USER": SMTP_USER,
        "SMTP_PASS": SMTP_PASS,
        "SMTP_FROM": SMTP_FROM,
        "SMTP_TO": SMTP_TO,

        "RPA_JOB_CODE": RPA_JOB_CODE,
        "RPA_JOB_NAME": RPA_JOB_NAME,
        "RPA_RUN_TYPE": RPA_RUN_TYPE,
        "RPA_FAIL_IF_DB_DOWN": bool(RPA_FAIL_IF_DB_DOWN),
    }



def build_run_email_body_diario(
    run_uuid: str,
    final_status: str,
    fecha_operativa: str,
    fecha_futuro_fin: str,
    start_dt,
    end_dt,
    dur: float,
    total_input: int,
    total_ok: int,
    total_fail: int,
    failed_centros,
    resultados_todos,
    final_publish_ok: bool,
    refresh_diario_ok: bool,
    report_pendientes_ok: bool,
    report_futuro_ok: bool,
    failure_stage: str,
    failure_detail: str,
    attachment_label: str,
) -> str:
    fail_by_user = {}
    fail_by_reason = {}
    fail_by_phase = {}

    retry_same_ok = 0
    fallback_ok = 0
    override_ok = 0

    for item in resultados_todos or []:
        fase = str(item.get("fase") or "N/A").strip()
        status = str(item.get("status") or "").strip()

        if status == "OK":
            if fase == "RETRY_SAME_MACRO":
                retry_same_ok += 1
            elif fase == "FALLBACK":
                fallback_ok += 1
            elif fase == "OVERRIDE":
                override_ok += 1
            continue

        user = str(item.get("usuario") or "N/A").strip()
        reason = str(item.get("motivo") or "SIN_MOTIVO").strip()

        fail_by_user[user] = fail_by_user.get(user, 0) + 1
        fail_by_reason[reason] = fail_by_reason.get(reason, 0) + 1
        fail_by_phase[fase] = fail_by_phase.get(fase, 0) + 1

    user_lines = "\n".join(
        [f"  - {k}: {v}" for k, v in sorted(fail_by_user.items(), key=lambda x: (-x[1], x[0]))]
    ) or "  - Sin fallas por usuario"

    reason_lines = "\n".join(
        [f"  - {k}: {v}" for k, v in sorted(fail_by_reason.items(), key=lambda x: (-x[1], x[0]))]
    ) or "  - Sin fallas por motivo"

    phase_lines = "\n".join(
        [f"  - {k}: {v}" for k, v in sorted(fail_by_phase.items(), key=lambda x: (-x[1], x[0]))]
    ) or "  - Sin fallas por fase"

    failed_centros_text = ", ".join(failed_centros[:80]) if failed_centros else "Ninguna"
    if failed_centros and len(failed_centros) > 80:
        failed_centros_text += f" ... (+{len(failed_centros) - 80} más)"

    body = [
        "Buen día,",
        "",
        "Se informa el resultado de la ejecución del RPA Consulta Externa Producción Diario.",
        "",
        f"Estado: {final_status}",
        f"Fecha operativa: {fecha_operativa or 'N/A'}",
        f"Fecha futuro fin: {fecha_futuro_fin or 'N/A'}",
        f"Run UUID: {run_uuid}",
        f"Inicio: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Fin: {end_dt.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Duración (s): {dur:.1f}",
        "",
        f"Total input: {total_input}",
        f"Total OK: {total_ok}",
        f"Total FAIL: {total_fail}",
        "",
        "Estado de procesos complementarios:",
        f"  - Publicación final: {'OK' if final_publish_ok else 'NO_OK'}",
        f"  - Refresh reportes diario: {'OK' if refresh_diario_ok else 'NO_OK'}",
        f"  - Reporte pendientes del día: {'OK' if report_pendientes_ok else 'NO_OK'}",
        f"  - Reporte citados futuro: {'OK' if report_futuro_ok else 'NO_OK'}",
        "",
        "Recuperaciones:",
        f"  - Overrides OK: {override_ok}",
        f"  - Retry misma macro OK: {retry_same_ok}",
        f"  - Fallback OK: {fallback_ok}",
        "",
    ]

    if final_status != "SUCCESS":
        body.extend([
            f"Etapa de falla: {failure_stage or 'NO_IDENTIFICADA'}",
            f"Detalle técnico: {failure_detail or 'Sin detalle'}",
            "",
        ])

    body.extend([
        "IPRESS fallidas:",
        f"  - {failed_centros_text}",
        "",
        "Fallas por usuario:",
        user_lines,
        "",
        "Fallas por motivo:",
        reason_lines,
        "",
        "Fallas por fase:",
        phase_lines,
        "",
        f"Archivo adjunto: {attachment_label}",
        "",
        "Saludos.",
    ])

    return "\n".join(body)


def derive_final_status(
    *,
    overall_exit: int,
    total_ok: int,
    total_fail: int,
    final_publish_ok: bool,
    refresh_diario_ok: bool,
    report_pendientes_ok: bool,
    report_futuro_ok: bool,
) -> str:
    if overall_exit == 130:
        return "CANCELLED"

    if overall_exit != 0:
        return "FAILED"

    if total_ok == 0 and total_fail > 0:
        return "FAILED"

    if not final_publish_ok:
        return "FAILED"

    if total_ok > 0 and (
        total_fail > 0
        or not refresh_diario_ok
        or not report_pendientes_ok
        or not report_futuro_ok
    ):
        return "PARTIAL_SUCCESS"

    return "SUCCESS"


# =========================
# MAIN (DIARIO: HOY/AYER con offset) + checks + merge + limpieza
# =========================
def main():
    try:
        cfg = load_config_from_env()
    except Exception as e:
        print(f"❌ CONFIG_ERROR | {type(e).__name__}: {e}", flush=True)
        sys.exit(1)

    set_driver_start_limit(cfg.get("MAX_CONCURRENT_DRIVER_STARTS", 2))

    start_dt = datetime.datetime.now()

    # ===== Defaults de seguridad para errores tempranos =====
    end_dt = start_dt
    dur = 0.0

    overall_exit = 1
    final_status = "RUNNING"

    fecha_operativa_mail = ""
    fecha_futuro_fin_mail = ""

    centros_meta = []
    resultados_todos = []
    descargados_total_ordenado = []
    centros_pendientes_ordenado = []

    final_publish_ok = False
    refresh_diario_ok = False
    report_pendientes_ok = False
    report_futuro_ok = False
    failure_stage = ""
    failure_detail = ""

    run_log_path = ""
    summary_path = ""
    # ==========================================

    logs_dir = cfg["LOGS_DIR"]
    run_name = cfg["RUN_NAME"]
    retention_days = cfg["LOG_RETENTION_DAYS"]

    ensure_dir(logs_dir)

    run_id = f"RUN_{run_name}_{ts_now()}"
    run_dir = os.path.join(logs_dir, run_id)
    ensure_dir(run_dir)

    run_log_path = os.path.join(run_dir, "run.log")
    summary_path = os.path.join(run_dir, "summary.log")

    run_log_f = open(run_log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = TeeWriter(sys.stdout, run_log_f)
    sys.stderr = TeeWriter(sys.stderr, run_log_f)

    removed = cleanup_old_run_dirs(logs_dir, run_prefix=f"RUN_{run_name}_", retention_days=retention_days)
    if removed:
        summary(summary_path, f"LOG_RETENTION | removed_dirs={removed} | days={retention_days}")

    summary(summary_path, "RUN_START")
    summary(summary_path, f"RUN_DIR | {run_dir}")
    summary(summary_path, f"LOGFILE | {run_log_path}")
    summary(summary_path, f"Fecha inicio | {start_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    summary(summary_path, "MODE | DAILY")
    summary(summary_path, f"FORCE_REDOWNLOAD | {cfg['FORCE_REDOWNLOAD']}")
    summary(summary_path, f"FILE_SUFFIX | {cfg['FILE_SUFFIX']}")
    summary(summary_path, f"KEEP_ONLY_CURRENT_TAG | {cfg['KEEP_ONLY_CURRENT_TAG']}")
    summary(summary_path, f"CHROME_TMP_ROOT | {cfg['CHROME_TMP_ROOT']}")
    summary(summary_path, f"CHROME_TMP_RETENTION_HOURS | {cfg['CHROME_TMP_RETENTION_HOURS']}")
    summary(summary_path, f"MAX_CONCURRENT_DRIVER_STARTS | {cfg['MAX_CONCURRENT_DRIVER_STARTS']}")

    usuarios = cfg["usuarios"]
    URL_HOME = cfg["URL_HOME"]
    URL_MASIVAS = cfg["URL_MASIVAS"]
    DOWNLOAD_DIR_LIST = cfg["DOWNLOAD_DIR_LIST"]
    DOWNLOAD_DIR_PRIMARY = cfg["DOWNLOAD_DIR_PRIMARY"]
    DOWNLOAD_DIR_MIRRORS = cfg["DOWNLOAD_DIR_MIRRORS"]
    FINAL_PUBLISH_DIR = cfg["FINAL_PUBLISH_DIR"]
    GSHEET_URL = cfg["GSHEET_URL"]
    CREDS_JSON = cfg["CREDS_JSON"]
    DOWNLOAD_TIMEOUT = cfg["DOWNLOAD_TIMEOUT"]
    BETWEEN_CENTERS_DELAY = cfg["BETWEEN_CENTERS_DELAY"]
    RETRY_PER_CENTER = cfg["RETRY_PER_CENTER"]
    MAX_THREADS = cfg["MAX_THREADS"]
    TABS = cfg["GSHEET_TABS"]
    HEADLESS = cfg["HEADLESS"]
    FILE_SUFFIX = cfg["FILE_SUFFIX"]
    MACRO_USERS = cfg["MACRO_USERS"]
    CHROME_TMP_ROOT = cfg["CHROME_TMP_ROOT"]
    CHROME_TMP_RETENTION_HOURS = cfg["CHROME_TMP_RETENTION_HOURS"]
    MAX_CONCURRENT_DRIVER_STARTS = cfg["MAX_CONCURRENT_DRIVER_STARTS"]

    PG_HOST = cfg["PG_HOST"]
    PG_PORT = cfg["PG_PORT"]
    PG_DATABASE = cfg["PG_DATABASE"]
    PG_USER = cfg["PG_USER"]
    PG_PASSWORD = cfg["PG_PASSWORD"]

    SRC241_HOST = cfg["SRC241_HOST"]
    SRC241_PORT = cfg["SRC241_PORT"]
    SRC241_DATABASE = cfg["SRC241_DATABASE"]
    SRC241_USER = cfg["SRC241_USER"]
    SRC241_PASSWORD = cfg["SRC241_PASSWORD"]


    db = None
    job_id = None
    run_db_id = None

    # ===== target range =====
    base = datetime.date.today()
    start_target = base + datetime.timedelta(days=cfg["DATE_OFFSET_DAYS"])

    # Normalmente usa END_OFFSET_DAYS.
    # Para días especiales (por defecto viernes=4) usa SPECIAL_END_OFFSET_DAYS.
    end_offset_effective = cfg["END_OFFSET_DAYS"]
    special_weekdays = set(cfg.get("SPECIAL_RANGE_WEEKDAYS", []))
    special_end_offset_days = int(cfg.get("SPECIAL_END_OFFSET_DAYS", 3))
    if start_target.weekday() in special_weekdays and end_offset_effective < special_end_offset_days:
        end_offset_effective = special_end_offset_days

    end_target = base + datetime.timedelta(days=end_offset_effective)

    fecha_operativa_mail = start_target.strftime("%Y-%m-%d")
    fecha_futuro_fin_mail = end_target.strftime("%Y-%m-%d")

    if end_target < start_target:
        raise RuntimeError(
            f"Rango inválido: END_OFFSET_DAYS={end_offset_effective} "
            f"genera una fecha fin menor que la fecha inicio."
        )

    month_num = start_target.month
    month_header = MONTHS_ES.get(month_num, f"{start_target.month:02d}")
    month_nums = month_range_list(start_target, end_target)

    FE_INI = start_target.strftime("%d/%m/%Y")
    FE_FIN = end_target.strftime("%d/%m/%Y")
    FE_INI_DATE = start_target
    FE_FIN_DATE = end_target
    TAG = f"{start_target.strftime('%Y%m%d')}_{end_target.strftime('%Y%m%d')}"
    LABEL = f"{start_target.strftime('%Y-%m-%d')} -> {end_target.strftime('%Y-%m-%d')}"

    summary(
        summary_path,
        f"TARGET_RANGE | {LABEL} | start_offset={cfg['DATE_OFFSET_DAYS']} | "
        f"end_offset={end_offset_effective} | special_weekdays={cfg.get('SPECIAL_RANGE_WEEKDAYS', [])} | "
        f"special_end_offset={cfg.get('SPECIAL_END_OFFSET_DAYS', 3)}"
    )
    summary(summary_path, f"RANGE | {FE_INI} -> {FE_FIN} | TAG={TAG}")
    summary(summary_path, f"GSHEET_TABS | {TABS}")

    removed_tmp_profiles = cleanup_old_chrome_profiles(CHROME_TMP_ROOT, CHROME_TMP_RETENTION_HOURS)
    summary(summary_path, f"CHROME_TMP_CLEANUP_START | removed={removed_tmp_profiles} | root={CHROME_TMP_ROOT}")

    # ===== init DB =====
    try:
        db = PgRPAControl(
            host=cfg["PG_HOST"],
            port=cfg["PG_PORT"],
            database=cfg["PG_DATABASE"],
            user=cfg["PG_USER"],
            password=cfg["PG_PASSWORD"],
        )
        job_id = db.get_or_create_job(cfg["RPA_JOB_CODE"], cfg["RPA_JOB_NAME"])
        run_db_id = db.create_run(
            id_job=job_id,
            run_uuid=run_id,
            run_type=cfg["RPA_RUN_TYPE"],
            target_date=start_target,
            fecha_ini_data=FE_INI_DATE,
            fecha_fin_data=FE_FIN_DATE,
            tag=TAG,
            estado="RUNNING",
            observacion=f"Servidor={socket.gethostname()} | FILE_SUFFIX={FILE_SUFFIX}"
        )
        db.log_event(run_db_id, "INFO", "RUN_START", f"Inicio corrida {run_id}")
        db.log_event(run_db_id, "INFO", "TARGET_DAY", LABEL)
        db.log_event(run_db_id, "INFO", "RANGE", f"{FE_INI} -> {FE_FIN} | TAG={TAG}")

        try:
            mark_reportes_diario_en_ejecucion(
                db=db,
                run_uuid=run_id,
                fecha_operativa=start_target,
                fecha_futuro_fin=end_target
            )
        except Exception as e:
            print(f"REPORT_STATUS_START_WARN | {type(e).__name__}: {e}", flush=True)

    except Exception as e:
        summary(summary_path, f"DB_INIT_ERROR | {type(e).__name__}: {e}")
        if cfg["RPA_FAIL_IF_DB_DOWN"]:
            try:
                run_log_f.close()
            except Exception:
                pass
            sys.exit(3)

    # ===== leer checks del rango (1 o varios meses) desde tabs y merge/dedupe + macro =====
    try:
        log_fn = lambda m: summary(summary_path, m)

        all_items: List[Dict[str, str]] = []
        stats_by_tab = {}
        month_headers_used = []

        client = _gsheet_call_with_retry(lambda: _get_gspread_client(CREDS_JSON), log_fn=log_fn)

        for mnum in month_nums:
            mh = MONTHS_ES.get(mnum, f"{mnum:02d}")
            month_headers_used.append(mh)

            for t in TABS:
                items, st, _ = read_checked_centros_with_macro_from_tab(
                    client, GSHEET_URL, t, mnum, log_fn=log_fn
                )

                stats_key = f"{t}|{mh}"
                stats_by_tab[stats_key] = st
                all_items.extend(items)

        centros_meta, dup_global, macro_conflict = merge_centros_meta_items(all_items)

    except Exception as e:
        summary(summary_path, f"ERROR | GSHEET_READ | {LABEL} | {type(e).__name__}: {e}")
        sys.exit(2)

    summary(summary_path, f"MONTH_CHECKS | {month_headers_used}")
    for key, st in stats_by_tab.items():
        summary(
            summary_path,
            f"GSHEET_TAB | {key} | selected={st.get('selected',0)} | dup={st.get('dup',0)} | "
            f"unchecked={st.get('unchecked',0)} | empty={st.get('empty',0)} | invalid_macro={st.get('invalid_macro',0)}"
        )

    summary(summary_path, f"GSHEET_MERGE | selected_total={len(centros_meta)} | dup_global={dup_global} | macro_conflict={macro_conflict}")

    if db and run_db_id:
        try:
           db.log_event(
                run_db_id,
                "INFO",
                "GSHEET_MERGE",
                f"selected_total={len(centros_meta)} | dup_global={dup_global} | macro_conflict={macro_conflict}"
           )
        except Exception as e:
            print(f"DB_LOG_WARN | {type(e).__name__}: {e}", flush=True)

    override_map = {}
    if db and run_db_id:
        try:
            override_map = db.get_active_overrides([x["centro"] for x in centros_meta])
            summary(summary_path, f"OVERRIDE_CACHE | total={len(override_map)} | centros={sorted(override_map.keys())}")
        except Exception as e:
            summary(summary_path, f"OVERRIDE_CACHE_WARN | {type(e).__name__}: {e}")

    if not centros_meta:
        summary(summary_path, f"NO_WORK | No hay IPRESS marcadas para el mes {month_header}.")
        end_dt = datetime.datetime.now()
        dur = (end_dt - start_dt).total_seconds()

        if db and run_db_id:
            try:
                db.finish_run(
                    id_run=run_db_id,
                    estado="SUCCESS",
                    total_input=0,
                    total_ok=0,
                    total_fail=0,
                    duration_seconds=dur,
                    observacion="NO_WORK"
                )
            except Exception as e:
                print(f"DB_FINISH_WARN | {type(e).__name__}: {e}", flush=True)

        summary(summary_path, "RUN_END")
        summary(summary_path, f"Fecha fin    | {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        summary(summary_path, f"Duración(s)  | {dur:.1f}")
        try:
            run_log_f.close()
        except Exception:
            pass
        sys.exit(0)

    print("\n===== CONFIGURACIÓN (DIARIO) =====", flush=True)
    print(f"Rango fechas  : {LABEL}", flush=True)
    print(f"Mes (checks)  : {month_header}", flush=True)
    print(f"Rango         : {FE_INI} -> {FE_FIN}", flush=True)
    print(f"TAG           : {TAG}", flush=True)
    print(f"FILE_SUFFIX   : {FILE_SUFFIX}", flush=True)
    print(f"Rutas descarga: {DOWNLOAD_DIR_LIST}", flush=True)
    print(f"Ruta publish  : {FINAL_PUBLISH_DIR}", flush=True)
    print(f"MACRO_USERS   : { {k: v[0] for k, v in MACRO_USERS.items()} }", flush=True)
    print(f"INPUT | Centros (checks merge) ({len(centros_meta)}): {centros_meta}", flush=True)
    print("==================================\n", flush=True)

    if not preflight_chromedriver(DOWNLOAD_DIR_PRIMARY, HEADLESS, summary_path):
        failure_stage = "CHROMEDRIVER_PREFLIGHT"
        failure_detail = "ChromeDriver no pudo iniciar antes de limpiar o descargar."
        end_dt = datetime.datetime.now()
        dur = (end_dt - start_dt).total_seconds()
        failed_centros_preflight = [x.get("centro", "") for x in centros_meta if x.get("centro")]
        final_status = "FAILED"

        if db and run_db_id:
            try:
                db.log_event(run_db_id, "ERROR", "CHROMEDRIVER_PREFLIGHT_FAIL", failure_detail)
                db.finish_run(
                    id_run=run_db_id,
                    estado="FAILED",
                    total_input=len(centros_meta),
                    total_ok=0,
                    total_fail=len(centros_meta),
                    duration_seconds=dur,
                    observacion=failure_detail
                )
                db.create_alert_event(
                    id_run=run_db_id,
                    channel="EMAIL",
                    alert_type="CHROMEDRIVER_PREFLIGHT_FAIL",
                    severity="HIGH",
                    title="RPA Diario falló antes de descargar",
                    message=failure_detail,
                    payload={
                        "final_status": final_status,
                        "failure_stage": failure_stage,
                        "failure_detail": failure_detail,
                        "total_input": len(centros_meta),
                        "total_ok": 0,
                        "total_fail": len(centros_meta),
                        "duration_seconds": dur,
                    }
                )
            except Exception as e:
                print(f"DB_FINISH_WARN | {type(e).__name__}: {e}", flush=True)

        summary(summary_path, "RUN_END")
        summary(summary_path, f"Fecha fin    | {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        summary(summary_path, f"Duración(s)  | {dur:.1f}")

        mail_enabled = bool(cfg.get("MAIL_ENABLED", False))
        smtp_to = cfg.get("SMTP_TO", [])
        if isinstance(smtp_to, str):
            smtp_to = [x.strip() for x in smtp_to.split(",") if x.strip()]
        smtp_cc = [x.strip() for x in os.getenv("SMTP_CC", "").split(",") if x.strip()]

        send_preflight_mail = should_send_preflight_mail()
        if mail_enabled and smtp_to and send_preflight_mail:
            try:
                try:
                    run_log_f.flush()
                except Exception:
                    pass

                mail_subject = (
                    f"[RPA DIARIO] {final_status} | {fecha_operativa_mail or 'SIN_FECHA'} | "
                    f"OK:0 FAIL:{len(centros_meta)}"
                )
                mail_body = build_run_email_body_diario(
                    run_uuid=run_id,
                    final_status=final_status,
                    fecha_operativa=fecha_operativa_mail,
                    fecha_futuro_fin=fecha_futuro_fin_mail,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    dur=dur,
                    total_input=len(centros_meta),
                    total_ok=0,
                    total_fail=len(centros_meta),
                    failed_centros=failed_centros_preflight,
                    resultados_todos=[],
                    final_publish_ok=False,
                    refresh_diario_ok=False,
                    report_pendientes_ok=False,
                    report_futuro_ok=False,
                    failure_stage=failure_stage,
                    failure_detail=failure_detail,
                    attachment_label=os.path.basename(run_log_path) if run_log_path else "SIN_LOG",
                )

                send_smtp_mail(
                    smtp_host=cfg.get("SMTP_HOST", ""),
                    smtp_port=int(cfg.get("SMTP_PORT", 587) or 587),
                    smtp_user=cfg.get("SMTP_USER", ""),
                    smtp_pass=cfg.get("SMTP_PASS", ""),
                    mail_from=cfg.get("SMTP_FROM", ""),
                    mail_to=smtp_to,
                    mail_cc=smtp_cc,
                    subject=mail_subject,
                    body_text=mail_body,
                    attachment_path=run_log_path if run_log_path and os.path.exists(run_log_path) else "",
                )
                print("MAIL_SEND_OK | CHROMEDRIVER_PREFLIGHT_FAIL", flush=True)
            except Exception as e:
                print(f"MAIL_SEND_WARN | CHROMEDRIVER_PREFLIGHT_FAIL | {type(e).__name__}: {e}", flush=True)
        else:
            if not send_preflight_mail:
                print("MAIL_SEND_SKIP | CHROMEDRIVER_PREFLIGHT_FAIL | ORCH_RETRY_PENDING", flush=True)
            else:
                print("MAIL_SEND_SKIP | CHROMEDRIVER_PREFLIGHT_FAIL | MAIL_DISABLED_OR_NO_RECIPIENTS", flush=True)

        try:
            run_log_f.close()
        except Exception:
            pass
        sys.exit(4)

    # Limpieza previa SOLO para TAG del día (evita acumulado entre cortes)
    limpieza_previa_en_varias_rutas(
        DOWNLOAD_DIR_LIST,
        [x["centro"] for x in centros_meta],
        TAG,
        file_suffix=FILE_SUFFIX
    )

    overall_exit = 0
    descargados_total_ordenado: List[str] = []
    centros_pendientes_ordenado: List[str] = []
    resultados_todos: List[Dict[str, str]] = []

    try:
        centros = [x["centro"] for x in centros_meta]

        summary(summary_path, f"MACRO_USERS | { {k: v[0] for k, v in MACRO_USERS.items()} }")

        descargados_total_ordenado, centros_pendientes_ordenado, resultados_todos = ejecutar_descargas_por_macro(
            centros_meta=centros_meta,
            macro_users=MACRO_USERS,
            fecha_ini_dmy=FE_INI,
            fecha_fin_dmy=FE_FIN,
            tag=TAG,
            URL_HOME=URL_HOME,
            URL_MASIVAS=URL_MASIVAS,
            DOWNLOAD_TIMEOUT=DOWNLOAD_TIMEOUT,
            BETWEEN_CENTERS_DELAY=BETWEEN_CENTERS_DELAY,
            RETRY_PER_CENTER=RETRY_PER_CENTER,
            MAX_THREADS=MAX_THREADS,
            DOWNLOAD_DIR_PRIMARY=DOWNLOAD_DIR_PRIMARY,
            DOWNLOAD_DIR_MIRRORS=DOWNLOAD_DIR_MIRRORS,
            headless=HEADLESS,
            force_redownload=cfg["FORCE_REDOWNLOAD"],
            file_suffix=FILE_SUFFIX,
            summary_path=summary_path,
            override_map=override_map,
            db=db,
            run_uuid=run_id,
            run_db_id=run_db_id
        )

        summary(summary_path, f"TOTAL_INPUT | {len(centros)}")
        summary(summary_path, f"TOTAL_OK | {len(descargados_total_ordenado)} | {descargados_total_ordenado}")
        summary(summary_path, f"TOTAL_FAIL | {len(centros_pendientes_ordenado)} | {centros_pendientes_ordenado}")

        if centros_pendientes_ordenado and overall_exit != 130:
            overall_exit = max(overall_exit, 2)

        if db and run_db_id:
            for item in resultados_todos:
                if item.get("status") == "OK" and item.get("archivo"):
                    try:
                        id_archivo = db.register_file(
                            id_run=run_db_id,
                            file_name=item["archivo"],
                            file_path=item.get("archivo_path", ""),
                            file_size_bytes=int(item.get("archivo_size", 0)),
                            estado="DOWNLOADED",
                            publicado_txt=True,
                            cargado_stg=False
                        )

                        procesar_txt_a_staging(
                            db=db,
                            id_run=run_db_id,
                            run_uuid=run_id,
                            id_archivo=id_archivo,
                            file_name=item["archivo"],
                            file_path=item.get("archivo_path", ""),
                            summary_path=summary_path
                        )

                    except Exception as e:
                        print(f"DB_FILE_WARN | {item.get('archivo')} | {type(e).__name__}: {e}", flush=True)
                        try:
                            db.create_alert_event(
                                id_run=run_db_id,
                                channel="EMAIL",
                                alert_type="STAGING_LOAD",
                                severity="HIGH",
                                title=f"Fallo al procesar archivo: {item.get('archivo')}",
                                message=f"{type(e).__name__}: {e}",
                                payload={
                                    "file_name": item.get("archivo"),
                                    "file_path": item.get("archivo_path", "")
                                }
                            )
                        except Exception:
                            pass

                elif item.get("status") != "OK":
                    try:
                        db.log_event(
                            run_db_id,
                            "WARN",
                            "CENTER_FAIL",
                            f"centro={item.get('centro')} | motivo={item.get('motivo')} | usuario={item.get('usuario')} | fase={item.get('fase')} | macro_objetivo={item.get('macro_objetivo')} | macro_revalidacion={item.get('macro_revalidacion','')}"
                        )
                    except Exception as e:
                        print(f"DB_LOG_WARN | {type(e).__name__}: {e}", flush=True)

        # Purga parciales huérfanos (todas rutas)
        purge_old_partials(DOWNLOAD_DIR_LIST, max_age_minutes=30)

        # Si hubo al menos 1 OK, eliminamos históricos y dejamos SOLO el TAG del día
        if cfg.get("KEEP_ONLY_CURRENT_TAG", True) and len(descargados_total_ordenado) > 0:
            log_fn2 = lambda m: summary(summary_path, m)
            cleanup_keep_only_tag(
                download_dirs=DOWNLOAD_DIR_LIST,
                keep_tag=TAG,
                file_suffix=FILE_SUFFIX,
                log_fn=log_fn2
            )
        else:
            summary(summary_path, "KEEP_ONLY_TAG_SKIP | no OK downloads (no se borran históricos)")

        # Publicación final al compartido si hubo al menos 1 archivo OK
        final_publish_ok = False
        if len(descargados_total_ordenado) > 0:
            final_publish_ok = publish_txts_to_final_dir(
                temp_dir=DOWNLOAD_DIR_PRIMARY,
                final_dir=FINAL_PUBLISH_DIR,
                tag=TAG,
                file_suffix=FILE_SUFFIX,
                summary_path=summary_path,
                db=db,
                run_db_id=run_db_id
            )

            if len(centros_pendientes_ordenado) > 0:
                emit_event(
                    summary_path,
                    db,
                    run_db_id,
                    "WARN",
                    "FINAL_PUBLISH_PARTIAL",
                    f"tag={TAG} | total_ok={len(descargados_total_ordenado)} | total_fail={len(centros_pendientes_ordenado)} | fail_centros={centros_pendientes_ordenado}"
                )
        else:
            emit_event(
                summary_path,
                db,
                run_db_id,
                "WARN",
                "FINAL_PUBLISH_SKIP",
                f"tag={TAG} | total_ok=0 | total_fail={len(centros_pendientes_ordenado)}"
            )

        if len(descargados_total_ordenado) > 0 and not final_publish_ok:
            overall_exit = max(overall_exit, 2)
            failure_stage = "FINAL_PUBLISH"
            failure_detail = f"tag={TAG} | total_ok={len(descargados_total_ordenado)} | total_fail={len(centros_pendientes_ordenado)}"

    except KeyboardInterrupt:
        STOP_EVENT.set()
        summary(summary_path, "CANCELLED | Ctrl+C")
        overall_exit = 130
    finally:
        cleanup_active_browser_resources()
        kill_chromedrivers()
        removed_tmp_profiles_end = cleanup_old_chrome_profiles(CHROME_TMP_ROOT, CHROME_TMP_RETENTION_HOURS)
        summary(summary_path, f"CHROME_TMP_CLEANUP_END | removed={removed_tmp_profiles_end} | root={CHROME_TMP_ROOT}")

    should_run_refresh = (
        db is not None
        and run_db_id is not None
        and overall_exit != 130
        and len(descargados_total_ordenado) > 0
        and final_publish_ok
    )

    if should_run_refresh:
        try:
            total_medicos = sync_medicos_cenate_from_241(
                db=db,
                src_host=SRC241_HOST,
                src_port=SRC241_PORT,
                src_database=SRC241_DATABASE,
                src_user=SRC241_USER,
                src_password=SRC241_PASSWORD,
                summary_path=summary_path,
                run_db_id=run_db_id
            )

            db.call_refresh_reportes_diario(
                id_run=run_db_id,
                run_uuid=run_id,
                fecha_operativa=start_target,
                fecha_futuro_fin=end_target
            )

            emit_event(
                summary_path,
                db,
                run_db_id,
                "INFO",
                "REFRESH_REPORTES_DIARIO",
                f"run_uuid={run_id} | medicos_sync={total_medicos} | fecha_operativa={start_target} | fecha_futuro_fin={end_target}"
            )

            refresh_diario_ok = True
            report_pendientes_ok = True
            report_futuro_ok = True

            try:
                db.prune_stg_cext_prod_diario_keep_run(run_db_id)
                summary(summary_path, f"STG_PRUNE_DIARIO | keep_id_run={run_db_id}")
                db.log_event(
                    run_db_id,
                    "INFO",
                    "STG_PRUNE_DIARIO",
                    f"keep_id_run={run_db_id}"
                )
            except Exception as e:
                summary(summary_path, f"STG_PRUNE_DIARIO_WARN | {type(e).__name__}: {e}")


        except Exception as e:
            failure_stage = "REFRESH_REPORTES_DIARIO"
            failure_detail = f"{type(e).__name__}: {e}"
            overall_exit = max(overall_exit, 2)
            print(f"REFRESH_REPORTES_DIARIO_WARN | {type(e).__name__}: {e}", flush=True)

            try:
                db.set_report_status(
                    report_code="REP_DIARIO_PENDIENTES_DIA",
                    report_name="Reporte Diario - Pendientes del Día",
                    rpa_job_code="CEXT_PROD_DIARIO",
                    status="ERROR",
                    message=str(e),
                    target_date_start=start_target,
                    target_date_end=start_target,
                    last_run_uuid=run_id,
                    started_at=None,
                    finished_at=datetime.datetime.now(),
                    last_success_at=None,
                    row_count=None
                )

                db.set_report_status(
                    report_code="REP_DIARIO_CITADOS_FUTURO",
                    report_name="Reporte Diario - Citados a Futuro",
                    rpa_job_code="CEXT_PROD_DIARIO",
                    status="ERROR",
                    message=str(e),
                    target_date_start=start_target + datetime.timedelta(days=1),
                    target_date_end=end_target,
                    last_run_uuid=run_id,
                    started_at=None,
                    finished_at=datetime.datetime.now(),
                    last_success_at=None,
                    row_count=None
                )
            except Exception as e2:
                print(f"REPORT_STATUS_ERROR_WARN | {type(e2).__name__}: {e2}", flush=True)
    else:
        if overall_exit == 130:
            summary(summary_path, "REFRESH_REPORTES_DIARIO_SKIP | motivo=CANCELLED")
        elif len(descargados_total_ordenado) == 0:
            summary(summary_path, "REFRESH_REPORTES_DIARIO_SKIP | motivo=NO_DOWNLOADS")
        elif not final_publish_ok:
            summary(summary_path, "REFRESH_REPORTES_DIARIO_SKIP | motivo=FINAL_PUBLISH_NOT_OK")
        elif not db or not run_db_id:
            summary(summary_path, "REFRESH_REPORTES_DIARIO_SKIP | motivo=DB_NOT_AVAILABLE")


    end_dt = datetime.datetime.now()
    dur = (end_dt - start_dt).total_seconds()

    final_status = derive_final_status(
        overall_exit=overall_exit,
        total_ok=len(descargados_total_ordenado),
        total_fail=len(centros_pendientes_ordenado),
        final_publish_ok=final_publish_ok,
        refresh_diario_ok=refresh_diario_ok,
        report_pendientes_ok=report_pendientes_ok,
        report_futuro_ok=report_futuro_ok,
    )

    override_hits = len([r for r in resultados_todos if r.get("fase") == "OVERRIDE" and r.get("status") == "OK"])
    fallback_hits = len([r for r in resultados_todos if r.get("fase") == "FALLBACK" and r.get("status") == "OK"])

    if db and run_db_id:
        try:
            email_msg = (
                f"RPA Diario finalizado\n"
                f"Estado: {final_status}\n"
                f"Total centros: {len(centros_meta)}\n"
                f"Descargados: {len(descargados_total_ordenado)}\n"
                f"Fallidos: {len(centros_pendientes_ordenado)}\n"
                f"Duración(s): {dur:.1f}\n"
                f"Overrides aplicados: {override_hits}\n"
                f"Fallback OK: {fallback_hits}"
            )

            wa_msg = (
                f"RPA Diario | {final_status}\n"
                f"Total: {len(centros_meta)} | OK: {len(descargados_total_ordenado)} | FAIL: {len(centros_pendientes_ordenado)}\n"
                f"Duración: {dur:.1f}s"
            )

            db.create_alert_event(
                id_run=run_db_id,
                channel="EMAIL",
                alert_type="RUN_SUMMARY",
                severity="INFO" if final_status in ("SUCCESS", "PARTIAL_SUCCESS") else "HIGH",
                title=f"Resumen RPA Diario - {final_status}",
                message=email_msg,
                payload={
                    "final_status": final_status,
                    "total_input": len(centros_meta),
                    "total_ok": len(descargados_total_ordenado),
                    "total_fail": len(centros_pendientes_ordenado),
                    "duration_seconds": dur,
                    "override_hits": override_hits,
                    "fallback_hits": fallback_hits
                }
            )

            db.create_alert_event(
                id_run=run_db_id,
                channel="WHATSAPP",
                alert_type="RUN_SUMMARY",
                severity="INFO" if final_status in ("SUCCESS", "PARTIAL_SUCCESS") else "HIGH",
                title=f"Resumen RPA Diario - {final_status}",
                message=wa_msg,
                payload={
                    "final_status": final_status,
                    "total_input": len(centros_meta),
                    "total_ok": len(descargados_total_ordenado),
                    "total_fail": len(centros_pendientes_ordenado),
                    "duration_seconds": dur
                }
            )
        except Exception as e:
            print(f"ALERT_SUMMARY_WARN | {type(e).__name__}: {e}", flush=True)

    if db and run_db_id:
        try:
            db.log_event(run_db_id, "INFO", "RUN_END", f"Fin corrida | estado={final_status} | duracion={dur:.1f}s")
            db.finish_run(
                id_run=run_db_id,
                estado=final_status,
                total_input=len(centros_meta),
                total_ok=len(descargados_total_ordenado),
                total_fail=len(centros_pendientes_ordenado),
                duration_seconds=dur,
                observacion=f"HEADLESS={HEADLESS} | MAX_THREADS={MAX_THREADS} | FINAL_PUBLISH_DIR={FINAL_PUBLISH_DIR}"
            )
        except Exception as e:
            print(f"DB_FINISH_WARN | {type(e).__name__}: {e}", flush=True)

    summary(summary_path, "RUN_END")
    summary(summary_path, f"Fecha fin    | {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    summary(summary_path, f"Duración(s)  | {dur:.1f}")

    # Configuración de correo robusta.
    # Lee variables desde .env y evita NameError si alguna no fue definida antes.
    MAIL_ENABLED_RAW = os.getenv("MAIL_ENABLED", str(locals().get("MAIL_ENABLED", "false")))
    MAIL_ENABLED = str(MAIL_ENABLED_RAW).strip().lower() in ("1", "true", "yes", "y", "si", "sí")

    SMTP_HOST = os.getenv("SMTP_HOST", str(locals().get("SMTP_HOST", "")))
    SMTP_PORT = os.getenv("SMTP_PORT", str(locals().get("SMTP_PORT", "587")))
    SMTP_USER = os.getenv("SMTP_USER", str(locals().get("SMTP_USER", "")))
    SMTP_PASS = os.getenv("SMTP_PASS", str(locals().get("SMTP_PASS", "")))
    SMTP_FROM = os.getenv("SMTP_FROM", str(locals().get("SMTP_FROM", "")))
    SMTP_TO = os.getenv("SMTP_TO", str(locals().get("SMTP_TO", "")))
    SMTP_CC = os.getenv("SMTP_CC", str(locals().get("SMTP_CC", "")))

    try:
        SMTP_PORT = int(SMTP_PORT or 587)
    except Exception:
        SMTP_PORT = 587

    if MAIL_ENABLED:
        try:
            try:
                run_log_f.flush()
            except Exception:
                pass

            attachment_path = ""
            if run_log_path and os.path.exists(run_log_path):
                attachment_path = run_log_path
            elif summary_path and os.path.exists(summary_path):
                attachment_path = summary_path

            mail_fecha = str(fecha_operativa_mail or locals().get("start_target", ""))
            mail_futuro = str(fecha_futuro_fin_mail or locals().get("end_target", ""))
            failure_stage_mail = str(locals().get("failure_stage", ""))
            failure_detail_mail = str(locals().get("failure_detail", ""))

            if not SMTP_TO:
                print("MAIL_SEND_SKIP | SMTP_TO vacío", flush=True)
            else:
                mail_subject = (
                    f"[RPA DIARIO] {final_status} | {mail_fecha or 'SIN_FECHA'} | "
                    f"OK:{len(descargados_total_ordenado)} FAIL:{len(centros_pendientes_ordenado)}"
                )

                mail_body = build_run_email_body_diario(
                    run_uuid=run_id,
                    final_status=final_status,
                    fecha_operativa=mail_fecha,
                    fecha_futuro_fin=mail_futuro,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    dur=dur,
                    total_input=len(centros_meta),
                    total_ok=len(descargados_total_ordenado),
                    total_fail=len(centros_pendientes_ordenado),
                    failed_centros=centros_pendientes_ordenado,
                    resultados_todos=resultados_todos,
                    final_publish_ok=final_publish_ok,
                    refresh_diario_ok=refresh_diario_ok,
                    report_pendientes_ok=report_pendientes_ok,
                    report_futuro_ok=report_futuro_ok,
                    failure_stage=failure_stage_mail,
                    failure_detail=failure_detail_mail,
                    attachment_label=os.path.basename(attachment_path) if attachment_path else "SIN_LOG",
                )

                send_smtp_mail(
                    smtp_host=SMTP_HOST,
                    smtp_port=SMTP_PORT,
                    smtp_user=SMTP_USER,
                    smtp_pass=SMTP_PASS,
                    mail_from=SMTP_FROM,
                    mail_to=[
                        x.strip()
                        for x in str(SMTP_TO or "").split(",")
                        if x.strip()
                    ],
                    mail_cc=[
                        x.strip()
                        for x in str(SMTP_CC or "").split(",")
                        if x.strip()
                    ],
                    subject=mail_subject,
                    body_text=mail_body,
                    attachment_path=attachment_path,
                )

                print("MAIL_SEND_OK", flush=True)

        except Exception as e:
            print(f"MAIL_SEND_WARN | {type(e).__name__}: {e}", flush=True)

    try:
        run_log_f.close()
    except Exception:
        pass

    sys.exit(overall_exit)


if __name__ == "__main__":
    main()
