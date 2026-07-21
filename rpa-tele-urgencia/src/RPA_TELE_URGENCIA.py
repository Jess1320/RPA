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


def setup_run_logger(logs_dir: str, run_name: str):
    run_id = f"RUN_{run_name}_{ts_now()}"
    run_dir = os.path.join(logs_dir, run_id)
    ensure_dir(run_dir)

    logfile = os.path.join(run_dir, "run.log")

    logger = logging.getLogger(run_name)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        for h in list(logger.handlers):
            logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)

    return logger, run_dir, logfile


def cleanup_old_runs(logger, logs_dir: str, retention_days: int):
    """Elimina carpetas logs/RUN_* antiguas para evitar acumulación."""
    if retention_days <= 0:
        return
    cutoff = datetime.datetime.now() - datetime.timedelta(days=retention_days)
    try:
        for p in Path(logs_dir).glob("RUN_*"):
            if p.is_dir():
                mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime)
                if mtime < cutoff:
                    shutil.rmtree(p, ignore_errors=True)
                    logger.info(f"LOG_RETENTION | deleted_dir | {p}")
    except Exception as e:
        logger.info(f"LOG_RETENTION_ERR | {type(e).__name__}:{e}")


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


def remove_partial_with_prefix(logger, download_dir: str, prefix: str, unconfirmed_age_min: int = 10) -> int:
    removed = 0
    now = time.time()

    # Parciales y duplicados del prefijo
    for f in files_with_prefix(download_dir, prefix):
        low = f.lower()
        if low.endswith((".crdownload", ".tmp", ".part")) or " (1)." in low or " (2)." in low or " (3)." in low:
            try:
                os.remove(os.path.join(download_dir, f))
                removed += 1
                logger.info(f"PRETRY_CLEAN | {download_dir} | {f}")
            except Exception as e:
                logger.info(f"PRETRY_CLEAN_ERR | {download_dir} | {f} | {type(e).__name__}:{e}")

    # Unconfirmed / Sin confirmar viejos
    for f in listar_archivos(download_dir):
        low = f.lower()
        if low.endswith(".crdownload") and ("unconfirmed" in low or "sin confirmar" in low):
            p = os.path.join(download_dir, f)
            try:
                if now - os.path.getmtime(p) > unconfirmed_age_min * 60:
                    os.remove(p)
                    removed += 1
                    logger.info(f"PRETRY_CLEAN_UNCONF | {download_dir} | {f}")
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
                    logger.info(f"PURGE_PARTIAL | {download_dir} | {f}")
            except Exception:
                pass


def clean_existing_finals(logger, download_dir: str, prefix: str, expected_suffix: str) -> int:
    deleted = 0
    exp = expected_suffix.lower()

    for f in listar_archivos(download_dir):
        low = f.lower()
        if f.startswith(prefix) and low.endswith(".txt") and low.endswith(exp):
            try:
                os.remove(os.path.join(download_dir, f))
                deleted += 1
                logger.info(f"CLEAN_DELETE | {download_dir} | {f}")
            except Exception as e:
                logger.info(f"CLEAN_ERR | {download_dir} | {f} | {type(e).__name__}:{e}")

    for f in listar_archivos(download_dir):
        low = f.lower()
        if f.startswith(prefix) and low.endswith(".txt") and (" (1)." in low or " (2)." in low or " (3)." in low):
            try:
                os.remove(os.path.join(download_dir, f))
                deleted += 1
                logger.info(f"CLEAN_DUP_DELETE | {download_dir} | {f}")
            except Exception:
                pass

    return deleted


def esperar_descarga_por_prefijo(
    download_dir: str,
    prefix: str,
    expected_suffix: str,
    timeout: int,
    stable_secs: int,
    poll_interval: int
) -> str:
    start = time.time()
    expected_suffix_l = expected_suffix.lower()

    while time.time() - start <= timeout:
        if STOP_EVENT.is_set():
            return ""

        files = files_with_prefix(download_dir, prefix)
        partials = [f for f in files if f.lower().endswith((".crdownload", ".tmp", ".part"))]

        finals = [
            f for f in files
            if f.lower().endswith(".txt")
            and " (" not in f
            and f.lower().endswith(expected_suffix_l)
        ]

        if finals and not partials:
            finals.sort(key=lambda x: os.path.getmtime(os.path.join(download_dir, x)), reverse=True)
            cand = finals[0]
            cand_path = os.path.join(download_dir, cand)
            if file_is_stable(cand_path, stable_secs):
                return cand

        time.sleep(poll_interval)

    return ""


def replicar_a_espejos(logger, src_fullpath: str, mirrors: List[str], filename: str):
    for mdir in mirrors:
        try:
            ensure_dir(mdir)
            dst = os.path.join(mdir, filename)
            shutil.copy2(src_fullpath, dst)
            logger.info(f"REPLICA_OK | {mdir} | {filename}")
        except Exception as e:
            logger.info(f"REPLICA_ERR | {mdir} | {filename} | {type(e).__name__}:{e}")


# =========================
# Config desde .env
# =========================
def _parse_bool(v: Optional[str], default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "si", "sí")


def parse_download_dirs(env_val: Optional[str], legacy: Optional[str]) -> List[str]:
    if env_val and env_val.strip():
        dirs = [d.strip() for d in env_val.split(",") if d.strip()]
        if dirs:
            return dirs
    if legacy and legacy.strip():
        return [legacy.strip()]
    return []


def load_config() -> dict:
    load_rpa_env_files()

    url_home = os.getenv("URL_HOME")
    frm_masivas = os.getenv("FRM_MASIVAS")

    # Legacy: se mantiene solo para transicion si aun no existe .env_usuarios.
    usuarios: List[Tuple[str, str, str]] = []
    for i in range(1, 51):
        u = os.getenv(f"USER_{i}")
        p = os.getenv(f"PASSWORD_{i}")
        if u and p:
            usuarios.append((f"USER_{i}", u.strip(), p.strip()))

    macro_users = {
        "CENTRO": (os.getenv("USER_CENTRO", "").strip(), os.getenv("PASSWORD_CENTRO", "").strip()),
        "NORTE": (os.getenv("USER_NORTE", "").strip(), os.getenv("PASSWORD_NORTE", "").strip()),
        "SUR": (os.getenv("USER_SUR", "").strip(), os.getenv("PASSWORD_SUR", "").strip()),
        "LIMA ORIENTE": (os.getenv("USER_LIMA_ORIENTE", "").strip(), os.getenv("PASSWORD_LIMA_ORIENTE", "").strip()),
    }
    default_macro = _norm_macro(os.getenv("DEFAULT_MACRO", "CENTRO"))
    if default_macro not in VALID_MACROS:
        default_macro = "CENTRO"
    require_macro = _parse_bool(os.getenv("REQUIRE_MACRO"), default=False)

    gsheet_url = os.getenv("GSHEET_URL")
    gsheet_tab = os.getenv("GSHEET_TAB", "Centros")
    creds_json = os.getenv("CREDS_JSON")

    # descargas (1+ rutas)
    download_dirs = parse_download_dirs(os.getenv("DOWNLOAD_DIRS"), os.getenv("DOWNLOAD_DIR"))
    download_primary = download_dirs[0] if download_dirs else None
    download_mirrors = download_dirs[1:] if len(download_dirs) > 1 else []

    # formato / formulario
    mes_a_procesar = (os.getenv("MES_A_PROCESAR", "ACTUAL") or "ACTUAL").strip()
    formato_archivo = (os.getenv("FORMATO_ARCHIVO", "xls") or "xls").strip()
    mostrar_por = (os.getenv("MOSTRAR_POR", "1") or "1").strip()   # PROFESIONAL = 1
    topico = (os.getenv("TOPICO", "00") or "00").strip()           # TODOS = 00
    file_suffix = (os.getenv("FILE_SUFFIX", "PacAtendxTopico.txt") or "PacAtendxTopico.txt").strip()

    # motor
    headless = _parse_bool(os.getenv("HEADLESS"), default=False)
    chrome_profile_base_dir = get_chrome_profile_base_dir()
    chrome_profile_max_age_hours = int(os.getenv("CHROME_PROFILE_MAX_AGE_HOURS", "12"))
    download_timeout = int(os.getenv("DOWNLOAD_TIMEOUT", "1500"))
    stable_secs = int(os.getenv("STABLE_SECS", "3"))
    poll_interval = int(os.getenv("POLL_INTERVAL", "2"))
    retry_per_center = int(os.getenv("RETRY_PER_CENTER", "1"))
    between_delay = int(os.getenv("BETWEEN_DOWNLOADS_DELAY", "2"))
    clean_before = _parse_bool(os.getenv("CLEAN_BEFORE"), default=True)
    purge_age_min = int(os.getenv("PURGE_PARTIALS_AGE_MIN", "30"))
    require_center = _parse_bool(os.getenv("REQUIRE_CENTER"), default=True)

    # delays
    delay_after_select_center = int(os.getenv("DELAY_AFTER_SELECT_CENTER", "1"))
    delay_after_submit_center = int(os.getenv("DELAY_AFTER_SUBMIT_CENTER", "1"))
    delay_before_open_form = int(os.getenv("DELAY_BEFORE_OPEN_FORM", "1"))

    # logs
    run_name = os.getenv("RUN_NAME", "TELE_URGENCIA")
    logs_dir = os.getenv("LOGS_DIR", "logs")
    log_mode = os.getenv("LOG_MODE", "COMPACT").strip().upper()  # COMPACT | VERBOSE
    log_retention_days = int(os.getenv("LOG_RETENTION_DAYS", "7"))

    # correo
    mail_enabled = _parse_bool(os.getenv("MAIL_ENABLED"), default=False)
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587") or "587")
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user).strip()
    smtp_to = _split_recipients(os.getenv("SMTP_TO", ""))
    smtp_cc = _split_recipients(os.getenv("SMTP_CC", ""))

    # opcionales
    max_centers = int(os.getenv("MAX_CENTERS", "0"))
    centers_filter_raw = (os.getenv("CENTERS_FILTER", "") or "").strip()
    centers_filter = [c.strip() for c in centers_filter_raw.split(",") if c.strip()] if centers_filter_raw else []

    faltan = []
    for k, v in [
        ("URL_HOME", url_home),
        ("FRM_MASIVAS", frm_masivas),
        ("GSHEET_URL", gsheet_url),
        ("GSHEET_TAB", gsheet_tab),
        ("CREDS_JSON", creds_json),
        ("DOWNLOAD_DIRS/DOWNLOAD_DIR", download_primary),
    ]:
        if not v:
            faltan.append(k)
    if len(usuarios) == 0:
        if all(not u or not p for u, p in macro_users.values()):
            faltan.append("credenciales macro o al menos un par USER_n / PASSWORD_n")

    configured_macros = {m: creds for m, creds in macro_users.items() if creds[0] and creds[1]}
    if configured_macros:
        for macro in VALID_MACROS:
            if macro not in configured_macros:
                faltan.append(f"credenciales macro {macro}")
    elif usuarios:
        _, u, p = usuarios[0]
        macro_users = {default_macro: (u, p)}

    if faltan:
        print("❌ Faltan variables en .env:", faltan, flush=True)
        sys.exit(1)

    ensure_dir(logs_dir)
    ensure_dir(download_primary)
    for d in download_mirrors:
        ensure_dir(d)

    return {
        "URL_HOME": url_home,
        "FRM_MASIVAS": frm_masivas,

        "USUARIOS": usuarios,
        "MACRO_USERS": macro_users,
        "DEFAULT_MACRO": default_macro,
        "REQUIRE_MACRO": require_macro,

        "GSHEET_URL": gsheet_url,
        "GSHEET_TAB": gsheet_tab,
        "CREDS_JSON": creds_json,

        "DOWNLOAD_DIRS": download_dirs,
        "DOWNLOAD_PRIMARY": download_primary,
        "DOWNLOAD_MIRRORS": download_mirrors,

        "MES_A_PROCESAR": mes_a_procesar,
        "FORMATO_ARCHIVO": formato_archivo,
        "MOSTRAR_POR": mostrar_por,
        "TOPICO": topico,
        "FILE_SUFFIX": file_suffix,

        "HEADLESS": headless,
        "CHROME_PROFILE_BASE_DIR": chrome_profile_base_dir,
        "CHROME_PROFILE_MAX_AGE_HOURS": chrome_profile_max_age_hours,
        "DOWNLOAD_TIMEOUT": download_timeout,
        "STABLE_SECS": stable_secs,
        "POLL_INTERVAL": poll_interval,
        "RETRY_PER_CENTER": retry_per_center,
        "BETWEEN_DOWNLOADS_DELAY": between_delay,
        "CLEAN_BEFORE": clean_before,
        "PURGE_PARTIALS_AGE_MIN": purge_age_min,
        "REQUIRE_CENTER": require_center,

        "DELAY_AFTER_SELECT_CENTER": delay_after_select_center,
        "DELAY_AFTER_SUBMIT_CENTER": delay_after_submit_center,
        "DELAY_BEFORE_OPEN_FORM": delay_before_open_form,

        "RUN_NAME": run_name,
        "LOGS_DIR": logs_dir,
        "LOG_MODE": log_mode,
        "LOG_RETENTION_DAYS": log_retention_days,

        "MAIL_ENABLED": mail_enabled,
        "SMTP_HOST": smtp_host,
        "SMTP_PORT": smtp_port,
        "SMTP_USER": smtp_user,
        "SMTP_PASS": smtp_pass,
        "SMTP_FROM": smtp_from,
        "SMTP_TO": smtp_to,
        "SMTP_CC": smtp_cc,

        "MAX_CENTERS": max_centers,
        "CENTERS_FILTER": centers_filter,
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

MONTH_ALIASES = {"SEPTIEMBRE": ["SEPTIEMBRE", "SETIEMBRE"]}


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
    is_table = ("COD_IPRESS" in headers_norm) or any(h in all_month_headers or h == "SETIEMBRE" for h in headers_norm)

    if not is_table:
        centros = ws.col_values(1)
        if centros and not centros[0].strip().isdigit():
            centros = centros[1:]
        centros = [c.strip() for c in centros if c and c.strip()]
        if config and config.get("REQUIRE_MACRO"):
            raise RuntimeError("GSHEET | La hoja simple no tiene columna MACRO y REQUIRE_MACRO=true.")
        default_macro = (config or {}).get("DEFAULT_MACRO", "CENTRO")
        if logger:
            logger.info(f"GSHEET | formato simple detectado | tab={gsheet_tab} | centros={len(centros)} | macro_default={default_macro}")
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
            f"GSHEET | tabla detectada | tab={gsheet_tab} | mes_col={month_header} | "
            f"seleccionados={len(selected)} | dup={dup} | unchecked={unchecked} | empty={empty} | sin_macro={sin_macro} | macro_default={default_macro if idx_macro < 0 else ''}"
        )

    return selected


# =========================
# Mes (single y multi-mes)
# =========================
def _month_bounds(y: int, m: int) -> Tuple[datetime.date, datetime.date]:
    first = datetime.date(y, m, 1)
    last = datetime.date(y, m, monthrange(y, m)[1])
    return first, last


def _from_token(token: str, today: datetime.date) -> dict:
    t = (token or "").strip().upper()
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


def _parse_meses_env(raw: str, today: datetime.date) -> List[dict]:
    """
    Acepta: ACTUAL | ANTERIOR | SIGUIENTE | YYYY-MM
    También múltiples separados por coma: "ACTUAL,ANTERIOR"
    """
    tokens = [t.strip() for t in (raw or "").split(",") if t.strip()]
    if not tokens:
        tokens = ["ACTUAL"]

    contexts: List[dict] = []
    for tok in tokens:
        ctx = _from_token(tok, today)
        ctx["TOKEN"] = tok.strip().upper()
        contexts.append(ctx)
    return contexts


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


def build_run_email_body(config: dict, start_dt: datetime.datetime, end_dt: datetime.datetime, exit_code: int, resultados: List[Dict[str, str]]) -> str:
    ok = [r for r in resultados if r.get("status") == "OK"]
    fail = [r for r in resultados if r.get("status") != "OK"]
    meses = sorted({r.get("month_label", "") for r in resultados if r.get("month_label", "")})
    lines = [
        "RPA Tele Urgencia",
        "",
        f"Estado: {'OK' if exit_code == 0 else 'FAIL'}",
        f"Exit code: {exit_code}",
        f"Inicio: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Fin: {end_dt.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Duracion(s): {(end_dt - start_dt).total_seconds():.1f}",
        f"Meses: {meses}",
        f"Eventos: {len(resultados)}",
        f"OK: {len(ok)}",
        f"FAIL: {len(fail)}",
        "",
        "Este correo fue generado automaticamente por el RPA.",
    ]
    if fail:
        lines.append("")
        lines.append("Fallas:")
        for r in fail[:30]:
            lines.append(f"- {r.get('centro','?')} | {r.get('motivo','DESCONOCIDO')}")
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
# Formulario TELE_URGENCIA
# =========================
def _trigger_change(driver, element):
    driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles:true}));", element)


def open_form_for_center(logger, driver, config: dict, user: str, pwd: str, centro: str) -> None:
    wait = WebDriverWait(driver, 25)
    driver.get(config["URL_HOME"])

    # login
    switch_to_deep_cuerpo(driver, wait, max_depth=6)
    wait.until(EC.presence_of_element_located((By.NAME, "USER"))).clear()
    driver.find_element(By.NAME, "USER").send_keys(user)
    driver.find_element(By.NAME, "PASS").clear()
    driver.find_element(By.NAME, "PASS").send_keys(pwd)
    driver.find_element(By.NAME, "Submit").click()

    if STOP_EVENT.is_set():
        raise RuntimeError("CANCELADO")

    ok = wait_select_center_post_login(driver, centro, timeout=30)
    if config["REQUIRE_CENTER"] and not ok:
        raise RuntimeError("NO_SELECCIONO_CENTRO")

    # Delay tras seleccionar centro
    if config["DELAY_AFTER_SELECT_CENTER"] > 0:
        time.sleep(config["DELAY_AFTER_SELECT_CENTER"])

    # ingresar post-centro
    try:
        driver.find_element(By.NAME, "Submit").click()
    except Exception:
        driver.find_element(By.XPATH, "//input[contains(translate(@value,'INGRESAR','ingresar'),'ingresar')]").click()

    # Delay tras submit del centro
    if config["DELAY_AFTER_SUBMIT_CENTER"] > 0:
        time.sleep(config["DELAY_AFTER_SUBMIT_CENTER"])

    if STOP_EVENT.is_set():
        raise RuntimeError("CANCELADO")

    # Delay antes de abrir formulario
    if config["DELAY_BEFORE_OPEN_FORM"] > 0:
        time.sleep(config["DELAY_BEFORE_OPEN_FORM"])

    driver.switch_to.default_content()
    driver.get(config["FRM_MASIVAS"])
    WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.ID, "boton")))


def fill_form(driver, config: dict, month_ctx: dict) -> None:
    wait = WebDriverWait(driver, 25)

    # Mostrar por (tipo): PROFESIONAL = 1
    el_tipo = wait.until(EC.presence_of_element_located((By.ID, "tipo")))
    Select(el_tipo).select_by_value(config["MOSTRAR_POR"])
    _trigger_change(driver, el_tipo)

    # Tópico: TODOS = 00
    el_top = wait.until(EC.presence_of_element_located((By.ID, "topico")))
    Select(el_top).select_by_value(config["TOPICO"])
    _trigger_change(driver, el_top)

    # Fechas
    fi = wait.until(EC.presence_of_element_located((By.ID, "fe_ini")))
    ff = wait.until(EC.presence_of_element_located((By.ID, "fechaFin")))
    fi.clear()
    fi.send_keys(month_ctx["MONTH_FIRST_DMY"])
    ff.clear()
    ff.send_keys(month_ctx["MONTH_LAST_DMY"])

    # Formato archivo
    el_fmt = wait.until(EC.presence_of_element_located((By.ID, "formatoArchivo")))
    Select(el_fmt).select_by_value(config["FORMATO_ARCHIVO"])
    _trigger_change(driver, el_fmt)


def click_imprimir(driver) -> None:
    WebDriverWait(driver, 25).until(EC.element_to_be_clickable((By.ID, "boton"))).click()


# =========================
# Validación nombre archivo
# =========================
def validate_filename(centro: str, month_ctx: dict, filename: str, expected_suffix: str) -> Tuple[bool, str]:
    if not filename or not filename.lower().endswith(".txt"):
        return False, "NOMBRE_INVALIDO"

    if not filename.lower().endswith(expected_suffix.lower()):
        return False, "SUFIJO_MISMATCH"

    prefix = f"{centro}_{month_ctx['MONTH_FIRST_YMD']}_{month_ctx['MONTH_LAST_YMD']}_"
    if not filename.startswith(prefix):
        return False, "PREFIJO_TAG_MISMATCH"

    return True, ""


# =========================
# Descarga por centro (secuencial + retry)
# =========================
def descargar_centro(logger, config: dict, user_label: str, user: str, pwd: str, centro: str, month_ctx: dict) -> Dict[str, str]:
    primary = config["DOWNLOAD_PRIMARY"]
    mirrors = config["DOWNLOAD_MIRRORS"]
    expected_suffix = config["FILE_SUFFIX"]
    prefix = f"{centro}_{month_ctx['MONTH_FIRST_YMD']}_{month_ctx['MONTH_LAST_YMD']}_"

    res = {
        "centro": centro,
        "status": "FAIL",
        "motivo": "DESCONOCIDO",
        "usuario": user_label,
        "archivo": "",
        "attempt": "0",
        "seconds": "0",
        "dir": primary,
        "mes": month_ctx["LABEL"],
        "tag": month_ctx["MONTH_TAG"],
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
        try:
            # Limpieza previa (en primaria y mirrors)
            if config["CLEAN_BEFORE"]:
                clean_existing_finals(logger, primary, prefix, expected_suffix)
                for d in mirrors:
                    clean_existing_finals(logger, d, prefix, expected_suffix)

            remove_partial_with_prefix(logger, primary, prefix, unconfirmed_age_min=10)

            options, profile_dir = build_chrome_options(
                primary,
                config["HEADLESS"],
                config["CHROME_PROFILE_BASE_DIR"],
                worker_id=f"{centro}-{user_label}-a{attempt}",
            )
            logger.info(f"TMP_PROFILE_CREATE | {profile_dir}")
            driver = webdriver.Chrome(
                options=options,
                service=build_chrome_service()
            )

            logger.info(f"RUN | centro={centro} | user={user_label} | attempt={attempt} | dir={primary}")

            open_form_for_center(logger, driver, config, user, pwd, centro)
            fill_form(driver, config, month_ctx)
            click_imprimir(driver)

            archivo = esperar_descarga_por_prefijo(
                download_dir=primary,
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
                continue

            ok_name, reason = validate_filename(centro, month_ctx, archivo, expected_suffix)
            if not ok_name:
                res["motivo"] = reason
                res["attempt"] = str(attempt)
                res["seconds"] = f"{time.time() - t0:.1f}"
                continue

            fullpath = os.path.join(primary, archivo)
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

            # Replica a mirrors
            if mirrors:
                replicar_a_espejos(logger, fullpath, mirrors, archivo)

            res["status"] = "OK"
            res["motivo"] = ""
            res["archivo"] = archivo
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

            for _ in range(config["BETWEEN_DOWNLOADS_DELAY"]):
                if STOP_EVENT.is_set():
                    break
                time.sleep(1)

    return res


# =========================
# Export CSV (mini resumen)
# =========================
def export_summary_csv(run_dir: str, rows: List[Dict[str, str]], logger) -> str:
    import csv
    csv_path = os.path.join(run_dir, "summary.csv")
    fields = ["mes", "tag", "centro", "status", "motivo", "usuario", "archivo", "attempt", "seconds", "dir"]
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in fields})
        logger.info(f"ARTIFACT | summary.csv generado en {csv_path}")
    except Exception as e:
        logger.info(f"ARTIFACT_ERR | {type(e).__name__}:{e}")
        return ""
    return csv_path


# =========================
# Main (multi-mes)
# =========================
def main():
    config = load_config()
    logger, run_dir, logfile = setup_run_logger(config["LOGS_DIR"], config["RUN_NAME"])

    logger.info("CONFIG_OK | .env cargado")
    cleanup_old_runs(logger, config["LOGS_DIR"], config["LOG_RETENTION_DAYS"])
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

    # multi-mes
    try:
        month_ctxs = _parse_meses_env(config["MES_A_PROCESAR"], datetime.date.today())
    except Exception as e:
        logger.info(f"❌ MES_A_PROCESAR inválido: {e}")
        sys.exit(1)

    # tab (si viene con comas, usamos la primera para este RPA)
    tab = (config["GSHEET_TAB"] or "").split(",")[0].strip()

    overall_fail = False
    all_rows: List[Dict[str, str]] = []

    start_dt_global = datetime.datetime.now()

    for month_ctx in month_ctxs:
        if STOP_EVENT.is_set():
            break

        month_name = _month_header_from_ctx(month_ctx) or month_ctx.get("LABEL", "MES")
        logger.info(
            f"MONTH | {month_ctx['LABEL']} | {month_ctx['MONTH_FIRST_DMY']} -> {month_ctx['MONTH_LAST_DMY']} | "
            f"TAG={month_ctx['MONTH_TAG']} | FILE_SUFFIX={config['FILE_SUFFIX']}"
        )

        # Centros desde Google Sheets (checks por mes) con macroregion
        centros_meta = get_centros_from_gsheet(
            creds_json=config["CREDS_JSON"],
            gsheet_url=config["GSHEET_URL"],
            gsheet_tab=tab,
            month_ctx=month_ctx,
            logger=logger,
            config=config
        )

        # no hay checks -> continuar siguiente mes
        if not centros_meta:
            logger.info(f"GSHEET | No hay IPRESS marcadas para el mes {month_name}. Fin sin descargas.")
            continue

        # filtros opcionales
        if config["CENTERS_FILTER"]:
            allowed = set(config["CENTERS_FILTER"])
            centros_meta = [x for x in centros_meta if x["centro"] in allowed]

        # dedupe adicional (por si llega algo raro)
        dedup: List[Dict[str, str]] = []
        seen = set()
        for item in centros_meta:
            c = item["centro"]
            canon = c
            if c.isdigit():
                try:
                    canon = str(int(c))
                except Exception:
                    canon = c
            if canon in seen:
                continue
            seen.add(canon)
            dedup.append(item)
        centros_meta = dedup

        if config["MAX_CENTERS"] and config["MAX_CENTERS"] > 0:
            centros_meta = centros_meta[: config["MAX_CENTERS"]]

        centros = [x["centro"] for x in centros_meta]
        logger.info(f"INPUT | Centros considerados (checks) = {len(centros)}")

        # Proceso por usuarios maestros asignados a macroregion.
        centros_ok: List[str] = []
        centros_fail: List[str] = []
        resultados_mes: List[Dict[str, str]] = []

        sin_macro_centros = [x["centro"] for x in centros_meta if x.get("macro") not in VALID_MACROS]
        if sin_macro_centros:
            logger.info(f"SIN_MACRO_QUEUE | total={len(sin_macro_centros)} | centros={sin_macro_centros}")

        for macro in VALID_MACROS:
            if STOP_EVENT.is_set():
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
            logger.info(f"MACRO_START | {macro} | user={user} | total={len(centros_macro)}")

            ok_user = 0
            fail_user = 0

            for centro in centros_macro:
                if STOP_EVENT.is_set():
                    break

                r = descargar_centro(logger, config, user_label, user, pwd, centro, month_ctx)
                r["month_label"] = month_ctx.get("LABEL", "")
                r["month_name_es"] = month_ctx.get("MONTH_NAME_ES", "")
                r["month_tag"] = month_ctx.get("MONTH_TAG", "")
                resultados_mes.append(r)
                all_rows.append(r)

                if r["status"] == "OK":
                    centros_ok.append(centro)
                    ok_user += 1
                    logger.info(f"OK | {centro} | {user_label} | {r['archivo']} | {r['seconds']}s")
                else:
                    fail_user += 1
                    logger.info(f"FAIL | {centro} | {user_label} | {r['motivo']} | {r['seconds']}s")

            logger.info(f"MACRO_END | {macro} | OK:{ok_user} | FAIL:{fail_user}")

        centros_fail = [c for c in centros if c not in set(centros_ok)]
        if centros_fail:
            overall_fail = True

        # Limpieza de parciales huérfanos
        purge_old_partials(logger, config["DOWNLOAD_PRIMARY"], max_age_minutes=config["PURGE_PARTIALS_AGE_MIN"])
        for d in config["DOWNLOAD_MIRRORS"]:
            purge_old_partials(logger, d, max_age_minutes=config["PURGE_PARTIALS_AGE_MIN"])
        kill_chromedrivers()
        removed_profiles = cleanup_old_chrome_profiles(
            config["CHROME_PROFILE_BASE_DIR"],
            config["CHROME_PROFILE_MAX_AGE_HOURS"],
            logger,
        )
        if removed_profiles:
            logger.info(f"TMP_PROFILE_CLEANUP_SUMMARY | month_removed={removed_profiles}")

        # Resumen del mes
        logger.info("===== RESUMEN FINAL =====")
        # (por corrida global en el mismo run_dir, pero resumen por mes)
        end_dt = datetime.datetime.now()
        dur = (end_dt - start_dt_global).total_seconds()

        logger.info(f"Fecha inicio : {start_dt_global.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Fecha fin    : {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duración(s)  : {dur:.1f}")
        logger.info(f"Mes          : {month_ctx['LABEL']} | {month_name} | TAG={month_ctx['MONTH_TAG']}")
        logger.info(f"Centros considerados (checks): {len(centros)}")
        logger.info(f"TOTAL_OK     : {len(set(centros_ok))}")
        logger.info(f"TOTAL_FAIL   : {len(set(centros_fail))}")
        if centros_fail:
            logger.info(f"FAIL_CENTROS : {sorted(set(centros_fail))}")

        # detalle de motivos (solo los FAIL finales de este mes)
        fail_events = [r for r in resultados_mes if r.get("status") != "OK" and r.get("centro") in set(centros_fail)]
        if fail_events:
            by_reason: Dict[str, List[str]] = {}
            for r in fail_events:
                by_reason.setdefault(r.get("motivo", "DESCONOCIDO"), []).append(r.get("centro", "?"))
            for motivo, items in by_reason.items():
                items_u = sorted(set(items))
                logger.info(f"FAIL_FINAL_DETAIL | {motivo} -> {items_u}")

    # Export CSV (toda la corrida)
    removed_profiles = cleanup_old_chrome_profiles(
        config["CHROME_PROFILE_BASE_DIR"],
        config["CHROME_PROFILE_MAX_AGE_HOURS"],
        logger,
    )
    if removed_profiles:
        logger.info(f"TMP_PROFILE_CLEANUP_SUMMARY | end_removed={removed_profiles}")
    csv_path = export_summary_csv(run_dir, all_rows, logger)

    exit_code = 130 if STOP_EVENT.is_set() else (2 if overall_fail else 0)
    end_dt_global = datetime.datetime.now()
    subject_status = "OK" if exit_code == 0 else "FAIL"
    send_run_email(
        logger,
        config,
        f"[{subject_status}] RPA Tele Urgencia | exit_code={exit_code}",
        build_run_email_body(config, start_dt_global, end_dt_global, exit_code, all_rows),
        csv_path,
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
