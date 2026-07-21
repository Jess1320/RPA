import os
import sys
import time
import signal
import platform
import threading
import datetime
import re
import logging
import shutil
import tempfile
from calendar import monthrange
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from dotenv import load_dotenv
from mailer import send_smtp_mail

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import NoSuchElementException

import gspread
from oauth2client.service_account import ServiceAccountCredentials


# =========================
# Señales / Cancelación
# =========================
STOP_EVENT = threading.Event()

def handle_signal(signum, frame):
    STOP_EVENT.set()

signal.signal(signal.SIGINT, handle_signal)
try:
    signal.signal(signal.SIGTERM, handle_signal)
except Exception:
    pass


def kill_chromedrivers():
    if platform.system() == "Windows":
        try:
            import subprocess
            subprocess.run(
                ["taskkill", "/F", "/IM", "chromedriver.exe", "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass


VALID_MACROS = ("CENTRO", "NORTE", "SUR", "LIMA ORIENTE")
INVALID_MACRO_LABEL = "SIN_MACRO"


def _norm_macro(value: str) -> str:
    s = (value or "").strip().upper().replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    if s == "LIMAORIENTE":
        return "LIMA ORIENTE"
    return s


def _split_recipients(value: str) -> List[str]:
    return [x.strip() for x in re.split(r"[;,]", value or "") if x.strip()]


def _env_bool(name: str, default: str = "false") -> bool:
    return (os.getenv(name, default) or default).strip().lower() in ("1", "true", "yes", "y", "si", "sí")


def load_rpa_env_files() -> None:
    load_dotenv(os.getenv("ENV_FILE", ".env"), override=False)

    users_env = os.getenv("RPA_USERS_ENV_FILE", "").strip() or os.getenv("USERS_ENV_FILE", "").strip()
    project_dir = Path(__file__).resolve().parents[1]
    candidates = []
    if users_env:
        candidates.append(users_env)
    candidates.extend([
        str(project_dir / "config" / ".env_usuarios"),
        str(project_dir.parent / "shared" / "config" / ".env_usuarios"),
        ".env_usuarios",
    ])

    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file():
            load_dotenv(path, override=True)
            break


# =========================
# Utils (dirs/log time)
# =========================
def ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)

def get_project_dir() -> Path:
    return Path(__file__).resolve().parents[1]

def get_chrome_profile_base_dir() -> str:
    configured = os.getenv("CHROME_PROFILE_BASE_DIR", "").strip()
    project_dir = get_project_dir()
    if configured:
        base_dir = Path(configured).expanduser()
        if not base_dir.is_absolute():
            base_dir = project_dir / base_dir
    else:
        base_dir = project_dir / "tmp" / "chrome_profiles"
    base_dir.mkdir(parents=True, exist_ok=True)
    return str(base_dir)

def safe_rmtree(path: str, retries: int = 3, delay: float = 1.0) -> bool:
    if not path:
        return True
    target = Path(path)
    if not target.exists():
        return True
    for attempt in range(1, retries + 1):
        try:
            shutil.rmtree(target, ignore_errors=False)
            return True
        except Exception:
            if attempt < retries:
                time.sleep(delay)
    return not target.exists()

def cleanup_old_chrome_profiles(profile_base_dir: str, max_age_hours: int = 12, logger=None) -> int:
    root = Path(profile_base_dir)
    if not root.is_dir():
        return 0
    cutoff = time.time() - (max_age_hours * 3600)
    removed = 0
    for item in root.iterdir():
        if not item.is_dir() or not item.name.startswith("chrome-profile-"):
            continue
        try:
            if item.stat().st_mtime > cutoff:
                continue
            if safe_rmtree(str(item)):
                removed += 1
                if logger:
                    logger.info(f"TMP_PROFILE_CLEANUP | {item}")
            elif logger:
                logger.info(f"TMP_PROFILE_CLEANUP_WARN | {item}")
        except Exception as e:
            if logger:
                logger.info(f"TMP_PROFILE_CLEANUP_ERR | {item} | {type(e).__name__}:{e}")
    return removed

def ts_now() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def setup_run_logger(logs_dir: str, run_name: str, log_mode: str = "PROD"):
    run_id = f"RUN_{run_name}_{ts_now()}"
    run_dir = os.path.join(logs_dir, run_id)
    ensure_dir(run_dir)

    logfile = os.path.join(run_dir, "run.log")

    logger = logging.getLogger(run_name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        for h in list(logger.handlers):
            logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    mode = (log_mode or "PROD").strip().upper()
    handler_level = logging.DEBUG if mode == "DEBUG" else logging.INFO

    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setLevel(handler_level)
    fh.setFormatter(fmt)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(handler_level)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)

    return logger, run_dir, logfile


# =========================
# Utilidades (archivos / descargas)
# =========================
def listar_archivos(dirpath: str) -> List[str]:
    try:
        return os.listdir(dirpath)
    except Exception:
        return []

def files_with_prefix(download_dir: str, prefix: str) -> List[str]:
    return [f for f in listar_archivos(download_dir) if f.startswith(prefix)]

def file_is_stable(path: str, stable_secs: int = 3) -> bool:
    if not os.path.exists(path):
        return False
    s1 = os.path.getsize(path)
    time.sleep(stable_secs)
    if not os.path.exists(path):
        return False
    s2 = os.path.getsize(path)
    return (s1 == s2) and (s2 > 0)

def archivo_esta_vacio(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) == 0

def normalize_expected_suffix(expected_suffix: str) -> str:
    suffix = (expected_suffix or "").strip()
    if suffix.lower().endswith(".txt"):
        suffix = suffix[:-4]
    return suffix

def filename_matches_expected_suffix(filename: str, expected_suffix: str) -> bool:
    if not filename:
        return False
    low = filename.lower()
    if not low.endswith(".txt"):
        return False
    stem = filename[:-4]
    suffix = normalize_expected_suffix(expected_suffix)
    return bool(suffix) and stem.lower().endswith(suffix.lower())

def remove_partial_with_prefix(logger, download_dir: str, prefix: str, unconfirmed_age_min: int = 10) -> int:
    removed = 0
    now = time.time()

    for f in files_with_prefix(download_dir, prefix):
        low = f.lower()
        if low.endswith((".crdownload", ".tmp", ".part")) or " (1)." in low or " (2)." in low or " (3)." in low:
            try:
                os.remove(os.path.join(download_dir, f))
                removed += 1
                logger.debug(f"PRETRY_CLEAN | {download_dir} | {f}")
            except Exception as e:
                logger.debug(f"PRETRY_CLEAN_ERR | {download_dir} | {f} | {type(e).__name__}:{e}")

    for f in listar_archivos(download_dir):
        low = f.lower()
        if low.endswith(".crdownload") and ("unconfirmed" in low or "sin confirmar" in low):
            p = os.path.join(download_dir, f)
            try:
                if now - os.path.getmtime(p) > unconfirmed_age_min * 60:
                    os.remove(p)
                    removed += 1
                    logger.debug(f"PRETRY_CLEAN_UNCONF | {download_dir} | {f}")
            except Exception:
                pass

    return removed

def purge_old_partials(logger, download_dir: str, max_age_minutes: int = 30) -> None:
    now = time.time()
    for f in listar_archivos(download_dir):
        low = f.lower()
        if low.endswith((".crdownload", ".tmp", ".part")):
            p = os.path.join(download_dir, f)
            try:
                if now - os.path.getmtime(p) > max_age_minutes * 60:
                    os.remove(p)
                    logger.debug(f"PURGE_PARTIAL | {download_dir} | {f}")
            except Exception:
                pass

def clean_existing_finals(logger, download_dir: str, prefix: str, expected_suffix: str) -> int:
    deleted = 0

    for f in listar_archivos(download_dir):
        if f.startswith(prefix) and filename_matches_expected_suffix(f, expected_suffix):
            try:
                os.remove(os.path.join(download_dir, f))
                deleted += 1
                logger.debug(f"CLEAN_DELETE | {download_dir} | {f}")
            except Exception as e:
                logger.debug(f"CLEAN_ERR | {download_dir} | {f} | {type(e).__name__}:{e}")

    for f in listar_archivos(download_dir):
        low = f.lower()
        if f.startswith(prefix) and low.endswith(".txt") and (" (1)." in low or " (2)." in low or " (3)." in low):
            try:
                os.remove(os.path.join(download_dir, f))
                deleted += 1
                logger.debug(f"CLEAN_DUP_DELETE | {download_dir} | {f}")
            except Exception:
                pass

    return deleted

def publish_validated_download(
    logger,
    source_path: str,
    final_dir: str,
    prefix: str,
    expected_suffix: str,
    target_filename: str = "",
    final_expected_suffix: str = "",
) -> str:
    archivo = target_filename or os.path.basename(source_path)
    ensure_dir(final_dir)

    deleted = clean_existing_finals(logger, final_dir, prefix, final_expected_suffix or expected_suffix)
    if deleted:
        logger.info(f"PUBLISH_CLEAN | dir={final_dir} | prefix={prefix} | deleted={deleted}")

    final_path = os.path.join(final_dir, archivo)
    tmp_path = os.path.join(final_dir, f".{archivo}.publishing_{ts_now()}")
    shutil.copy2(source_path, tmp_path)
    os.replace(tmp_path, final_path)
    logger.info(f"PUBLISH_OK | {final_path}")
    return final_path

def cleanup_empty_dirs(root_dir: str, logger=None, remove_root: bool = False) -> int:
    root = Path(root_dir)
    if not root.is_dir():
        return 0
    removed = 0
    for current, dirs, files in os.walk(root, topdown=False):
        current_path = Path(current)
        if current_path == root and not remove_root:
            continue
        try:
            if not any(current_path.iterdir()):
                current_path.rmdir()
                removed += 1
                if logger:
                    logger.info(f"STAGING_EMPTY_DIR_DELETE | {current_path}")
        except Exception:
            pass
    return removed

def esperar_descarga_por_prefijo(
    download_dir: str,
    prefix: str,
    expected_suffix: str,
    timeout: int,
    stable_secs: int,
    poll_interval: int
) -> str:
    start = time.time()
    while time.time() - start <= timeout:
        if STOP_EVENT.is_set():
            return ""

        files = files_with_prefix(download_dir, prefix)
        partials = [f for f in files if f.lower().endswith((".crdownload", ".tmp", ".part"))]

        finals = [
            f for f in files
            if f.lower().endswith(".txt")
            and " (" not in f
            and filename_matches_expected_suffix(f, expected_suffix)
        ]

        if finals and not partials:
            finals.sort(key=lambda x: os.path.getmtime(os.path.join(download_dir, x)), reverse=True)
            cand = finals[0]
            cand_path = os.path.join(download_dir, cand)
            if file_is_stable(cand_path, stable_secs):
                return cand

        time.sleep(poll_interval)

    return ""


# =========================
# Config desde .env
# =========================
def load_config() -> dict:
    load_rpa_env_files()

    url_home = os.getenv("URL_HOME")
    frm_resultado = os.getenv(
        "FRM_RESULTADO_TIPO_EXAMEN",
        "http://appsgasistexpl.essalud.gob.pe/explotaDatos/servlet/CtrlControl?opt=ayudaDx04A_B",
    ).strip()
    frm_pendientes = os.getenv(
        "FRM_TRATAMIENTO_PENDIENTES",
        "http://appsgasistexpl.essalud.gob.pe/explotaDatos/servlet/CtrlControl?opt=atentraimagPen",
    ).strip()
    frm_asignados = os.getenv(
        "FRM_TRATAMIENTO_ASIGNADOS",
        "http://appsgasistexpl.essalud.gob.pe/explotaDatos/servlet/CtrlControl?opt=atentraimagAsig",
    ).strip()

    # Legacy: se mantiene solo para transicion si aun no existe .env_usuarios.
    user = None
    pwd = None
    for i in range(1, 51):
        u = os.getenv(f"USER_{i}")
        p = os.getenv(f"PASSWORD_{i}")
        if u and p:
            user, pwd = u, p
            break

    macro_users = {
        "CENTRO": (os.getenv("USER_CENTRO", "").strip(), os.getenv("PASSWORD_CENTRO", "").strip()),
        "NORTE": (os.getenv("USER_NORTE", "").strip(), os.getenv("PASSWORD_NORTE", "").strip()),
        "SUR": (os.getenv("USER_SUR", "").strip(), os.getenv("PASSWORD_SUR", "").strip()),
        "LIMA ORIENTE": (os.getenv("USER_LIMA_ORIENTE", "").strip(), os.getenv("PASSWORD_LIMA_ORIENTE", "").strip()),
    }
    default_macro = _norm_macro(os.getenv("DEFAULT_MACRO", "CENTRO"))
    if default_macro not in VALID_MACROS:
        default_macro = "CENTRO"
    require_macro = _env_bool("REQUIRE_MACRO", "false")

    gsheet_url = os.getenv("GSHEET_URL")
    gsheet_tab = os.getenv("GSHEET_TAB", "TAD")
    creds_json = os.getenv("CREDS_JSON")

    download_dir_resultado = os.getenv(
        "DOWNLOAD_DIR_RESULTADO_TIPO_EXAMEN",
        "/mnt/comp_observatorio/BI_2025/Bases_Teleradio/2026 ESSI",
    ).strip()
    download_dir_pendientes = os.getenv(
        "DOWNLOAD_DIR_TRATAMIENTO_PENDIENTES",
        "/mnt/comp_observatorio/BI_2025/Bases_Teleradio/DIFERIMIENTO_ESSI_PENDIENTES",
    ).strip()
    download_dir_asignados = os.getenv(
        "DOWNLOAD_DIR_TRATAMIENTO_ASIGNADOS",
        "/mnt/comp_observatorio/BI_2025/Bases_Teleradio/DIFERIMIENTO_ESSI_ASIGNADOS",
    ).strip()
    staging_download_dir = os.getenv("STAGING_DOWNLOAD_DIR", "tmp/downloads").strip()
    staging_path = Path(staging_download_dir).expanduser()
    if not staging_path.is_absolute():
        staging_path = get_project_dir() / staging_path
    staging_download_dir = str(staging_path)

    headless = os.getenv("HEADLESS", "false").lower() == "true"
    chrome_profile_base_dir = get_chrome_profile_base_dir()
    chrome_profile_max_age_hours = int(os.getenv("CHROME_PROFILE_MAX_AGE_HOURS", "12"))
    logs_dir = os.getenv("LOGS_DIR", "logs")
    keep_open_seconds = int(os.getenv("KEEP_OPEN_SECONDS", "0"))
    require_center = os.getenv("REQUIRE_CENTER", "true").lower() == "true"

    # NUEVO: logs prod
    log_mode = os.getenv("LOG_MODE", "PROD").strip().upper()
    log_retention_days = int(os.getenv("LOG_RETENTION_DAYS", "14"))
    log_max_list = int(os.getenv("LOG_MAX_LIST", "50"))

    # correo
    mail_enabled = _env_bool("MAIL_ENABLED", "false")
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587") or "587")
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user).strip()
    smtp_to = _split_recipients(os.getenv("SMTP_TO", ""))
    smtp_cc = _split_recipients(os.getenv("SMTP_CC", ""))

    # formulario
    mes_a_procesar = os.getenv("MES_A_PROCESAR", "ACTUAL").strip()
    tipo_examen = os.getenv("TIPO_EXAMEN", "1").strip()
    area = os.getenv("AREA", "00").strip()
    servicio = os.getenv("SERVICIO", "00").strip()
    formato_archivo = os.getenv("FORMATO_ARCHIVO", "xls").strip()
    suffix_resultado = os.getenv("FILE_SUFFIX_RESULTADO_TIPO_EXAMEN", "ResulExam_Imagen").strip()
    suffix_pendientes = os.getenv("FILE_SUFFIX_TRATAMIENTO_PENDIENTES", "TratImagenesPendientes").strip()
    suffix_asignados = os.getenv("FILE_SUFFIX_TRATAMIENTO_ASIGNADOS", "TratImagenesAsignados").strip()
    publish_suffix_resultado = os.getenv("PUBLISH_SUFFIX_RESULTADO_TIPO_EXAMEN", "MONTH_NAME").strip()

    # motor
    run_resultado = os.getenv("RUN_RESULTADO_TIPO_EXAMEN", "true").lower() == "true"
    run_pendientes = os.getenv("RUN_TRATAMIENTO_PENDIENTES", "true").lower() == "true"
    run_asignados = os.getenv("RUN_TRATAMIENTO_ASIGNADOS", "true").lower() == "true"
    download_timeout = int(os.getenv("DOWNLOAD_TIMEOUT", "900"))
    stable_secs = int(os.getenv("STABLE_SECS", "3"))
    poll_interval = int(os.getenv("POLL_INTERVAL", "2"))
    retry_per_center = int(os.getenv("RETRY_PER_CENTER", "1"))
    between_delay = int(os.getenv("BETWEEN_DOWNLOADS_DELAY", "2"))
    clean_before = os.getenv("CLEAN_BEFORE", "true").lower() == "true"
    purge_age_min = int(os.getenv("PURGE_PARTIALS_AGE_MIN", "30"))

    # Paso 4: ejecución
    run_name = os.getenv("RUN_NAME", "TAD")
    max_centers = int(os.getenv("MAX_CENTERS", "0"))
    centers_filter_raw = os.getenv("CENTERS_FILTER", "").strip()
    centers_filter = [c.strip() for c in centers_filter_raw.split(",") if c.strip()] if centers_filter_raw else []

    # Timings nuevos (en segundos)
    delay_after_select_center = int(os.getenv("DELAY_AFTER_SELECT_CENTER", "1"))
    delay_after_submit_center = int(os.getenv("DELAY_AFTER_SUBMIT_CENTER", "1"))
    delay_before_open_form = int(os.getenv("DELAY_BEFORE_OPEN_FORM", "1"))

    faltan = []
    for k, v in [
        ("URL_HOME", url_home),
        ("FRM_RESULTADO_TIPO_EXAMEN", frm_resultado),
        ("FRM_TRATAMIENTO_PENDIENTES", frm_pendientes),
        ("FRM_TRATAMIENTO_ASIGNADOS", frm_asignados),
        ("GSHEET_URL", gsheet_url),
        ("GSHEET_TAB", gsheet_tab),
        ("CREDS_JSON", creds_json),
        ("DOWNLOAD_DIR_RESULTADO_TIPO_EXAMEN", download_dir_resultado),
        ("DOWNLOAD_DIR_TRATAMIENTO_PENDIENTES", download_dir_pendientes),
        ("DOWNLOAD_DIR_TRATAMIENTO_ASIGNADOS", download_dir_asignados),
        ("STAGING_DOWNLOAD_DIR", staging_download_dir),
    ]:
        if not v:
            faltan.append(k)
    if not tipo_examen:
        faltan.append("TIPO_EXAMEN")
    if not area:
        faltan.append("AREA")
    if not servicio:
        faltan.append("SERVICIO")
    if not suffix_resultado:
        faltan.append("FILE_SUFFIX_RESULTADO_TIPO_EXAMEN")
    if not suffix_pendientes:
        faltan.append("FILE_SUFFIX_TRATAMIENTO_PENDIENTES")
    if not suffix_asignados:
        faltan.append("FILE_SUFFIX_TRATAMIENTO_ASIGNADOS")
    if not user or not pwd:
        if all(not u or not p for u, p in macro_users.values()):
            faltan.append("credenciales macro o al menos un par USER_n / PASSWORD_n")

    configured_macros = {m: creds for m, creds in macro_users.items() if creds[0] and creds[1]}
    if configured_macros:
        for macro in VALID_MACROS:
            if macro not in configured_macros:
                faltan.append(f"credenciales macro {macro}")
    elif user and pwd:
        macro_users = {default_macro: (user, pwd)}

    if faltan:
        print("❌ Faltan variables en .env:", faltan, flush=True)
        sys.exit(1)

    primary_user, primary_pwd = next(iter(macro_users.values())) if macro_users else (user, pwd)

    ensure_dir(logs_dir)
    ensure_dir(download_dir_resultado)
    ensure_dir(download_dir_pendientes)
    ensure_dir(download_dir_asignados)
    ensure_dir(staging_download_dir)

    routes = []
    if run_resultado:
        routes.append({
            "code": "RESULTADO_TIPO_EXAMEN",
            "name": "Resultado por Tipo de Examen",
            "url": frm_resultado,
            "download_dir": download_dir_resultado,
            "expected_suffix": suffix_resultado,
            "publish_suffix": publish_suffix_resultado,
            "rename_to_month": True,
        })
    if run_pendientes:
        routes.append({
            "code": "TRATAMIENTO_PENDIENTES",
            "name": "Tratamiento de Imagenes - Pendientes",
            "url": frm_pendientes,
            "download_dir": download_dir_pendientes,
            "expected_suffix": suffix_pendientes,
            "rename_to_month": False,
        })
    if run_asignados:
        routes.append({
            "code": "TRATAMIENTO_ASIGNADOS",
            "name": "Tratamiento de Imagenes - Asignados",
            "url": frm_asignados,
            "download_dir": download_dir_asignados,
            "expected_suffix": suffix_asignados,
            "rename_to_month": False,
        })

    return {
        "URL_HOME": url_home,
        "FRM_RESULTADO_TIPO_EXAMEN": frm_resultado,
        "FRM_TRATAMIENTO_PENDIENTES": frm_pendientes,
        "FRM_TRATAMIENTO_ASIGNADOS": frm_asignados,
        "USER": primary_user,
        "PASS": primary_pwd,
        "MACRO_USERS": macro_users,
        "DEFAULT_MACRO": default_macro,
        "REQUIRE_MACRO": require_macro,
        "GSHEET_URL": gsheet_url,
        "GSHEET_TAB": gsheet_tab,
        "CREDS_JSON": creds_json,
        "DOWNLOAD_DIR_RESULTADO_TIPO_EXAMEN": download_dir_resultado,
        "DOWNLOAD_DIR_TRATAMIENTO_PENDIENTES": download_dir_pendientes,
        "DOWNLOAD_DIR_TRATAMIENTO_ASIGNADOS": download_dir_asignados,
        "STAGING_DOWNLOAD_DIR": staging_download_dir,
        "ROUTES": routes,
        "HEADLESS": headless,
        "CHROME_PROFILE_BASE_DIR": chrome_profile_base_dir,
        "CHROME_PROFILE_MAX_AGE_HOURS": chrome_profile_max_age_hours,
        "LOGS_DIR": logs_dir,
        "KEEP_OPEN_SECONDS": keep_open_seconds,
        "REQUIRE_CENTER": require_center,

        "LOG_MODE": log_mode,
        "LOG_RETENTION_DAYS": log_retention_days,
        "LOG_MAX_LIST": log_max_list,

        "MAIL_ENABLED": mail_enabled,
        "SMTP_HOST": smtp_host,
        "SMTP_PORT": smtp_port,
        "SMTP_USER": smtp_user,
        "SMTP_PASS": smtp_pass,
        "SMTP_FROM": smtp_from,
        "SMTP_TO": smtp_to,
        "SMTP_CC": smtp_cc,

        "MES_A_PROCESAR": mes_a_procesar,
        "TIPO_EXAMEN": tipo_examen,
        "AREA": area,
        "SERVICIO": servicio,
        "FORMATO_ARCHIVO": formato_archivo,
        "FILE_SUFFIX_RESULTADO_TIPO_EXAMEN": suffix_resultado,
        "FILE_SUFFIX_TRATAMIENTO_PENDIENTES": suffix_pendientes,
        "FILE_SUFFIX_TRATAMIENTO_ASIGNADOS": suffix_asignados,
        "PUBLISH_SUFFIX_RESULTADO_TIPO_EXAMEN": publish_suffix_resultado,

        "RUN_RESULTADO_TIPO_EXAMEN": run_resultado,
        "RUN_TRATAMIENTO_PENDIENTES": run_pendientes,
        "RUN_TRATAMIENTO_ASIGNADOS": run_asignados,
        "DOWNLOAD_TIMEOUT": download_timeout,
        "STABLE_SECS": stable_secs,
        "POLL_INTERVAL": poll_interval,
        "RETRY_PER_CENTER": retry_per_center,
        "BETWEEN_DOWNLOADS_DELAY": between_delay,
        "CLEAN_BEFORE": clean_before,
        "PURGE_PARTIALS_AGE_MIN": purge_age_min,

        "RUN_NAME": run_name,
        "MAX_CENTERS": max_centers,
        "CENTERS_FILTER": centers_filter,

        "DELAY_AFTER_SELECT_CENTER": delay_after_select_center,
        "DELAY_AFTER_SUBMIT_CENTER": delay_after_submit_center,
        "DELAY_BEFORE_OPEN_FORM": delay_before_open_form,
    }


# =========================
# Google Sheets (centros con filtro por check de mes)
# =========================
MONTHS_ES = {
    1: "ENERO",
    2: "FEBRERO",
    3: "MARZO",
    4: "ABRIL",
    5: "MAYO",
    6: "JUNIO",
    7: "JULIO",
    8: "AGOSTO",
    9: "SEPTIEMBRE",
    10: "OCTUBRE",
    11: "NOVIEMBRE",
    12: "DICIEMBRE",
}

# En Perú a veces se usa "SETIEMBRE"
MONTH_ALIASES = {
    "SEPTIEMBRE": ["SEPTIEMBRE", "SETIEMBRE"],
}

def _norm_cell(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().upper())

def _is_checked(v: str) -> bool:
    vv = _norm_cell(v)
    if vv in ("TRUE", "VERDADERO", "SI", "SÍ", "1", "X", "✔", "✅", "V"):
        return True
    if vv in ("FALSE", "FALSO", "NO", "0", ""):
        return False
    return False

def _month_header_from_ctx(month_ctx: dict) -> str:
    try:
        dmy = month_ctx.get("MONTH_FIRST_DMY", "")
        parts = dmy.split("/")
        m = int(parts[1])
        return MONTHS_ES.get(m, "")
    except Exception:
        return ""

def _find_col(headers_norm: List[str], candidates_norm: List[str]) -> int:
    cand_set = set(candidates_norm)
    for i, h in enumerate(headers_norm):
        if h in cand_set:
            return i
    return -1

def get_centros_from_gsheet(
    creds_json: str,
    gsheet_url: str,
    gsheet_tab: str,
    month_ctx: dict,
    logger=None,
    config=None
) -> List[Dict[str, str]]:
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_json, scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(gsheet_url).worksheet(gsheet_tab)

    values = ws.get_all_values()
    if not values:
        return []

    header = values[0]
    headers_norm = [_norm_cell(h) for h in header]

    all_month_headers = set(MONTHS_ES.values())
    is_table = ("COD_IPRESS" in headers_norm) or any(h in all_month_headers or h in ("SETIEMBRE",) for h in headers_norm)

    if not is_table:
        centros = ws.col_values(1)
        if centros and not centros[0].strip().isdigit():
            centros = centros[1:]
        centros = [c.strip() for c in centros if c and c.strip()]
        if config and config.get("REQUIRE_MACRO"):
            raise RuntimeError("GSHEET | La hoja simple no tiene columna MACRO y REQUIRE_MACRO=true.")
        default_macro = (config or {}).get("DEFAULT_MACRO", "CENTRO")
        if logger:
            logger.info(f"GSHEET | formato simple detectado | centros={len(centros)} | macro_default={default_macro}")
        return [{"centro": c, "macro": default_macro} for c in centros]

    idx_cod = _find_col(headers_norm, ["COD_IPRESS", "COD IPRESS", "CODIGO IPRESS", "CODIGO DE IPRESS"])
    if idx_cod < 0:
        for i, h in enumerate(headers_norm):
            if ("COD" in h and "IPRESS" in h) or h == "COD":
                idx_cod = i
                break
    if idx_cod < 0:
        raise RuntimeError("GSHEET | No se encontró columna COD_IPRESS en el header.")

    idx_macro = _find_col(headers_norm, [_norm_cell(x) for x in ["MACRO", "MACROREGION", "MACRO REGION", "MACRO REGIÓN"]])
    require_macro = bool((config or {}).get("REQUIRE_MACRO", False))
    default_macro = (config or {}).get("DEFAULT_MACRO", "CENTRO")
    if idx_macro < 0 and require_macro:
        raise RuntimeError("GSHEET | No se encontro columna MACRO y REQUIRE_MACRO=true.")

    month_header = _month_header_from_ctx(month_ctx)
    if not month_header:
        raise RuntimeError("GSHEET | No se pudo determinar el mes desde MES_A_PROCESAR.")

    month_candidates = MONTH_ALIASES.get(month_header, [month_header])
    idx_month = _find_col(headers_norm, [_norm_cell(x) for x in month_candidates])
    if idx_month < 0:
        raise RuntimeError(f"GSHEET | No se encontró la columna del mes '{month_header}' (candidatos={month_candidates}).")

    selected: List[Dict[str, str]] = []
    seen: set = set()
    dup = 0
    unchecked = 0
    empty = 0
    sin_macro = 0

    for row in values[1:]:
        cod = (row[idx_cod] if idx_cod < len(row) else "").strip()
        if not cod:
            empty += 1
            continue

        month_val = (row[idx_month] if idx_month < len(row) else "")
        if not _is_checked(month_val):
            unchecked += 1
            continue

        canon = cod
        if cod.isdigit():
            try:
                canon = str(int(cod))
            except Exception:
                canon = cod

        if canon in seen:
            dup += 1
            continue

        if idx_macro >= 0:
            macro = _norm_macro(row[idx_macro] if idx_macro < len(row) else "")
            if macro not in VALID_MACROS:
                macro = INVALID_MACRO_LABEL
                sin_macro += 1
        else:
            macro = default_macro

        seen.add(canon)
        selected.append({"centro": cod, "macro": macro})

    if logger:
        logger.info(
            f"GSHEET | tabla detectada | mes_col={month_header} | "
            f"seleccionados={len(selected)} | dup={dup} | unchecked={unchecked} | empty={empty} | sin_macro={sin_macro} | macro_default={default_macro if idx_macro < 0 else ''}"
        )

    return selected


# =========================
# Mes
# =========================
def _month_bounds(y: int, m: int) -> tuple[datetime.date, datetime.date]:
    first = datetime.date(y, m, 1)
    last = datetime.date(y, m, monthrange(y, m)[1])
    return first, last

def _from_token(token: str, today: datetime.date) -> dict:
    t = token.strip().upper()
    if t == "ACTUAL":
        y, m = today.year, today.month
    elif t == "ANTERIOR":
        y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    elif t == "SIGUIENTE":
        y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    else:
        mobj = re.match(r"^(\d{4})-(\d{2})$", t)
        if not mobj:
            raise ValueError(f"MES_A_PROCESAR inválido: {token}")
        y, m = int(mobj.group(1)), int(mobj.group(2))
        if not (1 <= m <= 12):
            raise ValueError(f"Mes inválido: {token}")

    first, last = _month_bounds(y, m)
    return {
        "LABEL": f"{y:04d}-{m:02d}",
        "MONTH_FIRST_DMY": first.strftime("%d/%m/%Y"),
        "MONTH_LAST_DMY": last.strftime("%d/%m/%Y"),
        "MONTH_FIRST_YMD": first.strftime("%Y%m%d"),
        "MONTH_LAST_YMD": last.strftime("%Y%m%d"),
        "MONTH_TAG": f"{first.strftime('%Y%m%d')}_{last.strftime('%Y%m%d')}",
    }


# =========================
# Chrome
# =========================
def build_chrome_options(download_dir: str, headless: bool, profile_base_dir: str, worker_id: str = "worker") -> Tuple[Options, str]:
    safe_worker = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(worker_id or "worker")).strip("_")[:80] or "worker"
    profile_dir = tempfile.mkdtemp(prefix=f"chrome-profile-{safe_worker}-", dir=profile_base_dir)

    opts = Options()
    opts.add_argument("--log-level=3")
    opts.add_argument(f"--user-data-dir={profile_dir}")
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    opts.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--mute-audio")
        opts.add_argument("--disable-background-networking")
        opts.add_argument("--blink-settings=imagesEnabled=false")
    return opts, profile_dir

def build_chrome_service() -> ChromeService:
    service = ChromeService(log_output=os.devnull)
    try:
        import subprocess as _sp
        if platform.system() == "Windows":
            service.creationflags = _sp.CREATE_NO_WINDOW
    except Exception:
        pass
    return service


def build_run_email_body(
    config: dict,
    start_dt: datetime.datetime,
    end_dt: datetime.datetime,
    exit_code: int,
    month_ctx: dict,
    rutas: List[str],
    checked_total: int,
    to_process_total: int,
    centros_ok: List[str],
    centros_fail: List[str],
    resultados: List[Dict[str, str]],
) -> str:
    ok = [r for r in resultados if r.get("status") == "OK"]
    fail = [r for r in resultados if r.get("status") != "OK"]
    lines = [
        "RPA Tele Apoyo al Diagnostico",
        "",
        f"Estado: {'OK' if exit_code == 0 else 'FAIL'}",
        f"Exit code: {exit_code}",
        f"Inicio: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Fin: {end_dt.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Duracion(s): {(end_dt - start_dt).total_seconds():.1f}",
        f"Mes: {month_ctx.get('LABEL', '')} | TAG={month_ctx.get('MONTH_TAG', '')}",
        f"Rutas: {rutas}",
        f"Centros con check: {checked_total}",
        f"Centros procesados: {to_process_total}",
        f"Centros OK: {len(centros_ok)}",
        f"Centros FAIL: {len(centros_fail)}",
        f"Eventos: {len(resultados)}",
        f"Eventos OK: {len(ok)}",
        f"Eventos FAIL: {len(fail)}",
        "",
        "Este correo fue generado automaticamente por el RPA.",
    ]
    if fail:
        lines.append("")
        lines.append("Fallas:")
        for r in fail[:30]:
            lines.append(f"- {r.get('centro','?')} | {r.get('tipo','?')} | {r.get('motivo','DESCONOCIDO')}")
    elif ok:
        lines.append("")
        lines.append("Archivos publicados:")
        for r in ok[:30]:
            lines.append(f"- {r.get('centro','?')} | {r.get('tipo','?')} | {r.get('archivo','')}")
    return "\n".join(lines)


def send_run_email(logger, config: dict, subject: str, body: str, attachment_path: str = "") -> None:
    if not config.get("MAIL_ENABLED"):
        logger.info("MAIL_SKIP | MAIL_ENABLED=false")
        return
    if not config.get("SMTP_TO"):
        logger.info("MAIL_SKIP | SMTP_TO vacio")
        return
    try:
        send_smtp_mail(
            smtp_host=config.get("SMTP_HOST", ""),
            smtp_port=int(config.get("SMTP_PORT", 587) or 587),
            smtp_user=config.get("SMTP_USER", ""),
            smtp_pass=config.get("SMTP_PASS", ""),
            mail_from=config.get("SMTP_FROM", ""),
            mail_to=config.get("SMTP_TO", []),
            mail_cc=config.get("SMTP_CC", []),
            subject=subject,
            body_text=body,
            attachment_path=attachment_path if attachment_path and os.path.exists(attachment_path) else None,
        )
        logger.info(
            f"MAIL_OK | to_count={len(config.get('SMTP_TO', []))} | cc_count={len(config.get('SMTP_CC', []))}"
        )
    except Exception as e:
        logger.info(f"MAIL_WARN | {type(e).__name__}: {e}")


# =========================
# Frames / Centro
# =========================
def switch_to_deep_cuerpo(driver, wait: WebDriverWait, max_depth: int = 6) -> int:
    driver.switch_to.default_content()
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "frame[name='cuerpo'],iframe[name='cuerpo']")))
    depth = 0
    for _ in range(max_depth):
        frames = driver.find_elements(By.CSS_SELECTOR, "frame[name='cuerpo'],iframe[name='cuerpo']")
        if not frames:
            break
        driver.switch_to.frame(frames[0])
        depth += 1
        time.sleep(0.2)
    return depth

def match_center_value(v: str, centro: str) -> bool:
    v = (v or "").strip()
    c = (centro or "").strip()
    if not v or not c:
        return False
    if v == c:
        return True
    try:
        return str(int(v)) == str(int(c))
    except Exception:
        return False

def wait_select_center_post_login(driver, centro: str, timeout: int = 30) -> bool:
    end = time.time() + timeout
    while time.time() < end and not STOP_EVENT.is_set():
        switch_to_deep_cuerpo(driver, WebDriverWait(driver, 10), max_depth=6)
        try:
            sel_el = driver.find_element(By.NAME, "centroAsistencial")
            sel = Select(sel_el)
            for o in sel.options:
                val = (o.get_attribute("value") or "").strip()
                if match_center_value(val, centro):
                    sel.select_by_value(val)
                    return True
        except NoSuchElementException:
            pass
        time.sleep(1)
    return False


# =========================
# Selects formulario (robustos)
# =========================
def _trigger_change(driver, element):
    driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles:true}));", element)

def find_select_by_value_el(driver, value: str, locators: List[tuple], label: str):
    wanted = (value or "").strip()
    for by, selector in locators:
        try:
            el = driver.find_element(by, selector)
            vals = [(o.get_attribute("value") or "").strip() for o in Select(el).options]
            if wanted in vals:
                return el
        except Exception:
            pass
    raise RuntimeError(f"No se encontró SELECT '{label}' con value={wanted}.")

def wait_select_by_value_el(driver, value: str, locators: List[tuple], label: str, timeout: int = 25):
    return WebDriverWait(driver, timeout).until(
        lambda d: find_select_by_value_el(d, value, locators, label)
    )

def find_select_servicio_el(driver, servicio_val: str):
    for by, selector in [(By.ID, "servicio"), (By.NAME, "servicio")]:
        try:
            el = driver.find_element(by, selector)
            vals = [(o.get_attribute("value") or "").strip() for o in Select(el).options]
            if servicio_val in vals:
                return el
        except Exception:
            pass
    for el in driver.find_elements(By.TAG_NAME, "select"):
        try:
            s = Select(el)
            for o in s.options:
                val = (o.get_attribute("value") or "").strip()
                if val == servicio_val:
                    return el
        except Exception:
            continue
    raise RuntimeError(f"No se encontró SELECT 'Servicio' con value={servicio_val}.")

def find_select_formato_el(driver):
    for by, selector in [(By.ID, "formatoArchivo"), (By.NAME, "formatoArchivo")]:
        try:
            el = driver.find_element(by, selector)
            vals = set((o.get_attribute("value") or "").strip() for o in Select(el).options)
            if "xls" in vals:
                return el
        except Exception:
            pass
    for el in driver.find_elements(By.TAG_NAME, "select"):
        try:
            s = Select(el)
            vals = set((o.get_attribute("value") or "").strip() for o in s.options)
            if "xls" in vals:
                return el
        except Exception:
            continue
    raise RuntimeError("No se encontró SELECT 'Tipo Archivo' con value=xls.")

def find_date_inputs(driver):
    def _find(cands):
        for by, sel in cands:
            try:
                return driver.find_element(by, sel)
            except Exception:
                continue
        return None

    fi = _find([
        (By.ID, "fe_ini"), (By.NAME, "fe_ini"),
        (By.ID, "fechaIni"), (By.NAME, "fechaIni"),
        (By.ID, "fechaInicio"), (By.NAME, "fechaInicio"),
    ])
    ff = _find([
        (By.ID, "fechaFin"), (By.NAME, "fechaFin"),
        (By.ID, "fe_fin"), (By.NAME, "fe_fin"),
        (By.ID, "fechaFinal"), (By.NAME, "fechaFinal"),
    ])
    if not fi or not ff:
        raise RuntimeError("No se pudieron ubicar inputs Fecha Inicio / Fecha Fin.")
    return fi, ff


# =========================
# Validación nombre archivo
# =========================
def validate_filename(centro: str, month_ctx: dict, expected_suffix: str, filename: str) -> tuple[bool, str]:
    if not filename or not filename.lower().endswith(".txt"):
        return False, "NOMBRE_INVALIDO"

    if not filename_matches_expected_suffix(filename, expected_suffix):
        return False, "SUFIJO_MISMATCH"

    prefix = f"{centro}_{month_ctx['MONTH_FIRST_YMD']}_{month_ctx['MONTH_LAST_YMD']}_"
    if not filename.startswith(prefix):
        return False, "PREFIJO_TAG_MISMATCH"

    return True, ""

def month_name_from_ctx(month_ctx: dict) -> str:
    try:
        month_num = int(str(month_ctx.get("LABEL", "")).split("-")[1])
    except Exception:
        month_num = int(str(month_ctx.get("MONTH_FIRST_DMY", "01/01/1900")).split("/")[1])
    return MONTHS_ES.get(month_num, "")

def build_publish_filename(centro: str, month_ctx: dict, ruta: dict, source_filename: str) -> tuple[str, str]:
    if not ruta.get("rename_to_month"):
        return source_filename, ruta.get("expected_suffix", "")
    month_name = month_name_from_ctx(month_ctx)
    if not month_name:
        raise RuntimeError("No se pudo determinar el nombre del mes para renombrar.")
    ext = Path(source_filename).suffix or ".txt"
    target = f"{centro}_{month_ctx['MONTH_FIRST_YMD']}_{month_ctx['MONTH_LAST_YMD']}_{month_name}{ext}"
    return target, month_name


# =========================
# Login + centro + abrir formulario (con DELAYS)
# =========================
def open_form_for_center(logger, driver, config: dict, centro: str, route_url: str) -> None:
    wait = WebDriverWait(driver, 25)
    driver.get(config["URL_HOME"])

    switch_to_deep_cuerpo(driver, wait, max_depth=6)
    wait.until(EC.presence_of_element_located((By.NAME, "USER"))).clear()
    driver.find_element(By.NAME, "USER").send_keys(config["USER"])
    driver.find_element(By.NAME, "PASS").clear()
    driver.find_element(By.NAME, "PASS").send_keys(config["PASS"])
    driver.find_element(By.NAME, "Submit").click()

    if STOP_EVENT.is_set():
        raise RuntimeError("CANCELADO")

    ok = wait_select_center_post_login(driver, centro, timeout=30)
    if config["REQUIRE_CENTER"] and not ok:
        raise RuntimeError("NO_SELECCIONO_CENTRO")

    if config["DELAY_AFTER_SELECT_CENTER"] > 0:
        logger.debug(f"DELAY | after_select_center={config['DELAY_AFTER_SELECT_CENTER']}s")
        time.sleep(config["DELAY_AFTER_SELECT_CENTER"])

    try:
        driver.find_element(By.NAME, "Submit").click()
    except Exception:
        driver.find_element(By.XPATH, "//input[contains(translate(@value,'INGRESAR','ingresar'),'ingresar')]").click()

    if config["DELAY_AFTER_SUBMIT_CENTER"] > 0:
        logger.debug(f"DELAY | after_submit_center={config['DELAY_AFTER_SUBMIT_CENTER']}s")
        time.sleep(config["DELAY_AFTER_SUBMIT_CENTER"])

    if STOP_EVENT.is_set():
        raise RuntimeError("CANCELADO")

    if config["DELAY_BEFORE_OPEN_FORM"] > 0:
        logger.debug(f"DELAY | before_open_form={config['DELAY_BEFORE_OPEN_FORM']}s")
        time.sleep(config["DELAY_BEFORE_OPEN_FORM"])

    driver.switch_to.default_content()
    driver.get(route_url)
    WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.ID, "boton")))


# =========================
# Formulario: set + imprimir
# =========================
def fill_form(driver, config: dict, month_ctx: dict, ruta: dict) -> None:
    wait = WebDriverWait(driver, 25)

    formato_val = config["FORMATO_ARCHIVO"]
    route_code = ruta["code"]

    wait.until(lambda d: len(d.find_elements(By.TAG_NAME, "select")) >= 1)

    if route_code == "RESULTADO_TIPO_EXAMEN":
        el_tipo = wait_select_by_value_el(
            driver,
            config["TIPO_EXAMEN"],
            [(By.ID, "tipoExamen"), (By.NAME, "tipoExamen")],
            "Tipo de Examen",
        )
        Select(el_tipo).select_by_value(config["TIPO_EXAMEN"])
        _trigger_change(driver, el_tipo)

        el_area = wait_select_by_value_el(
            driver,
            config["AREA"],
            [(By.ID, "area"), (By.NAME, "area")],
            "Area",
        )
        Select(el_area).select_by_value(config["AREA"])
        _trigger_change(driver, el_area)

        el_serv = wait_select_by_value_el(
            driver,
            config["SERVICIO"],
            [(By.ID, "idServicio"), (By.ID, "servicio"), (By.NAME, "servicio")],
            "Servicio",
        )
        Select(el_serv).select_by_value(config["SERVICIO"])
        _trigger_change(driver, el_serv)

    fi, ff = find_date_inputs(driver)
    fi.clear(); fi.send_keys(month_ctx["MONTH_FIRST_DMY"])
    ff.clear(); ff.send_keys(month_ctx["MONTH_LAST_DMY"])

    el_fmt = find_select_formato_el(driver)
    Select(el_fmt).select_by_value(formato_val)
    _trigger_change(driver, el_fmt)

def click_imprimir(driver) -> None:
    WebDriverWait(driver, 25).until(EC.element_to_be_clickable((By.ID, "boton"))).click()


def descargar_centro_tipo(
    logger,
    config: dict,
    centro: str,
    month_ctx: dict,
    ruta: dict,
    user_label: str,
    user: str,
    pwd: str,
) -> Dict[str, str]:
    route_code = ruta["code"]
    final_dir = ruta["download_dir"]
    expected_suffix = ruta["expected_suffix"]
    prefix = f"{centro}_{month_ctx['MONTH_FIRST_YMD']}_{month_ctx['MONTH_LAST_YMD']}_"

    login_config = dict(config)
    login_config["USER"] = user
    login_config["PASS"] = pwd

    res = {
        "centro": centro,
        "tipo": route_code,
        "status": "FAIL",
        "motivo": "DESCONOCIDO",
        "archivo": "",
        "attempt": "0",
        "seconds": "0",
        "download_dir": final_dir,
        "staging_dir": "",
        "user": user_label,
    }

    if STOP_EVENT.is_set():
        res["motivo"] = "CANCELADO"
        return res

    max_attempts = config["RETRY_PER_CENTER"] + 1

    for attempt in range(1, max_attempts + 1):
        if STOP_EVENT.is_set():
            res["motivo"] = "CANCELADO"
            return res

        t0 = time.time()
        driver = None
        profile_dir = ""
        attempt_download_dir = os.path.join(
            config["STAGING_DOWNLOAD_DIR"],
            route_code.lower(),
            f"{centro}_{month_ctx['MONTH_TAG']}_{ts_now()}_a{attempt}",
        )
        ensure_dir(attempt_download_dir)
        res["staging_dir"] = attempt_download_dir
        try:
            remove_partial_with_prefix(logger, attempt_download_dir, prefix, unconfirmed_age_min=10)

            options, profile_dir = build_chrome_options(
                attempt_download_dir,
                config["HEADLESS"],
                config["CHROME_PROFILE_BASE_DIR"],
                worker_id=f"{centro}-{route_code}-{user_label}-a{attempt}",
            )
            logger.info(f"TMP_PROFILE_CREATE | {profile_dir}")
            driver = webdriver.Chrome(
                options=options,
                service=build_chrome_service()
            )

            logger.info(
                f"RUN | centro={centro} | ruta={route_code} | user={user_label} | "
                f"attempt={attempt} | staging={attempt_download_dir} | final={final_dir}"
            )

            open_form_for_center(logger, driver, login_config, centro, ruta["url"])
            fill_form(driver, config, month_ctx, ruta)
            click_imprimir(driver)

            archivo = esperar_descarga_por_prefijo(
                download_dir=attempt_download_dir,
                prefix=prefix,
                expected_suffix=expected_suffix,
                timeout=config["DOWNLOAD_TIMEOUT"],
                stable_secs=config["STABLE_SECS"],
                poll_interval=config["POLL_INTERVAL"],
            )
            if not archivo:
                res["motivo"] = "TIMEOUT_DESCARGA"
                res["attempt"] = str(attempt)
                res["seconds"] = f"{time.time() - t0:.1f}"
                remove_partial_with_prefix(logger, attempt_download_dir, prefix, unconfirmed_age_min=10)
                continue

            ok_name, reason = validate_filename(centro, month_ctx, expected_suffix, archivo)
            if not ok_name:
                res["motivo"] = reason
                res["attempt"] = str(attempt)
                res["seconds"] = f"{time.time() - t0:.1f}"
                continue

            fullpath = os.path.join(attempt_download_dir, archivo)
            if archivo_esta_vacio(fullpath):
                res["motivo"] = "ARCHIVO_VACIO"
                res["attempt"] = str(attempt)
                res["seconds"] = f"{time.time() - t0:.1f}"
                continue

            if not file_is_stable(fullpath, config["STABLE_SECS"]):
                res["motivo"] = "ARCHIVO_NO_ESTABLE"
                res["attempt"] = str(attempt)
                res["seconds"] = f"{time.time() - t0:.1f}"
                continue

            target_filename, final_expected_suffix = build_publish_filename(centro, month_ctx, ruta, archivo)
            final_path = publish_validated_download(
                logger,
                fullpath,
                final_dir,
                prefix,
                expected_suffix,
                target_filename=target_filename,
                final_expected_suffix=final_expected_suffix,
            )

            res["status"] = "OK"
            res["motivo"] = ""
            res["archivo"] = os.path.basename(final_path)
            res["archivo_descargado"] = archivo
            res["final_path"] = final_path
            res["attempt"] = str(attempt)
            res["seconds"] = f"{time.time() - t0:.1f}"
            return res

        except Exception as e:
            res["motivo"] = f"EXCEPTION:{type(e).__name__}"
            res["attempt"] = str(attempt)
            res["seconds"] = f"{time.time() - t0:.1f}"
        finally:
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass
            if profile_dir:
                if safe_rmtree(profile_dir):
                    logger.info(f"TMP_PROFILE_DELETE | {profile_dir}")
                else:
                    logger.info(f"TMP_PROFILE_DELETE_WARN | {profile_dir}")
            if attempt_download_dir:
                if safe_rmtree(attempt_download_dir):
                    logger.info(f"STAGING_DELETE | {attempt_download_dir}")
                else:
                    logger.info(f"STAGING_DELETE_WARN | {attempt_download_dir}")
                cleanup_empty_dirs(config["STAGING_DOWNLOAD_DIR"], logger)

            for _ in range(config["BETWEEN_DOWNLOADS_DELAY"]):
                if STOP_EVENT.is_set():
                    break
                time.sleep(1)

    return res


# =========================
# Logs: purga de runs antiguos + helpers
# =========================
def _fmt_list(items: List[str], max_items: int) -> str:
    if max_items <= 0:
        return str(items)
    if len(items) <= max_items:
        return str(items)
    return str(items[:max_items])[:-1] + f", ... (+{len(items)-max_items})]"

def purge_old_run_dirs(logger, logs_dir: str, retention_days: int, keep_dir: str = "") -> int:
    if retention_days <= 0:
        return 0

    base = Path(logs_dir)
    if not base.exists():
        return 0

    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=retention_days)

    rx = re.compile(r"^RUN_.*_(\d{8})_(\d{6})$")
    removed = 0

    for p in base.iterdir():
        if not p.is_dir():
            continue
        if keep_dir and os.path.abspath(str(p)) == os.path.abspath(keep_dir):
            continue
        if not p.name.startswith("RUN_"):
            continue

        dt = None
        m = rx.match(p.name)
        if m:
            try:
                dt = datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            except Exception:
                dt = None

        if dt is None:
            try:
                dt = datetime.datetime.fromtimestamp(p.stat().st_mtime)
            except Exception:
                continue

        if dt < cutoff:
            try:
                shutil.rmtree(p, ignore_errors=True)
                removed += 1
            except Exception as e:
                logger.debug(f"LOG_PURGE_ERR | {p} | {type(e).__name__}:{e}")

    return removed


# =========================
# Main
# =========================
def main():
    config = load_config()
    logger, run_dir, logfile = setup_run_logger(
        config["LOGS_DIR"], config["RUN_NAME"], config.get("LOG_MODE", "PROD")
    )

    start_dt = datetime.datetime.now()
    logger.info("CONFIG_OK | .env cargado")
    logger.info(f"RUN_DIR | {run_dir}")
    logger.info(f"LOGFILE | {logfile}")
    logger.info(f"CHROME_PROFILE_BASE_DIR | {config['CHROME_PROFILE_BASE_DIR']}")
    removed_profiles = cleanup_old_chrome_profiles(
        config["CHROME_PROFILE_BASE_DIR"],
        config["CHROME_PROFILE_MAX_AGE_HOURS"],
        logger,
    )
    if removed_profiles:
        logger.info(f"TMP_PROFILE_CLEANUP_SUMMARY | start_removed={removed_profiles}")

    rutas = config["ROUTES"]
    route_codes = [r["code"] for r in rutas]
    if not rutas:
        logger.info("RUN_SKIP | Todas las rutas TAD estan en false. No hay nada que ejecutar.")
        sys.exit(1)

    # Mes objetivo
    try:
        month_ctx = _from_token(config["MES_A_PROCESAR"], datetime.date.today())
    except Exception as e:
        logger.info(f"❌ MES_A_PROCESAR inválido: {e}")
        sys.exit(1)

    # Centros desde Google Sheets (checks por mes) con macroregion
    centros_meta = get_centros_from_gsheet(
        config["CREDS_JSON"],
        config["GSHEET_URL"],
        config["GSHEET_TAB"],
        month_ctx,
        logger=logger,
        config=config
    )

    checked_total = len(centros_meta)

    # Si no hay marcados -> fin limpio (exit 0)
    if not centros_meta:
        mes_txt = _month_header_from_ctx(month_ctx) or month_ctx.get("LABEL", "MES")
        logger.info(f"GSHEET | No hay IPRESS marcadas para el mes {mes_txt}. Fin sin descargas.")

        removed = purge_old_run_dirs(
            logger, config["LOGS_DIR"], config.get("LOG_RETENTION_DAYS", 14), keep_dir=run_dir
        )
        if removed:
            logger.info(f"LOG_PURGE | removed={removed} | retention_days={config.get('LOG_RETENTION_DAYS', 14)}")
        end_dt = datetime.datetime.now()
        send_run_email(
            logger,
            config,
            "[OK] RPA Tele Apoyo al Diagnostico | exit_code=0",
            build_run_email_body(config, start_dt, end_dt, 0, month_ctx, route_codes, 0, 0, [], [], []),
            logfile,
        )
        sys.exit(0)

    # Filtros opcionales
    if config["CENTERS_FILTER"]:
        allowed = set(config["CENTERS_FILTER"])
        centros_meta = [x for x in centros_meta if x["centro"] in allowed]

    if config["MAX_CENTERS"] and config["MAX_CENTERS"] > 0:
        centros_meta = centros_meta[: config["MAX_CENTERS"]]

    centros = [x["centro"] for x in centros_meta]
    to_process_total = len(centros)
    max_list = config.get("LOG_MAX_LIST", 50)

    logger.info(
        f"MONTH | {month_ctx['LABEL']} | {month_ctx['MONTH_FIRST_DMY']} -> {month_ctx['MONTH_LAST_DMY']} | "
        f"TAG={month_ctx['MONTH_TAG']}"
    )
    logger.info(f"INPUT | Centros con check={checked_total} | a_procesar={to_process_total}")
    logger.info(f"INPUT_LIST | {_fmt_list(centros, max_list)}")

    center_results: Dict[str, Dict[str, str]] = {c: {} for c in centros}
    resultados: List[Dict[str, str]] = []

    sin_macro_centros = [x["centro"] for x in centros_meta if x.get("macro") not in VALID_MACROS]
    if sin_macro_centros:
        logger.info(f"SIN_MACRO_QUEUE | total={len(sin_macro_centros)} | centros={_fmt_list(sin_macro_centros, max_list)}")

    try:
        for macro in VALID_MACROS:
            if STOP_EVENT.is_set():
                logger.info("🛑 Cancelado por el usuario (Ctrl+C).")
                break

            centros_macro = [x["centro"] for x in centros_meta if x.get("macro") == macro]
            if not centros_macro:
                continue

            creds = config["MACRO_USERS"].get(macro)
            if not creds:
                logger.info(f"MACRO_SKIP | {macro} | sin credenciales | total={len(centros_macro)}")
                continue
            user, pwd = creds
            user_label = f"MACRO_{macro.replace(' ', '_')}"

            macro_ok = 0
            macro_fail = 0
            logger.info(f"MACRO_START | {macro} | user={user} | total={len(centros_macro)}")

            for centro in centros_macro:
                if STOP_EVENT.is_set():
                    break

                for ruta in rutas:
                    if STOP_EVENT.is_set():
                        break

                    route_code = ruta["code"]
                    r = descargar_centro_tipo(logger, config, centro, month_ctx, ruta, user_label, user, pwd)
                    resultados.append(r)
                    center_results[centro][route_code] = r["status"]

                    if r["status"] == "OK":
                        macro_ok += 1
                        logger.info(f"OK   | {centro} | {route_code} | {user_label} | {r['archivo']} | {r['seconds']}s")
                    else:
                        macro_fail += 1
                        logger.info(f"FAIL | {centro} | {route_code} | {user_label} | {r['motivo']} | {r['seconds']}s")

            logger.info(f"MACRO_END | {macro} | OK:{macro_ok} | FAIL:{macro_fail}")

    finally:
        for ruta in rutas:
            purge_old_partials(logger, ruta["download_dir"], max_age_minutes=config["PURGE_PARTIALS_AGE_MIN"])
        cleanup_empty_dirs(config["STAGING_DOWNLOAD_DIR"], logger, remove_root=True)
        cleanup_empty_dirs(config["CHROME_PROFILE_BASE_DIR"], logger, remove_root=True)
        cleanup_empty_dirs(str(get_project_dir() / "tmp"), logger, remove_root=True)
        kill_chromedrivers()
        removed_profiles = cleanup_old_chrome_profiles(
            config["CHROME_PROFILE_BASE_DIR"],
            config["CHROME_PROFILE_MAX_AGE_HOURS"],
            logger,
        )
        if removed_profiles:
            logger.info(f"TMP_PROFILE_CLEANUP_SUMMARY | end_removed={removed_profiles}")

    # Resumen por centro (OK si TODAS las rutas habilitadas publicaron archivo)
    total_centros = len(centros)
    centros_ok: List[str] = []
    centros_fail: List[str] = []

    for centro in centros:
        per = center_results.get(centro, {})
        if all(per.get(code) == "OK" for code in route_codes):
            centros_ok.append(centro)
        else:
            centros_fail.append(centro)

    end_dt = datetime.datetime.now()
    dur = (end_dt - start_dt).total_seconds()

    logger.info("===== RESUMEN FINAL =====")
    logger.info(f"Fecha inicio        : {start_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Fecha fin           : {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Duración(s)         : {dur:.1f}")
    logger.info(f"Mes                 : {month_ctx['LABEL']} | TAG={month_ctx['MONTH_TAG']}")
    logger.info(f"Rutas               : {route_codes}")
    logger.info(f"Centros con check   : {checked_total}")
    logger.info(f"Centros procesados  : {to_process_total}")
    logger.info(f"Centros OK          : {len(centros_ok)}/{total_centros} -> {_fmt_list(centros_ok, max_list)}")
    logger.info(f"Centros FAIL        : {len(centros_fail)}/{total_centros} -> {_fmt_list(centros_fail, max_list)}")

    # Detalle por motivo (solo si hubo fails)
    fails = [r for r in resultados if r["status"] != "OK"]
    if fails:
        by_reason: Dict[str, List[str]] = {}
        for r in fails:
            by_reason.setdefault(r["motivo"], []).append(f"{r['centro']}|{r['tipo']}")
        for motivo, items in by_reason.items():
            logger.info(f"FAIL_DETAIL | {motivo} -> {_fmt_list(items, max_list)}")

    # Purga de logs antiguos
    removed = purge_old_run_dirs(
        logger, config["LOGS_DIR"], config.get("LOG_RETENTION_DAYS", 14), keep_dir=run_dir
    )
    if removed:
        logger.info(f"LOG_PURGE | removed={removed} | retention_days={config.get('LOG_RETENTION_DAYS', 14)}")

    exit_code = 130 if STOP_EVENT.is_set() else (0 if len(centros_fail) == 0 else 2)
    subject_status = "OK" if exit_code == 0 else "FAIL"
    send_run_email(
        logger,
        config,
        f"[{subject_status}] RPA Tele Apoyo al Diagnostico | exit_code={exit_code}",
        build_run_email_body(
            config,
            start_dt,
            end_dt,
            exit_code,
            month_ctx,
            route_codes,
            checked_total,
            to_process_total,
            centros_ok,
            centros_fail,
            resultados,
        ),
        logfile,
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
