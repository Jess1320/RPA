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
from typing import List, Dict, Tuple, Optional

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


def kill_chromedrivers(logger=None):
    if platform.system() == "Windows":
        try:
            import subprocess
            subprocess.run(
                ["taskkill", "/F", "/IM", "chromedriver.exe", "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if logger:
                logger.info("CLEANUP | taskkill chromedriver.exe ejecutado")
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


def _env_bool(name: str, default: str = "false") -> bool:
    return (os.getenv(name, default) or default).strip().lower() in ("1", "true", "yes", "y", "si", "sí")


def _split_recipients(raw: str) -> List[str]:
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


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
# Utils
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

def prune_logs(logger, logs_dir: str, retention_days: int) -> None:
    """Elimina carpetas RUN_* viejas."""
    if retention_days <= 0:
        return
    try:
        cutoff = time.time() - (retention_days * 86400)
        base = Path(logs_dir)
        if not base.exists():
            return

        deleted = 0
        for p in base.iterdir():
            if p.is_dir() and p.name.startswith("RUN_"):
                try:
                    mtime = p.stat().st_mtime
                    if mtime < cutoff:
                        shutil.rmtree(p, ignore_errors=True)
                        deleted += 1
                except Exception:
                    pass
        if deleted:
            logger.info(f"LOGS | Retención aplicada | deleted_runs={deleted} | days={retention_days}")
    except Exception as e:
        logger.info(f"LOGS | Retención error | {type(e).__name__}:{e}")

def wlog(logger, config: dict, tag: str, msg: str) -> None:
    """Logger con modo COMPACT/VERBOSE."""
    mode = (config.get("LOG_MODE") or "COMPACT").strip().upper()
    if mode == "COMPACT":
        # Suprime ruido (deja lo esencial)
        noisy = {
            "DELAY", "STEP", "CLEAN_DELETE", "PRETRY_CLEAN", "PRETRY_CLEAN_UNCONF",
            "PURGE_PARTIAL", "REPLICA_OK"
        }
        if tag in noisy:
            return
    logger.info(f"{tag} | {msg}")


# =========================
# Archivos / Descargas
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

def remove_partial_with_prefix(logger, config, download_dir: str, prefix: str, unconfirmed_age_min: int = 10) -> int:
    removed = 0
    now = time.time()

    for f in files_with_prefix(download_dir, prefix):
        low = f.lower()
        if low.endswith((".crdownload", ".tmp", ".part")) or " (1)." in low or " (2)." in low or " (3)." in low:
            try:
                os.remove(os.path.join(download_dir, f))
                removed += 1
                wlog(logger, config, "PRETRY_CLEAN", f"{download_dir} | {f}")
            except Exception as e:
                wlog(logger, config, "PRETRY_CLEAN_ERR", f"{download_dir} | {f} | {type(e).__name__}:{e}")

    for f in listar_archivos(download_dir):
        low = f.lower()
        if low.endswith(".crdownload") and ("unconfirmed" in low or "sin confirmar" in low):
            p = os.path.join(download_dir, f)
            try:
                if now - os.path.getmtime(p) > unconfirmed_age_min * 60:
                    os.remove(p)
                    removed += 1
                    wlog(logger, config, "PRETRY_CLEAN_UNCONF", f"{download_dir} | {f}")
            except Exception:
                pass

    return removed

def purge_old_partials(logger, config, download_dir: str, max_age_minutes: int = 30) -> None:
    now = time.time()
    for f in listar_archivos(download_dir):
        low = f.lower()
        if low.endswith((".crdownload", ".tmp", ".part")):
            p = os.path.join(download_dir, f)
            try:
                if now - os.path.getmtime(p) > max_age_minutes * 60:
                    os.remove(p)
                    wlog(logger, config, "PURGE_PARTIAL", f"{download_dir} | {f}")
            except Exception:
                pass

def clean_existing_finals(logger, config, download_dir: str, prefix: str, expected_suffix: str) -> int:
    deleted = 0
    exp = expected_suffix.lower()

    for f in listar_archivos(download_dir):
        low = f.lower()
        if f.startswith(prefix) and low.endswith(".txt") and low.endswith(exp):
            try:
                os.remove(os.path.join(download_dir, f))
                deleted += 1
                wlog(logger, config, "CLEAN_DELETE", f"{download_dir} | {f}")
            except Exception as e:
                wlog(logger, config, "CLEAN_ERR", f"{download_dir} | {f} | {type(e).__name__}:{e}")

    for f in listar_archivos(download_dir):
        low = f.lower()
        if f.startswith(prefix) and low.endswith(".txt") and (" (1)." in low or " (2)." in low or " (3)." in low):
            try:
                os.remove(os.path.join(download_dir, f))
                deleted += 1
                wlog(logger, config, "CLEAN_DUP_DELETE", f"{download_dir} | {f}")
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


# =========================
# Config desde .env
# =========================
def parse_download_dirs(raw: str) -> List[str]:
    dirs = [d.strip() for d in (raw or "").split(",") if d.strip()]
    return dirs

def load_config() -> dict:
    load_rpa_env_files()

    url_home = os.getenv("URL_HOME")
    frm_masivas = os.getenv("FRM_MASIVAS")

    # Legacy: se mantiene solo para transicion si aun no existe .env_usuarios.
    usuarios: List[Tuple[int, str, str]] = []
    for i in range(1, 51):
        u = os.getenv(f"USER_{i}")
        p = os.getenv(f"PASSWORD_{i}")
        if u and p:
            usuarios.append((i, u, p))

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
    gsheet_tab = os.getenv("GSHEET_TAB", "Centros")
    creds_json = os.getenv("CREDS_JSON")

    # download dirs (principal + espejos)
    download_dirs_raw = os.getenv("DOWNLOAD_DIRS", "")
    download_dirs = parse_download_dirs(download_dirs_raw)
    download_dir_legacy = os.getenv("DOWNLOAD_DIR", "").strip()
    if not download_dirs and download_dir_legacy:
        download_dirs = [download_dir_legacy]

    headless = os.getenv("HEADLESS", "true").lower() == "true"
    chrome_profile_base_dir = get_chrome_profile_base_dir()
    chrome_profile_max_age_hours = int(os.getenv("CHROME_PROFILE_MAX_AGE_HOURS", "12"))

    # logs
    logs_dir = os.getenv("LOGS_DIR", "logs").strip()
    run_name = os.getenv("RUN_NAME", "TELE_TRIAJE").strip()
    log_mode = os.getenv("LOG_MODE", "COMPACT").strip().upper()
    log_retention_days = int(os.getenv("LOG_RETENTION_DAYS", "7"))

    # correo
    mail_enabled = _env_bool("MAIL_ENABLED", "false")
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587") or "587")
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user).strip()
    smtp_to = _split_recipients(os.getenv("SMTP_TO", ""))
    smtp_cc = _split_recipients(os.getenv("SMTP_CC", ""))

    # formulario/mes
    mes_a_procesar = os.getenv("MES_A_PROCESAR", "ACTUAL").strip()
    formato_archivo = os.getenv("FORMATO_ARCHIVO", "xls").strip()  # para TeleTriaje: xls = TXT para XLS
    file_suffix = os.getenv("FILE_SUFFIX", "PacAtenTriaje.txt").strip()  # EXACTO

    # motor
    download_timeout = int(os.getenv("DOWNLOAD_TIMEOUT", "1500"))
    stable_secs = int(os.getenv("STABLE_SECS", "3"))
    poll_interval = int(os.getenv("POLL_INTERVAL", "2"))
    retry_per_center = int(os.getenv("RETRY_PER_CENTER", "1"))
    between_delay = int(os.getenv("BETWEEN_DOWNLOADS_DELAY", "2"))
    clean_before = os.getenv("CLEAN_BEFORE", "true").lower() == "true"
    purge_age_min = int(os.getenv("PURGE_PARTIALS_AGE_MIN", "30"))
    require_center = os.getenv("REQUIRE_CENTER", "true").lower() == "true"

    # filtros opcionales
    max_centers = int(os.getenv("MAX_CENTERS", "0"))
    centers_filter_raw = os.getenv("CENTERS_FILTER", "").strip()
    centers_filter = [c.strip() for c in centers_filter_raw.split(",") if c.strip()] if centers_filter_raw else []

    # delays (por si el portal está “lento”)
    delay_after_select_center = int(os.getenv("DELAY_AFTER_SELECT_CENTER", "1"))
    delay_after_submit_center = int(os.getenv("DELAY_AFTER_SUBMIT_CENTER", "1"))
    delay_before_open_form = int(os.getenv("DELAY_BEFORE_OPEN_FORM", "1"))

    faltan = []
    for k, v in [
        ("URL_HOME", url_home),
        ("FRM_MASIVAS", frm_masivas),
        ("GSHEET_URL", gsheet_url),
        ("GSHEET_TAB", gsheet_tab),
        ("CREDS_JSON", creds_json),
        ("DOWNLOAD_DIRS/DOWNLOAD_DIR", ",".join(download_dirs) if download_dirs else ""),
    ]:
        if not v:
            faltan.append(k)
    if len(usuarios) == 0:
        if all(not u or not p for u, p in macro_users.values()):
            faltan.append("credenciales macro o al menos un par USER_n / PASSWORD_n")
    if not file_suffix:
        faltan.append("FILE_SUFFIX")

    configured_macros = {m: creds for m, creds in macro_users.items() if creds[0] and creds[1]}
    if configured_macros:
        for macro in VALID_MACROS:
            if macro not in configured_macros:
                faltan.append(f"credenciales macro {macro}")
    elif usuarios:
        uid, u, p = usuarios[0]
        macro_users = {default_macro: (u, p)}

    if faltan:
        print("❌ Faltan variables en .env:", faltan, flush=True)
        sys.exit(1)

    ensure_dir(logs_dir)
    for d in download_dirs:
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
        "DOWNLOAD_DIR_PRIMARY": download_dirs[0],
        "DOWNLOAD_DIR_MIRRORS": download_dirs[1:],

        "HEADLESS": headless,
        "CHROME_PROFILE_BASE_DIR": chrome_profile_base_dir,
        "CHROME_PROFILE_MAX_AGE_HOURS": chrome_profile_max_age_hours,

        "LOGS_DIR": logs_dir,
        "RUN_NAME": run_name,
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

        "MES_A_PROCESAR": mes_a_procesar,
        "FORMATO_ARCHIVO": formato_archivo,
        "FILE_SUFFIX": file_suffix,

        "DOWNLOAD_TIMEOUT": download_timeout,
        "STABLE_SECS": stable_secs,
        "POLL_INTERVAL": poll_interval,
        "RETRY_PER_CENTER": retry_per_center,
        "BETWEEN_DOWNLOADS_DELAY": between_delay,
        "CLEAN_BEFORE": clean_before,
        "PURGE_PARTIALS_AGE_MIN": purge_age_min,
        "REQUIRE_CENTER": require_center,

        "MAX_CENTERS": max_centers,
        "CENTERS_FILTER": centers_filter,

        "DELAY_AFTER_SELECT_CENTER": delay_after_select_center,
        "DELAY_AFTER_SUBMIT_CENTER": delay_after_submit_center,
        "DELAY_BEFORE_OPEN_FORM": delay_before_open_form,
    }


# =========================
# Google Sheets (checks por mes) - UNA pestaña
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

def _find_col(headers_norm: List[str], candidates_norm: List[str]) -> int:
    cand_set = set(candidates_norm)
    for i, h in enumerate(headers_norm):
        if h in cand_set:
            return i
    return -1

def get_centros_from_gsheet_checked(
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

    # Detectar si es tabla (tiene COD_IPRESS o meses) o formato simple (solo col 1)
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
            wlog(logger, config or {}, "GSHEET", f"formato simple detectado | centros={len(centros)} | macro_default={default_macro}")
        # dedupe
        seen = set()
        out = []
        for cod in centros:
            canon = str(int(cod)) if cod.isdigit() else cod
            if canon in seen:
                continue
            seen.add(canon)
            out.append({"centro": cod, "macro": default_macro})
        return out

    idx_cod = _find_col(headers_norm, [_norm_cell(x) for x in ["COD_IPRESS", "COD IPRESS", "CODIGO IPRESS", "CODIGO DE IPRESS"]])
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

    month_num = month_ctx.get("MONTH_NUM")
    month_header = MONTHS_ES.get(int(month_num)) if month_num else ""
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
        wlog(
            logger, config or {}, "GSHEET",
            f"tabla detectada | tab={gsheet_tab} | mes_col={month_header} | seleccionados={len(selected)} | dup={dup} | unchecked={unchecked} | empty={empty} | sin_macro={sin_macro} | macro_default={default_macro if idx_macro < 0 else ''}"
        )

    return selected


# =========================
# Mes
# =========================
def _month_bounds(y: int, m: int):
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
        "MONTH_NUM": m,
        "MONTH_NAME_ES": MONTHS_ES.get(m, ""),
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


def build_run_email_body(config: dict, start_dt: datetime.datetime, end_dt: datetime.datetime, exit_code: int, resultados: List[Dict[str, str]]) -> str:
    ok = [r for r in resultados if r.get("status") == "OK"]
    fail = [r for r in resultados if r.get("status") != "OK"]
    meses = sorted({r.get("month_label", "") for r in resultados if r.get("month_label", "")})
    lines = [
        "RPA Tele Triaje",
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
# Formulario TeleTriaje
# =========================
def find_date_inputs_teletriaje(driver):
    # según tu HTML:
    # Inicio: id="fe_ini" name="fechaInicio"
    # Fin:    id="fechaFin" name="fechaFin"
    def _find(cands):
        for by, sel in cands:
            try:
                return driver.find_element(by, sel)
            except Exception:
                continue
        return None

    fi = _find([(By.ID, "fe_ini"), (By.NAME, "fechaInicio"), (By.ID, "fechaInicio"), (By.NAME, "fe_ini")])
    ff = _find([(By.ID, "fechaFin"), (By.NAME, "fechaFin"), (By.ID, "fe_fin"), (By.NAME, "fe_fin")])

    if not fi or not ff:
        raise RuntimeError("No se pudieron ubicar inputs Fecha Inicio / Fecha Fin (TeleTriaje).")
    return fi, ff

def find_select_formato_el(driver):
    # según tu HTML: <select name="formatoArchivo" id="formatoArchivo">
    try:
        return driver.find_element(By.ID, "formatoArchivo")
    except Exception:
        pass
    try:
        return driver.find_element(By.NAME, "formatoArchivo")
    except Exception:
        pass

    # fallback por opciones típicas
    for el in driver.find_elements(By.TAG_NAME, "select"):
        try:
            s = Select(el)
            vals = set((o.get_attribute("value") or "").strip() for o in s.options)
            if "xls" in vals:
                return el
        except Exception:
            continue
    raise RuntimeError("No se encontró SELECT 'formatoArchivo'.")

def _trigger_change(driver, element):
    driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles:true}));", element)

def open_form_for_center(logger, config: dict, driver, centro: str, user: str, pwd: str) -> None:
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

    if config["DELAY_AFTER_SELECT_CENTER"] > 0:
        wlog(logger, config, "DELAY", f"after_select_center={config['DELAY_AFTER_SELECT_CENTER']}s")
        time.sleep(config["DELAY_AFTER_SELECT_CENTER"])

    # ingresar post-centro
    try:
        driver.find_element(By.NAME, "Submit").click()
    except Exception:
        driver.find_element(By.XPATH, "//input[contains(translate(@value,'INGRESAR','ingresar'),'ingresar')]").click()

    if config["DELAY_AFTER_SUBMIT_CENTER"] > 0:
        wlog(logger, config, "DELAY", f"after_submit_center={config['DELAY_AFTER_SUBMIT_CENTER']}s")
        time.sleep(config["DELAY_AFTER_SUBMIT_CENTER"])

    if STOP_EVENT.is_set():
        raise RuntimeError("CANCELADO")

    if config["DELAY_BEFORE_OPEN_FORM"] > 0:
        wlog(logger, config, "DELAY", f"before_open_form={config['DELAY_BEFORE_OPEN_FORM']}s")
        time.sleep(config["DELAY_BEFORE_OPEN_FORM"])

    driver.switch_to.default_content()
    driver.get(config["FRM_MASIVAS"])
    WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.ID, "boton")))

def fill_form_teletriaje(driver, config: dict, month_ctx: dict) -> None:
    wait = WebDriverWait(driver, 25)

    fi, ff = find_date_inputs_teletriaje(driver)
    fi.clear(); fi.send_keys(month_ctx["MONTH_FIRST_DMY"])
    ff.clear(); ff.send_keys(month_ctx["MONTH_LAST_DMY"])

    el_fmt = find_select_formato_el(driver)
    Select(el_fmt).select_by_value(config["FORMATO_ARCHIVO"])
    _trigger_change(driver, el_fmt)

    # asegurar que el botón existe (no clic acá)
    wait.until(EC.presence_of_element_located((By.ID, "boton")))

def click_imprimir(driver) -> None:
    WebDriverWait(driver, 25).until(EC.element_to_be_clickable((By.ID, "boton"))).click()


# =========================
# Validación nombre archivo
# =========================
def validate_filename(centro: str, month_ctx: dict, expected_suffix: str, filename: str) -> Tuple[bool, str]:
    if not filename or not filename.lower().endswith(".txt"):
        return False, "NOMBRE_INVALIDO"

    if not filename.lower().endswith(expected_suffix.lower()):
        return False, "SUFIJO_MISMATCH"

    prefix = f"{centro}_{month_ctx['MONTH_FIRST_YMD']}_{month_ctx['MONTH_LAST_YMD']}_"
    if not filename.startswith(prefix):
        return False, "PREFIJO_TAG_MISMATCH"

    return True, ""


# =========================
# Réplica a espejos
# =========================
def replicar_a_espejos(logger, config, src_fullpath: str, mirrors: List[str], filename: str) -> None:
    for mdir in mirrors:
        try:
            ensure_dir(mdir)
            dst = os.path.join(mdir, filename)
            shutil.copy2(src_fullpath, dst)
            wlog(logger, config, "REPLICA_OK", f"{mdir} | {filename}")
        except Exception as e:
            logger.info(f"REPLICA_ERR | {mdir} | {filename} | {type(e).__name__}:{e}")


# =========================
# Descarga por centro (secuencial) + reintentos
# =========================
def descargar_centro(logger, config: dict, centro: str, month_ctx: dict, user_label: str, user: str, pwd: str) -> Dict[str, str]:
    download_dir = config["DOWNLOAD_DIR_PRIMARY"]
    expected_suffix = config["FILE_SUFFIX"]
    prefix = f"{centro}_{month_ctx['MONTH_FIRST_YMD']}_{month_ctx['MONTH_LAST_YMD']}_"

    res = {
        "centro": centro,
        "status": "FAIL",
        "motivo": "DESCONOCIDO",
        "archivo": "",
        "attempt": "0",
        "seconds": "0",
        "user": user_label,
        "download_dir": download_dir,
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
            # limpieza previa (en principal y espejos)
            if config["CLEAN_BEFORE"]:
                clean_existing_finals(logger, config, download_dir, prefix, expected_suffix)
                for mdir in config["DOWNLOAD_DIR_MIRRORS"]:
                    clean_existing_finals(logger, config, mdir, prefix, expected_suffix)

            remove_partial_with_prefix(logger, config, download_dir, prefix, unconfirmed_age_min=10)

            options, profile_dir = build_chrome_options(
                download_dir,
                config["HEADLESS"],
                config["CHROME_PROFILE_BASE_DIR"],
                worker_id=f"{centro}-{user_label}-a{attempt}",
            )
            logger.info(f"TMP_PROFILE_CREATE | {profile_dir}")
            driver = webdriver.Chrome(
                options=options,
                service=build_chrome_service()
            )

            wlog(logger, config, "RUN", f"centro={centro} | user={user_label} | attempt={attempt} | dir={download_dir}")

            open_form_for_center(logger, config, driver, centro, user, pwd)
            fill_form_teletriaje(driver, config, month_ctx)
            click_imprimir(driver)

            archivo = esperar_descarga_por_prefijo(
                download_dir=download_dir,
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
                remove_partial_with_prefix(logger, config, download_dir, prefix, unconfirmed_age_min=10)
                continue

            ok_name, reason = validate_filename(centro, month_ctx, expected_suffix, archivo)
            if not ok_name:
                res["motivo"] = reason
                res["attempt"] = str(attempt)
                res["seconds"] = f"{time.time() - t0:.1f}"
                continue

            fullpath = os.path.join(download_dir, archivo)
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

            # réplica a espejos
            if config["DOWNLOAD_DIR_MIRRORS"]:
                replicar_a_espejos(logger, config, fullpath, config["DOWNLOAD_DIR_MIRRORS"], archivo)

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

            # delay entre centros/reintentos
            for _ in range(config["BETWEEN_DOWNLOADS_DELAY"]):
                if STOP_EVENT.is_set():
                    break
                time.sleep(1)

    return res


# =========================
# Main (multi-usuario con pendientes) + MULTI-MES
# =========================
def main():
    config = load_config()
    logger, run_dir, logfile = setup_run_logger(config["LOGS_DIR"], config["RUN_NAME"])

    prune_logs(logger, config["LOGS_DIR"], config["LOG_RETENTION_DAYS"])

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

    # --- Parse multi-mes ---
    def _parse_meses_env(raw: str, today: datetime.date) -> List[dict]:
        # Quita comentarios inline tipo: ACTUAL # comentario
        cleaned = (raw or "ACTUAL")
        cleaned = cleaned.split("#", 1)[0].strip()
        # Split por coma
        tokens = [t.strip() for t in cleaned.split(",") if t.strip()]
        if not tokens:
            tokens = ["ACTUAL"]
        return [_from_token(t, today) for t in tokens]

    try:
        month_ctxs = _parse_meses_env(config["MES_A_PROCESAR"], datetime.date.today())
    except Exception as e:
        logger.info(f"❌ MES_A_PROCESAR inválido: {e}")
        sys.exit(1)

    # Acumuladores globales (para artifact y exit code)
    resultados_all: List[Dict[str, str]] = []
    any_fail_final = False
    any_work_done = False

    # ====== LOOP POR MES ======
    for month_ctx in month_ctxs:
        if STOP_EVENT.is_set():
            break

        logger.info(
            f"MONTH | {month_ctx['LABEL']} | {month_ctx['MONTH_FIRST_DMY']} -> {month_ctx['MONTH_LAST_DMY']} | "
            f"TAG={month_ctx['MONTH_TAG']} | FILE_SUFFIX={config['FILE_SUFFIX']}"
        )

        # Centros (checks por mes) con macroregion
        centros_meta = get_centros_from_gsheet_checked(
            config["CREDS_JSON"],
            config["GSHEET_URL"],
            config["GSHEET_TAB"],
            month_ctx,
            logger=logger,
            config=config
        )

        if not centros_meta:
            # No aborta todo el run si otro mes sí tiene checks
            logger.info(
                f"GSHEET | No hay IPRESS marcadas para el mes {month_ctx.get('MONTH_NAME_ES','') or month_ctx.get('LABEL','')}. "
                f"Fin sin descargas para este mes."
            )
            continue

        any_work_done = True

        # filtros opcionales
        if config["CENTERS_FILTER"]:
            allowed = set(config["CENTERS_FILTER"])
            centros_meta = [x for x in centros_meta if x["centro"] in allowed]

        if config["MAX_CENTERS"] and config["MAX_CENTERS"] > 0:
            centros_meta = centros_meta[: config["MAX_CENTERS"]]

        centros = [x["centro"] for x in centros_meta]
        logger.info(f"INPUT | Centros considerados (checks) = {len(centros)}")

        # Ejecucion por usuarios maestros asignados a macroregion.
        ok_total_mes: List[str] = []
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

            ok_user: List[str] = []
            fail_user: List[str] = []

            for centro in centros_macro:
                if STOP_EVENT.is_set():
                    break

                r = descargar_centro(logger, config, centro, month_ctx, user_label, user, pwd)

                # Enriquecemos el registro para distinguir meses en el CSV final (sin tocar descargar_centro)
                r["month_label"] = month_ctx.get("LABEL", "")
                r["month_name_es"] = month_ctx.get("MONTH_NAME_ES", "")
                r["month_tag"] = month_ctx.get("MONTH_TAG", "")

                resultados_all.append(r)

                if r["status"] == "OK":
                    ok_user.append(centro)
                    ok_total_mes.append(centro)
                    logger.info(f"OK   | {centro} | {user_label} | {r['archivo']} | {r['seconds']}s")
                else:
                    fail_user.append(centro)
                    logger.info(f"FAIL | {centro} | {user_label} | {r['motivo']} | {r['seconds']}s")

            logger.info(f"MACRO_END | {macro} | OK:{len(ok_user)} | FAIL:{len(fail_user)}")

        # Consolidado final del MES (igual que antes, pero por mes)
        ok_set_mes = set(ok_total_mes)
        fail_final_mes = [c for c in centros if c not in ok_set_mes]

        logger.info(f"MONTH_SUMMARY | {month_ctx['LABEL']} | OK:{len(ok_set_mes)} | FAIL:{len(fail_final_mes)}")
        if fail_final_mes:
            any_fail_final = True
            logger.info(f"FAIL_CENTROS | {month_ctx['LABEL']} -> {fail_final_mes}")

        # (Opcional) detalle por motivos SOLO del mes (si hubo fails finales)
        if fail_final_mes:
            final_fail_set = set(fail_final_mes)
            fail_events_mes = [
                r for r in resultados_all
                if r.get("month_tag") == month_ctx.get("MONTH_TAG")
                and r.get("status") != "OK"
                and r.get("centro") in final_fail_set
            ]
            if fail_events_mes:
                by_reason_final: Dict[str, List[str]] = {}
                for r in fail_events_mes:
                    by_reason_final.setdefault(r.get("motivo", "DESCONOCIDO"), []).append(r.get("centro", "?"))
                for motivo, items in by_reason_final.items():
                    logger.info(f"FAIL_FINAL_DETAIL | {month_ctx['LABEL']} | {motivo} -> {sorted(set(items))}")

    # ====== Cleanup general ======
    for d in config["DOWNLOAD_DIRS"]:
        purge_old_partials(logger, config, d, max_age_minutes=config["PURGE_PARTIALS_AGE_MIN"])
    kill_chromedrivers(logger)
    removed_profiles = cleanup_old_chrome_profiles(
        config["CHROME_PROFILE_BASE_DIR"],
        config["CHROME_PROFILE_MAX_AGE_HOURS"],
        logger,
    )
    if removed_profiles:
        logger.info(f"TMP_PROFILE_CLEANUP_SUMMARY | end_removed={removed_profiles}")

    # ====== Resumen final global ======
    end_dt = datetime.datetime.now()
    dur = (end_dt - start_dt).total_seconds()

    logger.info("===== RESUMEN FINAL (RUN) =====")
    logger.info(f"Fecha inicio : {start_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Fecha fin    : {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Duración(s)  : {dur:.1f}")
    logger.info(f"Meses        : {[m.get('LABEL','') for m in month_ctxs]}")
    logger.info(f"Eventos      : {len(resultados_all)}")

    csv_path = ""
    # export mini-resumen csv (para auditoría)
    try:
        csv_path = os.path.join(run_dir, "summary.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("month_label,month_name_es,month_tag,centro,status,motivo,archivo,attempt,seconds,user,download_dir\n")
            for r in resultados_all:
                f.write(
                    f"{r.get('month_label','')},{r.get('month_name_es','')},{r.get('month_tag','')},"
                    f"{r.get('centro','')},{r.get('status','')},{r.get('motivo','')},"
                    f"{r.get('archivo','')},{r.get('attempt','')},{r.get('seconds','')},"
                    f"{r.get('user','')},{r.get('download_dir','')}\n"
                )
        logger.info(f"ARTIFACT | summary.csv generado en {csv_path}")
    except Exception as e:
        logger.info(f"ARTIFACT_ERR | summary.csv | {type(e).__name__}:{e}")

    if STOP_EVENT.is_set():
        exit_code = 130
    elif not any_work_done:
        exit_code = 0
    else:
        exit_code = 2 if any_fail_final else 0

    subject = f"[{'OK' if exit_code == 0 else 'FAIL'}] RPA Tele Triaje | exit_code={exit_code}"
    send_run_email(
        logger,
        config,
        subject,
        build_run_email_body(config, start_dt, end_dt, exit_code, resultados_all),
        csv_path,
    )

    if STOP_EVENT.is_set():
        sys.exit(130)

    # Si no hubo nada para descargar en ningún mes => exit 0
    if not any_work_done:
        sys.exit(0)

    # Si algún mes terminó con FAIL final => exit 2, sino 0
    sys.exit(2 if any_fail_final else 0)


if __name__ == "__main__":
    main()

