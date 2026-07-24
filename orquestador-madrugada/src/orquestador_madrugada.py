import ast
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from mailer import send_smtp_mail


VALID_JOB_CODES = (
    "MENSUAL",
    "TELE_TRIAJE",
    "TELE_URGENCIA",
    "MEDICO_NO_MEDICO",
    "TELE_PROAD",
    "TELE_PSICOPROFILAXIS",
    "TAD",
)


def parse_bool(value: str, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "y", "si", "sí")


def split_list(value: str) -> List[str]:
    return [x.strip() for x in re.split(r"[;,]", value or "") if x.strip()]


def split_int_list(value: str, default: List[int]) -> List[int]:
    items = []
    for raw in split_list(value):
        try:
            day = int(raw)
        except ValueError:
            continue
        if 1 <= day <= 31:
            items.append(day)
    return items or default


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def ts_now() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def human_dt(value: Optional[dt.datetime]) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else "-"


def duration_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {sec}s"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def normalize_macro_label(value: str) -> str:
    macro = re.sub(r"\s+", "_", (value or "").strip().upper())
    return f"MACRO_{macro}" if macro else ""


def mask_login(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def canon_center_code(value: str) -> str:
    text = str(value or "").strip()
    if text.isdigit():
        return str(int(text))
    return text


def short_path(path: str) -> str:
    return path or "-"


def add_months(value: dt.date, months: int) -> dt.date:
    year = value.year + ((value.month - 1 + months) // 12)
    month = ((value.month - 1 + months) % 12) + 1
    return dt.date(year, month, 1)


def month_label_for_token(token: str, run_date: dt.date) -> str:
    normalized = (token or "ACTUAL").strip().upper()
    if normalized == "ANTERIOR":
        target = add_months(run_date.replace(day=1), -1)
    elif normalized == "SIGUIENTE":
        target = add_months(run_date.replace(day=1), 1)
    elif normalized == "ACTUAL":
        target = run_date.replace(day=1)
    else:
        return normalized
    return target.strftime("%Y-%m")


def phase_label(phase: str) -> str:
    labels = {
        "CIERRE_MES_ANTERIOR": "Cierre mes anterior",
        "MES_ACTUAL": "Mes actual",
    }
    return labels.get(phase or "", phase or "-")


def result_display_name(result: "JobResult") -> str:
    if result.phase:
        return f"{result.config.name} ({phase_label(result.phase)})"
    return result.config.name


def result_period_label(result: "JobResult") -> str:
    run_date = (result.start_dt or dt.datetime.now()).date()
    period = month_label_for_token(result.mes_a_procesar, run_date)
    if result.mes_a_procesar and period != result.mes_a_procesar:
        return f"{period} ({result.mes_a_procesar})"
    return period or "-"


def safe_file_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", (value or "").strip())


@dataclass
class Failure:
    rpa: str
    centro: str = ""
    ipress: str = ""
    red: str = ""
    tipo: str = ""
    usuario: str = ""
    login: str = ""
    macro: str = ""
    motivo: str = ""
    fase: str = ""
    archivo: str = ""
    raw: str = ""


@dataclass
class JobConfig:
    code: str
    name: str
    workdir: str
    command: str
    logs_dir: str
    run_name: str
    parser: str
    enabled: bool = True


@dataclass
class JobResult:
    config: JobConfig
    status: str = "PENDING"
    exit_code: Optional[int] = None
    start_dt: Optional[dt.datetime] = None
    end_dt: Optional[dt.datetime] = None
    run_dir: str = ""
    run_log: str = ""
    summary_csv: str = ""
    total_input: Optional[int] = None
    total_ok: Optional[int] = None
    total_fail: Optional[int] = None
    failures: List[Failure] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    phase: str = ""
    mes_a_procesar: str = ""
    effective_run_name: str = ""

    @property
    def duration_seconds(self) -> float:
        if self.start_dt and self.end_dt:
            return (self.end_dt - self.start_dt).total_seconds()
        return 0.0


@dataclass
class JobExecution:
    config: JobConfig
    phase: str
    mes_a_procesar: str
    run_name: str
    close_month_period: str = ""


def build_job_config(code: str) -> JobConfig:
    prefix = code
    defaults = {
        "MENSUAL": {
            "name": "RPA Mensual",
            "workdir": "/home/cenate/rpa_cext_diario",
            "command": "/home/cenate/rpa_cext_diario/run_rpa_mensual.sh",
            "logs_dir": "/home/cenate/rpa_cext_diario/logs",
            "run_name": "CEXT_PROD_MENSUAL_MADRUGADA",
            "parser": "mensual",
        },
        "TELE_TRIAJE": {
            "name": "RPA Tele Triaje",
            "workdir": "/home/cenate/rpa_tele_triaje",
            "command": "scripts/run_rpa_tele_triaje.sh",
            "logs_dir": "/home/cenate/rpa_tele_triaje/logs",
            "run_name": "TELE_TRIAJE_MADRUGADA",
            "parser": "tele",
        },
        "TELE_URGENCIA": {
            "name": "RPA Tele Urgencia",
            "workdir": "/home/cenate/rpa_tele_urgencia",
            "command": "scripts/run_rpa_tele_urgencia.sh",
            "logs_dir": "/home/cenate/rpa_tele_urgencia/logs",
            "run_name": "TELE_URGENCIA_MADRUGADA",
            "parser": "tele",
        },
        "MEDICO_NO_MEDICO": {
            "name": "RPA Medico y No Medico",
            "workdir": "/home/cenate/rpa_medico_no_medico",
            "command": "scripts/run_rpa_medico_no_medico.sh",
            "logs_dir": "/home/cenate/rpa_medico_no_medico/logs",
            "run_name": "MEDICO_NO_MEDICO_MADRUGADA",
            "parser": "medico_no_medico",
        },
        "TELE_PROAD": {
            "name": "RPA Tele Proad",
            "workdir": "/home/cenate/rpa_tele_proad",
            "command": "scripts/run_rpa_tele_proad.sh",
            "logs_dir": "/home/cenate/rpa_tele_proad/logs",
            "run_name": "TELE_PROAD_MADRUGADA",
            "parser": "medico_no_medico",
        },
        "TELE_PSICOPROFILAXIS": {
            "name": "RPA Tele Psicoprofilaxis",
            "workdir": "/home/cenate/rpa_tele_psicoprofilaxis",
            "command": "scripts/run_rpa_tele_psicoprofilaxis.sh",
            "logs_dir": "/home/cenate/rpa_tele_psicoprofilaxis/logs",
            "run_name": "TELE_PSICOPROFILAXIS_MADRUGADA",
            "parser": "medico_no_medico",
        },
        "TAD": {
            "name": "RPA TAD",
            "workdir": "/home/cenate/rpa_tad",
            "command": "scripts/run_rpa_tad.sh",
            "logs_dir": "/home/cenate/rpa_tad/logs",
            "run_name": "TAD_MADRUGADA",
            "parser": "medico_no_medico",
        },
    }[code]

    return JobConfig(
        code=code,
        name=os.getenv(f"{prefix}_NAME", defaults["name"]),
        workdir=os.getenv(f"{prefix}_WORKDIR", defaults["workdir"]),
        command=os.getenv(f"{prefix}_COMMAND", defaults["command"]),
        logs_dir=os.getenv(f"{prefix}_LOGS_DIR", defaults["logs_dir"]),
        run_name=os.getenv(f"{prefix}_RUN_NAME", defaults["run_name"]),
        parser=os.getenv(f"{prefix}_PARSER", defaults["parser"]),
        enabled=parse_bool(os.getenv(f"{prefix}_ENABLED", "true"), default=True),
    )


def should_run_month_start_close(run_date: dt.date) -> bool:
    enabled = parse_bool(os.getenv("MONTH_START_CLOSE_ENABLED", "true"), default=True)
    if not enabled:
        return False
    days = split_int_list(os.getenv("MONTH_START_CLOSE_DAYS", "1"), [1])
    return run_date.day in days


def month_start_close_lock_enabled() -> bool:
    return parse_bool(os.getenv("MONTH_START_CLOSE_LOCK_ENABLED", "true"), default=True)


def month_start_close_force() -> bool:
    return parse_bool(os.getenv("MONTH_START_CLOSE_FORCE", "false"), default=False)


def month_start_close_lock_dir(project_dir: Path) -> Path:
    raw = os.getenv("MONTH_START_CLOSE_LOCK_DIR", "state/month_start_close")
    path = Path(raw)
    return path if path.is_absolute() else project_dir / path


def month_start_close_lock_path(project_dir: Path, period: str, job: JobConfig) -> Path:
    period_token = safe_file_token(period)
    job_token = safe_file_token(job.code)
    return month_start_close_lock_dir(project_dir) / period_token / f"{job_token}.json"


def is_month_start_close_job_locked(project_dir: Path, period: str, job: JobConfig) -> bool:
    if not month_start_close_lock_enabled() or month_start_close_force():
        return False
    return month_start_close_lock_path(project_dir, period, job).is_file()


def write_month_start_close_job_lock(project_dir: Path, period: str, result: JobResult, run_dir: str) -> Optional[Path]:
    if not month_start_close_lock_enabled():
        return None
    path = month_start_close_lock_path(project_dir, period, result.config)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "periodo": period,
        "rpa": result.config.name,
        "code": result.config.code,
        "status": result.status,
        "closed_at": human_dt(result.end_dt),
        "run_dir": result.run_dir,
        "orchestrator_run_dir": run_dir,
        "total_input": result.total_input,
        "total_ok": result.total_ok,
        "total_fail": result.total_fail,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_job_executions(
    jobs: List[JobConfig],
    run_date: dt.date,
    close_jobs: Optional[List[JobConfig]] = None,
) -> List[JobExecution]:
    executions: List[JobExecution] = []
    if should_run_month_start_close(run_date):
        previous_period = month_label_for_token("ANTERIOR", run_date)
        jobs_to_close = jobs if close_jobs is None else close_jobs
        for job in jobs_to_close:
            executions.append(
                JobExecution(
                    config=job,
                    phase="CIERRE_MES_ANTERIOR",
                    mes_a_procesar="ANTERIOR",
                    run_name=f"{job.run_name}_CIERRE_MES_ANTERIOR",
                    close_month_period=previous_period if job.code == "MENSUAL" else "",
                )
            )
        for job in jobs:
            executions.append(
                JobExecution(
                    config=job,
                    phase="MES_ACTUAL",
                    mes_a_procesar="ACTUAL",
                    run_name=job.run_name,
                )
            )
        return executions

    for job in jobs:
        executions.append(
            JobExecution(
                config=job,
                phase="MES_ACTUAL",
                mes_a_procesar="ACTUAL",
                run_name=job.run_name,
            )
        )
    return executions


def read_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    return Path(path).read_text(encoding="utf-8", errors="replace")


def find_run_dir(logs_dir: str, run_name: str, started_at: dt.datetime) -> str:
    base = Path(logs_dir)
    if not base.is_dir():
        return ""
    pattern = f"RUN_{run_name}_*"
    candidates = [p for p in base.glob(pattern) if p.is_dir()]
    if not candidates:
        return ""
    start_epoch = started_at.timestamp() - 10
    recent = [p for p in candidates if p.stat().st_mtime >= start_epoch]
    selected = recent or candidates
    selected.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(selected[0])


def extract_macro_users(log_text: str) -> Dict[str, str]:
    mapping = {}
    rx = re.compile(r"MACRO_START\s*\|\s*([^|]+?)\s*\|\s*user=([^|\s]+)")
    for macro, login in rx.findall(log_text or ""):
        mapping[normalize_macro_label(macro)] = mask_login(login)
    return mapping


def parse_int_list_line(log_text: str, key: str) -> tuple[Optional[int], List[str]]:
    rx = re.compile(rf"{re.escape(key)}\s*\|\s*(\d+)\s*\|\s*(\[.*?\])")
    matches = rx.findall(log_text or "")
    if not matches:
        return None, []
    count_raw, list_raw = matches[-1]
    try:
        items = ast.literal_eval(list_raw)
        if not isinstance(items, list):
            items = []
        items = [str(x) for x in items]
    except Exception:
        items = []
    return int(count_raw), items


def parse_key_value_detail(line: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for part in line.split("|")[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def parse_fail_center_details(log_text: str) -> Dict[str, Dict[str, str]]:
    details: Dict[str, Dict[str, str]] = {}
    for line in (log_text or "").splitlines():
        if "FAIL_CENTER_DETAIL |" not in line:
            continue
        data = parse_key_value_detail(line)
        centro = data.get("centro", "").strip()
        if centro:
            details[centro] = data
            details[canon_center_code(centro)] = data
    return details


def parse_summary_csv(result: JobResult, login_by_user: Dict[str, str]) -> None:
    path = result.summary_csv
    if not path or not os.path.exists(path):
        return
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    result.total_input = len(rows)
    result.total_ok = len([r for r in rows if (r.get("status") or "").upper() == "OK"])
    result.total_fail = len(rows) - result.total_ok
    for row in rows:
        if (row.get("status") or "").upper() == "OK":
            continue
        usuario = row.get("user") or row.get("usuario") or ""
        result.failures.append(
            Failure(
                rpa=result.config.name,
                centro=row.get("centro", ""),
                tipo=row.get("tipo", ""),
                usuario=usuario,
                login=login_by_user.get(usuario, ""),
                motivo=row.get("motivo", "") or "SIN_MOTIVO",
                archivo=row.get("archivo", ""),
                raw="summary.csv",
            )
        )


def parse_tele_result(result: JobResult) -> None:
    log_text = read_text(result.run_log)
    login_by_user = extract_macro_users(log_text)
    csv_path = os.path.join(result.run_dir, "summary.csv") if result.run_dir else ""
    if os.path.exists(csv_path):
        result.summary_csv = csv_path
        parse_summary_csv(result, login_by_user)
        return

    fail_rx = re.compile(r"^FAIL\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|", re.MULTILINE)
    ok_rx = re.compile(r"\bOK\s*\|\s*([^|]+)\|\s*([^|]+)\|")
    failures = []
    for centro, usuario, motivo in fail_rx.findall(log_text):
        usuario = usuario.strip()
        failures.append(
            Failure(
                rpa=result.config.name,
                centro=centro.strip(),
                usuario=usuario,
                login=login_by_user.get(usuario, ""),
                motivo=motivo.strip() or "SIN_MOTIVO",
                raw="run.log",
            )
        )
    result.failures = failures
    result.total_fail = len({f.centro for f in failures})
    result.total_ok = len(ok_rx.findall(log_text))
    if result.total_input is None and result.total_ok is not None and result.total_fail is not None:
        result.total_input = result.total_ok + result.total_fail


def parse_medico_result(result: JobResult) -> None:
    log_text = read_text(result.run_log)
    login_by_user = extract_macro_users(log_text)

    ok_match = re.findall(r"Centros OK\s*:\s*(\d+)/(\d+)", log_text)
    fail_match = re.findall(r"Centros FAIL\s*:\s*(\d+)/(\d+)", log_text)
    if ok_match:
        result.total_ok = int(ok_match[-1][0])
        result.total_input = int(ok_match[-1][1])
    if fail_match:
        result.total_fail = int(fail_match[-1][0])
        result.total_input = int(fail_match[-1][1])

    fail_rx = re.compile(r"^FAIL\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|", re.MULTILINE)
    for centro, tipo, usuario, motivo in fail_rx.findall(log_text):
        usuario = usuario.strip()
        result.failures.append(
            Failure(
                rpa=result.config.name,
                centro=centro.strip(),
                tipo=tipo.strip(),
                usuario=usuario,
                login=login_by_user.get(usuario, ""),
                motivo=motivo.strip() or "SIN_MOTIVO",
                raw="run.log",
            )
        )


def parse_mensual_result(result: JobResult) -> None:
    log_text = read_text(result.run_log)
    summary_text = read_text(os.path.join(result.run_dir, "summary.log")) if result.run_dir else ""
    combined = "\n".join([log_text, summary_text])
    login_by_user = extract_macro_users(combined)
    login_to_label = {login: label for label, login in login_by_user.items()}

    total_ok, ok_centers = parse_int_list_line(combined, "TOTAL_OK")
    total_fail, fail_centers = parse_int_list_line(combined, "TOTAL_FAIL")
    fail_details = parse_fail_center_details(combined)
    total_input = None
    input_match = re.findall(r"TOTAL_INPUT\s*\|\s*(\d+)", combined)
    if input_match:
        total_input = int(input_match[-1])
    elif total_ok is not None and total_fail is not None:
        total_input = total_ok + total_fail

    result.total_input = total_input
    result.total_ok = total_ok if total_ok is not None else len(ok_centers)
    result.total_fail = total_fail if total_fail is not None else len(fail_centers)

    fail_by_center: Dict[str, Failure] = {}
    fail_rx = re.compile(r"^FAIL\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|\n]+)", re.MULTILINE)
    for login, centro, motivo in fail_rx.findall(log_text):
        centro = centro.strip()
        if fail_centers and centro not in set(fail_centers):
            continue
        masked = mask_login(login.strip())
        detail = fail_details.get(centro, {}) or fail_details.get(canon_center_code(centro), {})
        fail_by_center[centro] = Failure(
            rpa=result.config.name,
            centro=centro,
            ipress=detail.get("ipress", ""),
            red=detail.get("red", ""),
            macro=detail.get("macro", ""),
            usuario=detail.get("usuario", "") or login_to_label.get(masked, ""),
            login=masked,
            motivo=detail.get("motivo", "") or motivo.strip() or "SIN_MOTIVO",
            raw="run.log",
        )

    for centro in fail_centers:
        detail = fail_details.get(centro, {}) or fail_details.get(canon_center_code(centro), {})
        fail_by_center.setdefault(
            centro,
            Failure(
                rpa=result.config.name,
                centro=centro,
                ipress=detail.get("ipress", ""),
                red=detail.get("red", ""),
                macro=detail.get("macro", ""),
                usuario=detail.get("usuario", ""),
                motivo=detail.get("motivo", "") or "NO_DETALLADO",
                raw="TOTAL_FAIL",
            ),
        )

    fail_class_rx = re.compile(r"FAIL_CLASS\s*\|\s*stage=([^|]+)\|\s*detail=([^\n]+)")
    for stage, detail in fail_class_rx.findall(combined):
        result.failures.append(
            Failure(
                rpa=result.config.name,
                motivo=detail.strip(),
                fase=stage.strip(),
                raw="FAIL_CLASS",
            )
        )

    result.failures.extend(fail_by_center.values())


def parse_job_result(result: JobResult) -> None:
    result.run_log = os.path.join(result.run_dir, "run.log") if result.run_dir else ""
    if result.config.parser == "mensual":
        parse_mensual_result(result)
    elif result.config.parser == "medico_no_medico":
        parse_medico_result(result)
    else:
        parse_tele_result(result)

    if result.exit_code not in (0, None) and not result.failures:
        result.failures.append(
            Failure(
                rpa=result.config.name,
                motivo=f"El proceso termino con exit_code={result.exit_code}, sin detalle de IPRESS en el parser.",
                raw="exit_code",
            )
        )

    has_failures = bool(result.failures) or (result.total_fail is not None and result.total_fail > 0)
    if result.exit_code == 0 and not has_failures:
        result.status = "OK"
    elif result.exit_code == 0 and has_failures:
        result.status = "OBSERVACION"
    else:
        result.status = "FALLA"


def run_job(execution: JobExecution, suppress_child_mail: bool) -> JobResult:
    config = execution.config
    result = JobResult(
        config=config,
        start_dt=dt.datetime.now(),
        phase=execution.phase,
        mes_a_procesar=execution.mes_a_procesar,
        effective_run_name=execution.run_name,
    )
    env = os.environ.copy()
    env["RUN_NAME"] = execution.run_name
    env["MES_A_PROCESAR"] = execution.mes_a_procesar
    env["PYTHONUNBUFFERED"] = "1"
    if execution.close_month_period:
        env["CLOSE_MONTH"] = "true"
        env["CLOSE_MONTH_PERIOD"] = execution.close_month_period
    if suppress_child_mail:
        env["MAIL_ENABLED"] = "false"

    try:
        completed = subprocess.run(
            ["/bin/bash", "-lc", config.command],
            cwd=config.workdir,
            env=env,
            timeout=None,
            check=False,
        )
        result.exit_code = completed.returncode
    except Exception as e:
        result.exit_code = 99
        result.notes.append(f"RUN_EXCEPTION | {type(e).__name__}: {e}")
    finally:
        result.end_dt = dt.datetime.now()

    result.run_dir = find_run_dir(config.logs_dir, execution.run_name, result.start_dt)
    parse_job_result(result)
    return result


def status_icon(status: str) -> str:
    if status == "OK":
        return "OK"
    if status == "OBSERVACION":
        return "OBS"
    return "FALLA"


def whatsapp_text(results: List[JobResult], run_date: dt.date) -> str:
    ok = [result_display_name(r).replace("RPA ", "") for r in results if r.status == "OK"]
    bad = [r for r in results if r.status != "OK"]
    date_txt = run_date.strftime("%d/%m/%Y")
    if not bad:
        ok_txt = ", ".join(ok) if ok else "sin RPAs ejecutados"
        return (
            f"Descargas de madrugada {date_txt} listas: "
            f"{ok_txt} OK."
        )
    ok_txt = ", ".join(ok) if ok else "sin RPAs completamente OK"
    bad_txt = "; ".join(
        f"{result_display_name(r).replace('RPA ', '')}: {(r.total_fail or len(r.failures) or 1)} incidencia(s)"
        for r in bad
    )
    return f"Descargas de madrugada {date_txt}: OK en {ok_txt}. Observaciones: {bad_txt}."


def build_email_body(
    results: List[JobResult],
    run_dir: str,
    start_dt: dt.datetime,
    end_dt: dt.datetime,
    notes: Optional[List[str]] = None,
) -> str:
    failed = [r for r in results if r.status != "OK"]
    general = "OK" if not failed else "CON OBSERVACIONES"
    lines = [
        "Reporte de ejecuciones de madrugada",
        "",
        f"Estado general: {general}",
        f"Inicio: {human_dt(start_dt)}",
        f"Fin: {human_dt(end_dt)}",
        f"Duracion total: {duration_text((end_dt - start_dt).total_seconds())}",
    ]
    if notes:
        lines.extend(["", "Notas operativas:"])
        lines.extend(f"- {note}" for note in notes)
    lines.extend([
        "",
        "Mensaje sugerido para WhatsApp:",
        whatsapp_text(results, end_dt.date()),
        "",
        "Resumen por RPA:",
        "RPA | Fase | Mes | Estado | Inicio | Fin | Duracion | OK | Fallas",
        "--- | --- | --- | --- | --- | --- | --- | --- | ---",
    ])

    for result in results:
        lines.append(
            " | ".join([
                result.config.name,
                phase_label(result.phase),
                result_period_label(result),
                status_icon(result.status),
                human_dt(result.start_dt),
                human_dt(result.end_dt),
                duration_text(result.duration_seconds),
                str(result.total_ok if result.total_ok is not None else "-"),
                str(result.total_fail if result.total_fail is not None else len(result.failures)),
            ])
        )

    if failed:
        lines.extend(["", "Detalle de incidencias:"])
        for result in failed:
            lines.append("")
            lines.append(f"{result_display_name(result)}:")
            if not result.failures:
                lines.append(f"- Sin detalle parseado. Exit code: {result.exit_code}")
                continue
            for failure in result.failures[:80]:
                parts = []
                if failure.centro:
                    parts.append(f"IPRESS {failure.centro}")
                if failure.ipress:
                    parts.append(f"centro {failure.ipress}")
                if failure.red:
                    parts.append(f"red {failure.red}")
                if failure.macro:
                    parts.append(f"macro {failure.macro}")
                if failure.tipo:
                    parts.append(f"tipo {failure.tipo}")
                if failure.usuario:
                    parts.append(f"usuario a habilitar {failure.usuario}")
                if failure.login:
                    parts.append(f"login {failure.login}")
                if failure.fase:
                    parts.append(f"fase {failure.fase}")
                parts.append(f"motivo {failure.motivo or 'SIN_MOTIVO'}")
                lines.append("- " + " | ".join(parts))
            if len(result.failures) > 80:
                lines.append(f"- ... {len(result.failures) - 80} incidencias adicionales en el CSV adjunto.")
    else:
        lines.extend([
            "",
            "Todas las ejecuciones terminaron sin fallas finales registradas.",
        ])

    lines.extend([
        "",
        "Rutas de auditoria:",
    ])
    for result in results:
        lines.append(f"- {result_display_name(result)}: {short_path(result.run_dir)}")
    lines.append(f"- Orquestador: {run_dir}")
    lines.extend([
        "",
        "Nota: una falla en un RPA no detiene los siguientes; la cadena continua y el correo consolida el resultado final.",
    ])
    return "\n".join(lines)


def write_report_files(results: List[JobResult], run_dir: str) -> List[str]:
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    csv_path = os.path.join(run_dir, "reporte_madrugada.csv")
    json_path = os.path.join(run_dir, "reporte_madrugada.json")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        fields = [
            "rpa", "fase_ejecucion", "mes_a_procesar", "periodo", "estado", "exit_code", "inicio", "fin", "duracion_seg",
            "total_input", "total_ok", "total_fail", "centro", "ipress", "red", "tipo",
            "usuario", "login", "macro", "motivo", "fase_error", "archivo", "run_dir",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for result in results:
            failures = result.failures or [Failure(rpa=result.config.name)]
            for failure in failures:
                writer.writerow({
                    "rpa": result.config.name,
                    "fase_ejecucion": phase_label(result.phase),
                    "mes_a_procesar": result.mes_a_procesar,
                    "periodo": result_period_label(result),
                    "estado": result.status,
                    "exit_code": result.exit_code,
                    "inicio": human_dt(result.start_dt),
                    "fin": human_dt(result.end_dt),
                    "duracion_seg": f"{result.duration_seconds:.1f}",
                    "total_input": result.total_input,
                    "total_ok": result.total_ok,
                    "total_fail": result.total_fail,
                    "centro": failure.centro,
                    "ipress": failure.ipress,
                    "red": failure.red,
                    "tipo": failure.tipo,
                    "usuario": failure.usuario,
                    "login": failure.login,
                    "macro": failure.macro,
                    "motivo": failure.motivo,
                    "fase_error": failure.fase,
                    "archivo": failure.archivo,
                    "run_dir": result.run_dir,
                })

    payload = []
    for result in results:
        payload.append({
            "rpa": result.config.name,
            "code": result.config.code,
            "phase": result.phase,
            "phase_label": phase_label(result.phase),
            "mes_a_procesar": result.mes_a_procesar,
            "periodo": result_period_label(result),
            "effective_run_name": result.effective_run_name,
            "status": result.status,
            "exit_code": result.exit_code,
            "start": human_dt(result.start_dt),
            "end": human_dt(result.end_dt),
            "duration_seconds": result.duration_seconds,
            "total_input": result.total_input,
            "total_ok": result.total_ok,
            "total_fail": result.total_fail,
            "run_dir": result.run_dir,
            "failures": [failure.__dict__ for failure in result.failures],
            "notes": result.notes,
        })
    Path(json_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return [csv_path, json_path]


def send_report_email(subject: str, body: str, attachments: List[str]) -> None:
    if not parse_bool(os.getenv("MAIL_ENABLED", "false"), default=False):
        print("MAIL_SKIP | MAIL_ENABLED=false", flush=True)
        return
    smtp_to = split_list(os.getenv("SMTP_TO", ""))
    if not smtp_to:
        print("MAIL_SKIP | SMTP_TO vacio", flush=True)
        return
    send_smtp_mail(
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587") or "587"),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_pass=os.getenv("SMTP_PASS", ""),
        mail_from=os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")),
        mail_to=smtp_to,
        mail_cc=split_list(os.getenv("SMTP_CC", "")),
        subject=subject,
        body_text=body,
        attachment_paths=attachments,
    )
    print(f"MAIL_OK | to_count={len(smtp_to)} | cc_count={len(split_list(os.getenv('SMTP_CC', '')))}", flush=True)


def main() -> int:
    project_dir = Path(__file__).resolve().parents[1]
    env_file = Path(os.getenv("ENV_FILE", project_dir / ".env"))
    if not env_file.is_absolute():
        env_file = project_dir / env_file
    load_env_file(env_file)

    run_name = os.getenv("ORCH_RUN_NAME", "ORQUESTADOR_MADRUGADA")
    logs_dir = Path(os.getenv("LOGS_DIR", project_dir / "logs"))
    if not logs_dir.is_absolute():
        logs_dir = project_dir / logs_dir
    run_dir = str(logs_dir / f"RUN_{run_name}_{ts_now()}")
    Path(run_dir).mkdir(parents=True, exist_ok=True)

    start_dt = dt.datetime.now()
    print(f"ORCH_START | run_dir={run_dir}", flush=True)

    order = split_list(os.getenv("JOB_ORDER", "MENSUAL,TELE_TRIAJE,TELE_URGENCIA,MEDICO_NO_MEDICO"))
    jobs = [build_job_config(code) for code in order if code in VALID_JOB_CODES]
    suppress_child_mail = parse_bool(os.getenv("SUPPRESS_CHILD_MAIL", "true"), default=True)
    run_date = start_dt.date()
    previous_period = month_label_for_token("ANTERIOR", run_date)
    current_period = month_label_for_token("ACTUAL", run_date)
    orch_notes: List[str] = []

    results = []
    for job in jobs:
        if not job.enabled:
            print(f"JOB_SKIP | {job.code} | disabled", flush=True)

    enabled_jobs = [job for job in jobs if job.enabled]
    close_active = should_run_month_start_close(run_date)
    close_jobs: Optional[List[JobConfig]] = None
    locked_close_jobs: List[JobConfig] = []
    if close_active:
        close_jobs = []
        for job in enabled_jobs:
            lock_path = month_start_close_lock_path(project_dir, previous_period, job)
            if is_month_start_close_job_locked(project_dir, previous_period, job):
                locked_close_jobs.append(job)
                note = f"Cierre {previous_period} omitido para {job.name}: periodo ya marcado como cerrado."
                orch_notes.append(note)
                print(
                    f"MONTH_START_CLOSE_SKIP | {job.code} | period={previous_period} | lock={lock_path}",
                    flush=True,
                )
            else:
                close_jobs.append(job)

    executions = build_job_executions(enabled_jobs, run_date, close_jobs=close_jobs)
    print(
        "ORCH_PLAN | "
        f"run_date={run_date.isoformat()} | jobs={len(enabled_jobs)} | executions={len(executions)} | "
        f"month_start_close={str(close_active).lower()} | "
        f"previous_period={previous_period} | current_period={current_period} | "
        f"close_pending={len(close_jobs) if close_jobs is not None else 0} | "
        f"close_locked={len(locked_close_jobs)} | "
        f"lock_enabled={str(month_start_close_lock_enabled()).lower()} | "
        f"force_close={str(month_start_close_force()).lower()}",
        flush=True,
    )

    for execution in executions:
        job = execution.config
        print(
            f"JOB_START | {job.code} | {job.name} | phase={execution.phase} | "
            f"mes={execution.mes_a_procesar} | run_name={execution.run_name}",
            flush=True,
        )
        result = run_job(execution, suppress_child_mail=suppress_child_mail)
        results.append(result)
        if execution.phase == "CIERRE_MES_ANTERIOR":
            if result.status == "OK":
                lock_path = write_month_start_close_job_lock(project_dir, previous_period, result, run_dir)
                if lock_path:
                    orch_notes.append(f"Cierre {previous_period} marcado como cerrado para {job.name}.")
                    print(
                        f"MONTH_START_CLOSE_LOCK_OK | {job.code} | period={previous_period} | lock={lock_path}",
                        flush=True,
                    )
            else:
                print(
                    f"MONTH_START_CLOSE_LOCK_SKIP | {job.code} | period={previous_period} | status={result.status}",
                    flush=True,
                )
        print(
            f"JOB_END | {job.code} | phase={execution.phase} | mes={execution.mes_a_procesar} | "
            f"status={result.status} | exit_code={result.exit_code} | "
            f"ok={result.total_ok} | fail={result.total_fail} | run_dir={result.run_dir}",
            flush=True,
        )

    end_dt = dt.datetime.now()
    attachments = write_report_files(results, run_dir)
    has_problem = any(r.status != "OK" for r in results)
    subject_status = "OK" if not has_problem else "OBSERVACION"
    subject = f"[{subject_status}] Reporte RPAs madrugada - {end_dt.strftime('%d/%m/%Y')}"
    body = build_email_body(results, run_dir, start_dt, end_dt, notes=orch_notes)
    Path(run_dir, "correo_madrugada.txt").write_text(body, encoding="utf-8")

    try:
        send_report_email(subject, body, attachments)
    except Exception as e:
        print(f"MAIL_WARN | {type(e).__name__}: {e}", flush=True)

    print(f"ORCH_END | status={subject_status} | run_dir={run_dir}", flush=True)
    return 0 if not has_problem else 2


if __name__ == "__main__":
    sys.exit(main())
