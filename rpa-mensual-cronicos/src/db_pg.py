import json
from typing import Optional, Tuple
from psycopg2.extras import execute_values
import datetime
import os
import re
import socket
from typing import Optional, Tuple

import psycopg2


_RE_FILE_META = re.compile(
    r"^(?P<center>[^_]+)_(?P<ini>\d{8})_(?P<fin>\d{8})_(?P<tipo>.+?)(?:\.txt)?$",
    re.IGNORECASE
)


def parse_file_metadata(filename: str) -> Tuple[Optional[str], Optional[datetime.date], Optional[datetime.date], Optional[str], Optional[str]]:
    """
    Devuelve:
    (codigo_centro, fecha_inicio_data, fecha_fin_data, tipo_descarga_archivo, scope_descarga)
    """
    base = os.path.basename(filename or "").strip()
    m = _RE_FILE_META.match(base)
    if not m:
        return None, None, None, None, None

    center = m.group("center")
    ini = datetime.datetime.strptime(m.group("ini"), "%Y%m%d").date()
    fin = datetime.datetime.strptime(m.group("fin"), "%Y%m%d").date()
    tipo = m.group("tipo")

    if ini == fin:
        scope = "DIARIO"
    else:
        scope = "RANGO"

    return center, ini, fin, tipo, scope



class PgRPAControl:

    def prune_stg_cext_prod_diario_keep_run(self, id_run_keep: int) -> None:
        sql = """
        delete from stg.cext_prod_diario
        where id_run <> %s;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (id_run_keep,))

    def prune_stg_cext_prod_mensual_keep_run(self, periodo_proceso: str, id_run_keep: int) -> None:
        sql = """
        delete from stg.cext_prod_mensual
        where periodo_proceso = %s
          and id_run <> %s;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (periodo_proceso, id_run_keep))

    def call_archivar_mensual_raw_cerrado(self, periodo_proceso: str):
        sql = """
        select *
        from ops.fn_archivar_mensual_raw_cerrado(%s);
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (periodo_proceso,))
                return cur.fetchone()

    def call_refresh_mensual_actual(
        self,
        id_run: int,
        run_uuid: str,
        periodo_proceso: str,
        fecha_ini,
        fecha_fin
    ) -> None:
        sql = "call ops.sp_refresh_mensual_actual(%s, %s, %s, %s, %s);"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (id_run, run_uuid, periodo_proceso, fecha_ini, fecha_fin))

    def call_cerrar_periodo_mensual(
        self,
        periodo_proceso: str,
        observacion: Optional[str] = None
    ) -> None:
        sql = "call ops.sp_cerrar_periodo_mensual(%s, %s);"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (periodo_proceso, observacion))


    def set_report_status(
    	self,
    	report_code: str,
    	report_name: str,
    	rpa_job_code: str,
    	status: str,
    	message: str,
    	target_date_start,
    	target_date_end,
    	last_run_uuid: Optional[str] = None,
    	started_at=None,
    	finished_at=None,
    	last_success_at=None,
    	row_count: Optional[int] = None
    ) -> None:
    	sql = """
    	select control.fn_set_report_status(
    	    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    	);
    	"""
    	with self._conn() as conn:
    	    with conn.cursor() as cur:
    	        cur.execute(
    	            sql,
    	            (
       	  	         report_code,
           	         report_name,
      	                 rpa_job_code,
                         status,
                         message,
                         target_date_start,
                         target_date_end,
                         last_run_uuid,
                         started_at,
                         finished_at,
                         last_success_at,
                         row_count,
                    ),
                )


    def upsert_user_health(
        self,
        id_run: int,
        run_uuid: str,
        username: str,
        macro_asignada: str,
        status: str,
        detail: str = ""
    ) -> None:
        sql_hist = """
        insert into control.rpa_user_health_history (
            id_run, username, macro_asignada, status, detail
        )
        values (%s, %s, %s, %s, %s)
        on conflict (id_run, username, status) do nothing;
        """

        sql_curr = """
        insert into control.rpa_user_health_current (
            username, macro_asignada, status, detail, id_run, last_run_uuid, last_detected_at, updated_at
        )
        values (%s, %s, %s, %s, %s, %s, now(), now())
        on conflict (username)
        do update set
            macro_asignada = excluded.macro_asignada,
            status = excluded.status,
            detail = excluded.detail,
            id_run = excluded.id_run,
            last_run_uuid = excluded.last_run_uuid,
            last_detected_at = now(),
            updated_at = now();
        """

        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_hist, (id_run, username, macro_asignada, status, detail))
                cur.execute(sql_curr, (username, macro_asignada, status, detail, id_run, run_uuid))

    def create_alert_event(
        self,
        id_run: int,
        channel: str,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        payload: Optional[dict] = None
    ) -> None:
        sql = """
        insert into control.rpa_alert_event (
            id_run, channel, alert_type, severity, title, message, payload, status
        )
        values (%s, %s, %s, %s, %s, %s, %s::jsonb, 'PENDING');
        """
        import json
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        id_run,
                        channel,
                        alert_type,
                        severity,
                        title,
                        message,
                        json.dumps(payload or {}, ensure_ascii=False),
                    )
                )

    def get_active_overrides(self, centros: list[str]) -> dict:
        if not centros:
            return {}

        sql = """
        select codigo_centro, macro_declarada, macro_efectiva, usuario_efectivo, success_count
        from config.rpa_centro_usuario_override
        where activo = true
          and codigo_centro = any(%s);
        """

        out = {}
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (centros,))
                for row in cur.fetchall():
                    out[str(row[0])] = {
                        "codigo_centro": str(row[0]),
                        "macro_declarada": row[1],
                        "macro_efectiva": row[2],
                        "usuario_efectivo": row[3],
                        "success_count": int(row[4] or 0),
                    }
        return out

    def upsert_override(
        self,
        codigo_centro: str,
        macro_declarada: str,
        macro_efectiva: str,
        usuario_efectivo: str,
        run_uuid: str,
        fuente: str = "AUTO"
    ) -> None:
        sql = """
        insert into config.rpa_centro_usuario_override (
            codigo_centro,
            macro_declarada,
            macro_efectiva,
            usuario_efectivo,
            fuente,
            activo,
            success_count,
            first_learned_at,
            last_confirmed_at,
            last_run_uuid,
            updated_at
        )
        values (%s, %s, %s, %s, %s, true, 1, now(), now(), %s, now())
        on conflict (codigo_centro)
        do update set
            macro_declarada = excluded.macro_declarada,
            macro_efectiva = excluded.macro_efectiva,
            usuario_efectivo = excluded.usuario_efectivo,
            fuente = excluded.fuente,
            activo = true,
            success_count = config.rpa_centro_usuario_override.success_count + 1,
            last_confirmed_at = now(),
            last_run_uuid = excluded.last_run_uuid,
            updated_at = now();
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        codigo_centro,
                        macro_declarada,
                        macro_efectiva,
                        usuario_efectivo,
                        fuente,
                        run_uuid,
                    )
                )

    def mark_override_failure(self, codigo_centro: str, reason: str) -> None:
        sql = """
        update config.rpa_centro_usuario_override
           set last_failure_reason = %s,
               updated_at = now()
         where codigo_centro = %s;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (reason, codigo_centro))

    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self.host = host
        self.port = int(port)
        self.database = database
        self.user = user
        self.password = password

    def _conn(self):
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
            connect_timeout=10
        )

    def get_or_create_job(self, codigo: str, nombre: str) -> int:
        sql = """
        insert into control.rpa_job (codigo, nombre, activo)
        values (%s, %s, true)
        on conflict (codigo)
        do update set nombre = excluded.nombre
        returning id_job;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (codigo, nombre))
                row = cur.fetchone()
                return int(row[0])

    def create_run(
        self,
        id_job: int,
        run_uuid: str,
        run_type: str,
        target_date,
        fecha_ini_data,
        fecha_fin_data,
        tag: str,
        estado: str = "RUNNING",
        observacion: Optional[str] = None
    ) -> int:
        sql = """
        insert into control.rpa_job_run (
            id_job, run_uuid, run_type, target_date,
            fecha_ini_data, fecha_fin_data, tag, estado,
            started_at, host_name, observacion
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, now(), %s, %s)
        returning id_run;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        id_job, run_uuid, run_type, target_date,
                        fecha_ini_data, fecha_fin_data, tag, estado,
                        socket.gethostname(), observacion
                    )
                )
                row = cur.fetchone()
                return int(row[0])

    def log_event(self, id_run: int, level: str, event_type: str, message: str) -> None:
        sql = """
        insert into control.rpa_job_log (id_run, level, event_type, message)
        values (%s, %s, %s, %s);
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (id_run, level, event_type, message))

    def register_file(
        self,
        id_run: int,
        file_name: str,
        file_path: str,
        file_size_bytes: int,
        estado: str = "DOWNLOADED",
        publicado_txt: bool = True,
        cargado_stg: bool = False
    ) -> int:
        center, ini, fin, tipo, scope = parse_file_metadata(file_name)

        sql = """
        insert into raw.archivo_descargado (
            id_run, nombre_archivo, ruta_archivo,
            codigo_centro, fecha_inicio_data, fecha_fin_data,
            tipo_descarga_archivo, scope_descarga,
            tamanio_bytes, publicado_txt, cargado_stg, estado
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning id_archivo;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        id_run, file_name, file_path,
                        center, ini, fin, tipo, scope,
                        file_size_bytes, publicado_txt, cargado_stg, estado
                    )
                )
                row = cur.fetchone()
                return int(row[0])

    def get_expected_columns(self) -> dict:
        sql = """
        select canonical_name, es_requerida, es_texto_critico
        from config.explotadatos_columna
        where activa = true;
        """
        out = {}
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                for row in cur.fetchall():
                    out[str(row[0])] = {
                        "required": bool(row[1]),
                        "text_critical": bool(row[2]),
                    }
        return out

    def get_column_aliases(self) -> dict:
        sql = """
        select alias_name, canonical_name
        from config.explotadatos_columna_alias
        where activa = true;
        """
        out = {}
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                for row in cur.fetchall():
                    out[str(row[0])] = str(row[1])
        return out

    def insert_file_header_version(
        self,
        id_run: int,
        id_archivo: int,
        tipo_descarga_archivo: str,
        header_signature: str,
        header_original: list,
        header_normalized: list,
        matched_columns: list,
        unknown_columns: list,
        missing_required: list,
        status: str
    ) -> None:
        sql = """
        insert into raw.file_header_version (
            id_run, id_archivo, tipo_descarga_archivo, header_signature,
            header_original, header_normalized, matched_columns,
            unknown_columns, missing_required, status
        )
        values (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)
        on conflict (id_archivo)
        do update set
            header_signature = excluded.header_signature,
            header_original = excluded.header_original,
            header_normalized = excluded.header_normalized,
            matched_columns = excluded.matched_columns,
            unknown_columns = excluded.unknown_columns,
            missing_required = excluded.missing_required,
            status = excluded.status;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        id_run,
                        id_archivo,
                        tipo_descarga_archivo,
                        header_signature,
                        json.dumps(header_original, ensure_ascii=False),
                        json.dumps(header_normalized, ensure_ascii=False),
                        json.dumps(matched_columns, ensure_ascii=False),
                        json.dumps(unknown_columns, ensure_ascii=False),
                        json.dumps(missing_required, ensure_ascii=False),
                        status,
                    )
                )

    def mark_file_loaded_to_staging(self, id_archivo: int, loaded: bool, estado: str) -> None:
        sql = """
        update raw.archivo_descargado
           set cargado_stg = %s,
               estado = %s
         where id_archivo = %s;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (loaded, estado, id_archivo))

    def bulk_insert_cext_prod_diario(self, rows: list[tuple]) -> None:
        if not rows:
            return

        sql = """
        insert into stg.cext_prod_diario (
            id_run, id_archivo, row_num,
            centro, periodo, cod_servicio, servicio, codactividad, actividad, codsubacti, subactividad,
            fecha_solic, fecha_cita, hora_cita, condicion_cita, codestcita, estado_cita, codtipcita, tipo_cita,
            h_c, ubicacion_hc, acto_med, dni_medico, cmp, codgrupocup, grupo_ocupacional, profesional,
            tipo_paciente, doc_paciente, autogenerado, paciente, fecnacimpaciente, edad, sexo,
            tel_fijo, tel_movil, cod_tipseguro, tipo_seguro, codtiparent, tiparentesco,
            codprecedencia, descprecedencia, cas_adscripcion, nombadscripcion, n_r_c_ser, n_r_c_est,
            horainicio, horafinal, codubigdomic, ubigeodomic, turno, codtipprogramac, tip_programacion,
            useregistro, fecha_reg, hora_reg, usermodifica, fecha_modifica, hora_modifica,
            useranula, fecha_anula, hora_anula, orden_atencion, codmotdeser, motivo_desercion,
            codmodotorcita, modalidadotorcita, motivelimcita, numreferorigen, codconsultorio,
            desconsultorio, ultcie10aten, estado_programacion, motivo_suspension, fechreferencia,
            usuaregistro, estadreferencia, observacion,
            extra_columns, row_hash
        )
        values %s
        on conflict (id_archivo, row_num) do nothing;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                execute_values(cur, sql, rows, page_size=500)


    def bulk_insert_cext_prod_mensual(self, rows):
        if not rows:
            return

        sql = """
        insert into stg.cext_prod_mensual (
            periodo_proceso,
            id_run, id_archivo, row_num,
            centro, periodo, cod_servicio, servicio, codactividad, actividad, codsubacti, subactividad,
            fecha_solic, fecha_cita, hora_cita, condicion_cita, codestcita, estado_cita, codtipcita, tipo_cita,
            h_c, ubicacion_hc, acto_med, dni_medico, cmp, codgrupocup, grupo_ocupacional, profesional,
            tipo_paciente, doc_paciente, autogenerado, paciente, fecnacimpaciente, edad, sexo,
            tel_fijo, tel_movil, cod_tipseguro, tipo_seguro, codtiparent, tiparentesco,
            codprecedencia, descprecedencia, cas_adscripcion, nombadscripcion, n_r_c_ser, n_r_c_est,
            horainicio, horafinal, codubigdomic, ubigeodomic, turno, codtipprogramac, tip_programacion,
            useregistro, fecha_reg, hora_reg, usermodifica, fecha_modifica, hora_modifica,
            useranula, fecha_anula, hora_anula, orden_atencion, codmotdeser, motivo_desercion,
            codmodotorcita, modalidadotorcita, motivelimcita, numreferorigen, codconsultorio,
            desconsultorio, ultcie10aten, estado_programacion, motivo_suspension, fechreferencia,
            usuaregistro, estadreferencia, observacion,
            extra_columns,
            row_hash
        ) values %s
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                execute_values(cur, sql, rows, page_size=500)


    def refresh_medicos_cenate_current(self, rows: list[tuple]) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("truncate table ref.medicos_cenate_activos_current;")

                if rows:
                    sql = """
                    insert into ref.medicos_cenate_activos_current (
                        dni_medico,
                        nombre_completo,
                        area,
                        id_servicio,
                        cod_servicio,
                        servicio,
                        tipo_personal,
                        id_reg_lab,
                        regimen_laboral,
                        fecha_actualizacion
                    )
                    values %s
                    """
                    execute_values(cur, sql, rows, page_size=500)

    def set_report_status(
        self,
        report_code: str,
        report_name: str,
        rpa_job_code: str,
        status: str,
        message: str,
        target_date_start,
        target_date_end,
        last_run_uuid: str,
        started_at=None,
        finished_at=None,
        last_success_at=None,
        row_count: Optional[int] = None
    ) -> None:
        sql = """
        select control.fn_set_report_status(
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        );
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        report_code,
                        report_name,
                        rpa_job_code,
                        status,
                        message,
                        target_date_start,
                        target_date_end,
                        last_run_uuid,
                        started_at,
                        finished_at,
                        last_success_at,
                        row_count
                    )
                )

    def call_refresh_reportes_diario(
        self,
        id_run: int,
        run_uuid: str,
        fecha_operativa,
        fecha_futuro_fin
    ) -> None:
        sql = "call ops.sp_refresh_reportes_diario(%s, %s, %s, %s);"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (id_run, run_uuid, fecha_operativa, fecha_futuro_fin))


    def finish_run(
        self,
        id_run: int,
        estado: str,
        total_input: int,
        total_ok: int,
        total_fail: int,
        duration_seconds: float,
        observacion: Optional[str] = None
    ) -> None:
        sql = """
        update control.rpa_job_run
           set estado = %s,
               total_input = %s,
               total_ok = %s,
               total_fail = %s,
               ended_at = now(),
               duration_seconds = %s,
               observacion = coalesce(%s, observacion)
         where id_run = %s;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        estado, total_input, total_ok, total_fail,
                        duration_seconds, observacion, id_run
                    )
                )
