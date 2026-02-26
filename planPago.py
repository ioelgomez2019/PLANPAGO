"""
╔══════════════════════════════════════════════════════════════╗
║          PLAN DE PAGOS - CAJA LOS ANDES                     ║
║          Cuotas Constantes (Sistema Francés)                 ║
╚══════════════════════════════════════════════════════════════╝

Autor  : Adaptado del sistema original
Lógica : Equivalent al método CalculaPpgCuotasConstantes2
"""

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from dataclasses import dataclass, field
from typing import Optional
import math


# ─────────────────────────────────────────────────────────────
# ESTRUCTURAS DE DATOS
# ─────────────────────────────────────────────────────────────

@dataclass
class CuotaPlan:
    """Representa una fila del plan de pagos."""
    cuota: int
    fecha: date
    dias: int
    dias_acu: int
    frc: float           # Factor de recuperación de capital
    sal_cap: float       # Saldo capital al inicio de la cuota
    capital: float       # Amortización de capital
    interes: float       # Interés de la cuota
    comisiones: float    # Comisiones / seguros
    imp_cuota: float     # Importe total de la cuota


@dataclass
class ParametrosPlanPago:
    """
    Parámetros de entrada para generar el plan de pagos.

    Campos
    ------
    monto_desembolso      : Monto neto desembolsado (ej. 5000.00)
    tasa_interes_anual    : TEA como fracción (ej. 56.99% → 0.5699)
    fecha_desembolso      : Fecha en que se entrega el dinero
    num_cuotas            : Número de cuotas totales
    dias_gracia           : Días de gracia antes de la primera cuota
    tipo_periodo          : 1 = Fecha Fija  |  2 = Periodo Fijo
    dia_fec_pago          : Si tipo=1 → día fijo del mes (ej. 24)
                            Si tipo=2 → cada cuántos días (ej. 30)
    fecha_primera_cuota   : Fecha exacta de la primera cuota
    nro_cuotas_gracia     : Cuotas en las que no se amortiza capital (gracia total)
    forma_calculo_tasa    : 1 = base 360 días  |  2 = base 30 días
    """
    monto_desembolso: float
    tasa_interes_anual: float
    fecha_desembolso: date
    num_cuotas: int
    dias_gracia: int
    tipo_periodo: int           # 1 = Fecha Fija, 2 = Periodo Fijo
    dia_fec_pago: int           # día del mes (tipo=1) o nro días (tipo=2)
    fecha_primera_cuota: date
    nro_cuotas_gracia: int = 0
    forma_calculo_tasa: int = 1  # 1 → base 360


# ─────────────────────────────────────────────────────────────
# TASA EFECTIVA DIARIA
# ─────────────────────────────────────────────────────────────

def calcular_tasa_efectiva_diaria(tasa_anual: float, forma: int) -> float:
    """
    Convierte la TEA a tasa efectiva diaria.

    forma=1 → base 360 días  → (1+TEA)^(1/360) - 1
    forma=2 → base 30 días   → (1+TEA)^(1/30)  - 1
    """
    if forma == 1:
        return math.pow(1.0 + tasa_anual, 1.0 / 360.0) - 1.0
    elif forma == 2:
        return math.pow(1.0 + tasa_anual, 1.0 / 30.0) - 1.0
    else:
        raise ValueError(f"forma_calculo_tasa={forma} no válido. Use 1 o 2.")


# ─────────────────────────────────────────────────────────────
# GENERACIÓN DE FECHAS
# ─────────────────────────────────────────────────────────────

def _fecha_valida_dia_mes(dia: int, mes: int, anio: int) -> date:
    """
    Devuelve la fecha con ese día/mes/año.
    Si el día no existe en ese mes retrocede hasta encontrar uno válido
    (p.ej. 31 de febrero → 28/29 de febrero).
    """
    d = dia
    while d >= 1:
        try:
            return date(anio, mes, d)
        except ValueError:
            d -= 1
    raise ValueError(f"No se pudo crear fecha válida para mes={mes}, año={anio}")


def _generar_fechas_fecha_fija(params: ParametrosPlanPago) -> list[tuple[date, int, int]]:
    """
    Genera lista de (fecha, dias, dias_acumulados) para tipo_periodo=1 (Fecha Fija).
    La lógica replica exactamente el bloque C# 'Fecha Fija'.
    """
    fechas = []
    dias_acu = 0
    fecha_anterior = params.fecha_desembolso

    for i in range(1, params.num_cuotas + 1):
        if i == 1:
            # Primera cuota: usar fecha_primera_cuota directamente
            fecha_cuota = params.fecha_primera_cuota
            dias = (fecha_cuota - params.fecha_desembolso).days
        else:
            # Avanzar un mes desde la cuota anterior
            fecha_ant = fechas[-1][0]
            nuevo_mes = fecha_ant.month + 1
            nuevo_anio = fecha_ant.year
            if nuevo_mes > 12:
                nuevo_mes = 1
                nuevo_anio += 1
            fecha_cuota = _fecha_valida_dia_mes(params.dia_fec_pago, nuevo_mes, nuevo_anio)
            dias = (fecha_cuota - fecha_ant).days

        dias_acu += dias
        fechas.append((fecha_cuota, dias, dias_acu))

    return fechas


def _generar_fechas_periodo_fijo(params: ParametrosPlanPago) -> list[tuple[date, int, int]]:
    """
    Genera lista de (fecha, dias, dias_acumulados) para tipo_periodo=2 (Periodo Fijo).
    La lógica replica el bloque C# 'Periodo Fijo'.
    """
    fechas = []
    dias_acu = 0
    fecha_cuota = params.fecha_primera_cuota

    for i in range(1, params.num_cuotas + 1):
        if i == 1:
            dias = params.dia_fec_pago + params.dias_gracia
            dias_acu += dias
        else:
            dias = params.dia_fec_pago
            dias_acu += dias
            fecha_cuota = fecha_cuota + timedelta(days=params.dia_fec_pago)

        fechas.append((fecha_cuota, dias, dias_acu))

    return fechas


# ─────────────────────────────────────────────────────────────
# CUOTA APROXIMADA (búsqueda por factor acumulado)
# ─────────────────────────────────────────────────────────────

def _calcular_cuota_sugerida(monto: float, fac_acumul: float, decimales: int = 2) -> float:
    """Cuota inicial aproximada = Monto / Σ FRC."""
    if fac_acumul == 0:
        return 0.0
    return round(monto / fac_acumul, decimales)


# ─────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────────────────────

def generar_plan_pagos(params: ParametrosPlanPago) -> list[CuotaPlan]:
    """
    Genera el plan de pagos con cuotas constantes (sistema francés).

    Pasos
    -----
    1. Calcular tasa efectiva diaria.
    2. Generar fechas y días acumulados según tipo de periodo.
    3. Calcular FRC (Factor Recuperación Capital) por cuota.
    4. Calcular cuota aproximada usando Σ FRC.
    5. Iterar para ajustar la cuota hasta que el saldo final ≈ 0.
    6. Ajustar última cuota exactamente.

    Retorna
    -------
    Lista de CuotaPlan con el detalle de cada cuota.
    """

    TED = calcular_tasa_efectiva_diaria(params.tasa_interes_anual, params.forma_calculo_tasa)
    DEC = 2   # decimales de redondeo

    # ── Paso 1: Generar cronograma de fechas ──────────────────
    if params.tipo_periodo == 1:
        cronograma = _generar_fechas_fecha_fija(params)
    elif params.tipo_periodo == 2:
        cronograma = _generar_fechas_periodo_fijo(params)
    else:
        raise ValueError("tipo_periodo debe ser 1 (Fecha Fija) o 2 (Periodo Fijo).")

    # ── Paso 2: Calcular FRC acumulado ────────────────────────
    frcs = []
    fac_acumul = 0.0
    for (_, __, dias_acu) in cronograma:
        frc = 1.0 / math.pow(1.0 + TED, dias_acu)
        frcs.append(frc)
        fac_acumul += frc

    # ── Paso 3: Cuota inicial ─────────────────────────────────
    cuota_base = _calcular_cuota_sugerida(params.monto_desembolso, fac_acumul, DEC)

    # ── Paso 4: Iteración para saldo final = 0 ────────────────
    MAX_ITER   = 20
    ERR_MAX    = 0.09 * params.num_cuotas
    cuota_iter = cuota_base
    saldo_final = params.monto_desembolso
    mejor_plan: list[CuotaPlan] = []
    menor_diff = 9_999_999.0

    potenc_dos = 0.0
    razon_busq = 0.0
    flag_factor = False
    itera_true  = 0
    ind_sal_ite = False
    num_sal_ite = 0

    for iteracion in range(MAX_ITER):
        plan_iter: list[CuotaPlan] = []
        saldo = round(params.monto_desembolso, DEC)

        for idx, (fecha, dias, dias_acu) in enumerate(cronograma):
            num_cuota = idx + 1
            interes = round(saldo * (math.pow(1.0 + TED, dias) - 1.0), DEC)
            cuota_redond = round(cuota_iter, DEC)

            # Cuotas en periodo de gracia: no amortiza capital
            if params.nro_cuotas_gracia >= num_cuota:
                capital = 0.0
            else:
                capital = cuota_redond - interes

            imp_cuota = capital + interes

            plan_iter.append(CuotaPlan(
                cuota     = num_cuota,
                fecha     = fecha,
                dias      = dias,
                dias_acu  = dias_acu,
                frc       = frcs[idx],
                sal_cap   = round(saldo, DEC),
                capital   = round(capital, DEC),
                interes   = round(interes, DEC),
                comisiones= 0.0,
                imp_cuota = round(imp_cuota, DEC),
            ))

            saldo = saldo - capital

        saldo_final = round(saldo, DEC)

        # Guardar el plan con menor diferencia de saldo
        diff = abs(plan_iter[-1].sal_cap - plan_iter[-1].capital)
        if diff <= menor_diff:
            menor_diff  = diff
            mejor_plan  = [c for c in plan_iter]   # copia

        # ¿Convergió?
        if abs(saldo_final) <= ERR_MAX:
            break

        # Ajuste de cuota (bisección adaptativa, igual que C#)
        if itera_true > 0:
            if saldo_final < 0:
                potenc_dos = potenc_dos / 2.0
                cuota_iter = cuota_base - razon_busq
                flag_factor = True
            else:
                if not flag_factor:
                    potenc_dos *= 2.0
        else:
            potenc_dos = 2.0

        itera_true += 1
        dias_acu_total = cronograma[-1][2]
        razon_busq = round(saldo_final * potenc_dos / dias_acu_total, 10)
        cuota_iter = cuota_iter + razon_busq

        if razon_busq == 0:
            if not ind_sal_ite:
                ind_sal_ite = True
                num_sal_ite = iteracion
            cuota_iter += 0.01

        if ind_sal_ite and iteracion == num_sal_ite + 1:
            break

    # ── Paso 5: Ajuste exacto última cuota ───────────────────
    if mejor_plan:
        ult = mejor_plan[-1]
        dias_ult = ult.dias
        saldo_ult = ult.sal_cap
        interes_ult = round(saldo_ult * (math.pow(1.0 + TED, dias_ult) - 1.0), DEC)
        capital_ult = round(saldo_ult, DEC)
        imp_ult     = round(capital_ult + interes_ult + ult.comisiones, DEC)

        mejor_plan[-1] = CuotaPlan(
            cuota     = ult.cuota,
            fecha     = ult.fecha,
            dias      = ult.dias,
            dias_acu  = ult.dias_acu,
            frc       = ult.frc,
            sal_cap   = ult.sal_cap,
            capital   = capital_ult,
            interes   = interes_ult,
            comisiones= ult.comisiones,
            imp_cuota = imp_ult,
        )

    return mejor_plan


# ─────────────────────────────────────────────────────────────
# IMPRIMIR PLAN DE PAGOS (como en la imagen)
# ─────────────────────────────────────────────────────────────

def imprimir_plan_pagos(plan: list[CuotaPlan], params: ParametrosPlanPago):
    """
    Imprime el plan de pagos en formato tabular, idéntico a la imagen
    de referencia (columnas: cuota, fecha, dias, dias_acu, frc,
    sal_cap, capital, interes, comisiones, imp_cuota).
    """
    tipo_str = "Fecha Fija" if params.tipo_periodo == 1 else "Periodo Fijo"
    tea_pct  = params.tasa_interes_anual * 100

    print("=" * 115)
    print(f"  CAJA LOS ANDES  —  PLAN DE PAGOS")
    print(f"  Monto desembolsado : S/ {params.monto_desembolso:,.2f}")
    print(f"  TEA                : {tea_pct:.4f} %")
    print(f"  Fecha desembolso   : {params.fecha_desembolso.strftime('%d/%m/%Y')}")
    print(f"  N° cuotas          : {params.num_cuotas}")
    print(f"  Tipo periodo       : {tipo_str}  |  Dia/periodo: {params.dia_fec_pago}")
    print(f"  Primera cuota      : {params.fecha_primera_cuota.strftime('%d/%m/%Y')}")
    print("=" * 115)

    # Encabezados
    col = "{:>5}  {:<22}  {:>5}  {:>8}  {:>26}  {:>9}  {:>9}  {:>8}  {:>11}  {:>9}"
    print(col.format(
        "cuota", "fecha", "dias", "dias_acu",
        "frc", "sal_cap", "capital", "interes", "comisiones", "imp_cuota"
    ))
    print("-" * 115)

    total_capital = 0.0
    total_interes = 0.0
    total_comis   = 0.0
    total_cuota   = 0.0

    row = "{:>5}  {:<22}  {:>5}  {:>8}  {:>26.22f}  {:>9.2f}  {:>9.2f}  {:>8.2f}  {:>11.2f}  {:>9.2f}"
    for c in plan:
        print(row.format(
            c.cuota,
            c.fecha.strftime("%d/%m/%Y %H:%M:%S"),
            c.dias,
            c.dias_acu,
            c.frc,
            c.sal_cap,
            c.capital,
            c.interes,
            c.comisiones,
            c.imp_cuota,
        ))
        total_capital += c.capital
        total_interes += c.interes
        total_comis   += c.comisiones
        total_cuota   += c.imp_cuota

    print("-" * 115)
    print(col.format(
        "TOTAL", "", "", "",
        "", f"{total_capital:.2f}", f"{total_capital:.2f}",
        f"{total_interes:.2f}", f"{total_comis:.2f}", f"{total_cuota:.2f}"
    ))
    print("=" * 115)


# ─────────────────────────────────────────────────────────────
# EJEMPLO DE USO  (replica exacta de los parámetros del código)
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # ── EJEMPLO 1: Fecha Fija (tipo_periodo=1) ────────────────
    print("\n>>> EJEMPLO 1 — FECHA FIJA\n")

    params_fecha_fija = ParametrosPlanPago(
        monto_desembolso   = 5000.00,
        tasa_interes_anual = 56.99 / 100.0,   # 56.99% TEA
        fecha_desembolso   = date(2026, 1, 29),
        num_cuotas         = 10,
        dias_gracia        = 0,
        tipo_periodo       = 1,                # 1 = Fecha Fija
        dia_fec_pago       = 24,               # día 24 de cada mes
        fecha_primera_cuota= date(2026, 2, 24),
        nro_cuotas_gracia  = 0,
        forma_calculo_tasa = 1,                # base 360
    )

    plan1 = generar_plan_pagos(params_fecha_fija)
    imprimir_plan_pagos(plan1, params_fecha_fija)

    # ── EJEMPLO 2: Periodo Fijo (tipo_periodo=2) ──────────────
    print("\n>>> EJEMPLO 2 — PERIODO FIJO (cada 30 días)\n")

    params_periodo_fijo = ParametrosPlanPago(
        monto_desembolso   = 5000.00,
        tasa_interes_anual = 56.99 / 100.0,
        fecha_desembolso   = date(2026, 1, 29),
        num_cuotas         = 10,
        dias_gracia        = 0,
        tipo_periodo       = 2,                # 2 = Periodo Fijo
        dia_fec_pago       = 30,               # cada 30 días
        fecha_primera_cuota= date(2026, 2, 28),
        nro_cuotas_gracia  = 0,
        forma_calculo_tasa = 1,
    )

    plan2 = generar_plan_pagos(params_periodo_fijo)
    imprimir_plan_pagos(plan2, params_periodo_fijo)