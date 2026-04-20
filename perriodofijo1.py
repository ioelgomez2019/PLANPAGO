import re
import json
from datetime import date, timedelta
from dataclasses import dataclass
from typing import Optional
from decimal import Decimal, ROUND_HALF_UP, getcontext

getcontext().prec = 28


# ══════════════════════════════════════════════════════════════════════
# HELPERS DE REDONDEO
# ══════════════════════════════════════════════════════════════════════

def _d(value) -> Decimal:
    return Decimal(str(value))

def _round(x: Decimal, decimales: int) -> Decimal:
    fmt = Decimal(10) ** -decimales
    return x.quantize(fmt, rounding=ROUND_HALF_UP)

def _r2(x): return _round(x, 2)
def _r1(x): return _round(x, 1)
def _r10(x): return _round(x, 10)


# ══════════════════════════════════════════════════════════════════════
# 1. TABLA DE SEGUROS
# ══════════════════════════════════════════════════════════════════════

@dataclass
class TipoSeguro:
    id_tipo_seguro: int
    nombre: str
    n_valor: Decimal
    id_tipo_valor: int


TABLA_SEGUROS: dict[int, TipoSeguro] = {
    1:  TipoSeguro(1,  "SEGURO MULTIRIESGO",                               _d("0.001150"), 1),
    2:  TipoSeguro(2,  "SEGURO VIDA",                                      _d("5.000000"), 2),
    4:  TipoSeguro(4,  "SEGURO ONCOLÓGICO",                                _d("5.000000"), 2),
    5:  TipoSeguro(5,  "PLAN 1: A. EDUCATIVA",                             _d("2.500000"), 2),
    6:  TipoSeguro(6,  "PLAN 2: A. EDUCATIVA + A. SALUD",                  _d("5.750000"), 2),
    7:  TipoSeguro(7,  "PLAN 3: A. EDUCATIVA + A. SALUD + S. INCAPACIDAD", _d("8.500000"), 2),
    8:  TipoSeguro(8,  "SIN SEGURO DESGRAVAMEN",                           _d("0.000000"), 1),
    9:  TipoSeguro(9,  "SEGURO DESGRAVAMEN INDIVIDUAL",                    _d("0.001650"), 1),
    10: TipoSeguro(10, "SEGURO DESGRAVAMEN CONYUGAL",                      _d("0.002050"), 1),
    11: TipoSeguro(11, "SEGURO DESGRAVAMEN INDIVIDUAL ESPECIAL",           _d("0.001450"), 1),
    12: TipoSeguro(12, "SEGURO DESGRAVAMEN DEVOLUCIÓN",                    _d("0.002340"), 1),
}

_ID_DESGRAV_INDIVIDUAL          = 9
_ID_DESGRAV_INDIVIDUAL_ESPECIAL = 11
_MONTO_LIMITE_ESPECIAL          = Decimal("10000.00")


def obtener_seguro_por_id(id_tipo_seguro: int) -> TipoSeguro:
    if id_tipo_seguro not in TABLA_SEGUROS:
        raise KeyError(
            f"idTipoSeguro={id_tipo_seguro} no existe. "
            f"IDs válidos: {sorted(TABLA_SEGUROS.keys())}"
        )
    return TABLA_SEGUROS[id_tipo_seguro]


def obtener_seguro_por_nombre(nombre: str) -> TipoSeguro:
    nombre_norm = nombre.strip().upper()
    for s in TABLA_SEGUROS.values():
        if s.nombre.upper() == nombre_norm:
            return s
    coincidencias = [s for s in TABLA_SEGUROS.values() if nombre_norm in s.nombre.upper()]
    if len(coincidencias) == 1:
        return coincidencias[0]
    if len(coincidencias) > 1:
        nombres = ", ".join(f'"{s.nombre}"' for s in coincidencias)
        raise ValueError(f'Nombre ambiguo "{nombre}". Coincide con: {nombres}')
    raise ValueError(
        f'Seguro "{nombre}" no encontrado.\n'
        f'Nombres válidos:\n' +
        "\n".join(f'  [{s.id_tipo_seguro}] {s.nombre}' for s in TABLA_SEGUROS.values())
    )


def resolver_seguro(valor) -> Optional[int]:
    if valor is None:
        return None
    if isinstance(valor, int):
        if valor == 0:
            return None
        obtener_seguro_por_id(valor)
        return valor
    if isinstance(valor, str):
        v = valor.strip()
        if v.lower() in ("0", "", "ninguno", "ninguna", "none", "no", "sin plan",
                         "sin seguro", "sin desgravamen", "0.00"):
            return None
        try:
            id_int = int(v)
            return resolver_seguro(id_int)
        except ValueError:
            pass
        return obtener_seguro_por_nombre(v).id_tipo_seguro
    raise TypeError(f"Tipo inesperado para resolver_seguro: {type(valor)}")


def listar_seguros():
    print("─" * 80)
    print(f"  {'ID':>4}  {'Nombre':<52}  {'nValor (Prima)':>14}  {'Tipo'}")
    print("─" * 80)
    for s in sorted(TABLA_SEGUROS.values(), key=lambda x: x.id_tipo_seguro):
        if s.id_tipo_valor == 1:
            tipo = f"{s.n_valor}% × Saldo/100"
        else:
            tipo = f"S/{s.n_valor}/mes (fija)"
        print(f"  {s.id_tipo_seguro:>4}  {s.nombre:<52}  {float(s.n_valor):>14.6f}  {tipo}")
    print("─" * 80)


def calcular_prima_seguro(seguro: TipoSeguro, sal_cap: Decimal, dias: int) -> Decimal:
    if seguro.id_tipo_valor == 1:
        factor = _d(dias) / _d(30)
        return _r2(sal_cap * seguro.n_valor * factor)
    elif seguro.id_tipo_valor == 2:
        return _r2(seguro.n_valor)
    return Decimal("0.00")


# ══════════════════════════════════════════════════════════════════════
# 2. ESTRUCTURAS DE DATOS
# ══════════════════════════════════════════════════════════════════════

@dataclass
class CuotaPlan:
    cuota: int
    fecha: date
    dias: int
    dias_acu: int
    frc: Decimal
    sal_cap: Decimal
    capital: Decimal
    interes: Decimal
    seguro_desgravamen: Decimal
    prima_plan: Decimal
    seg_comi: Decimal
    imp_cuota: Decimal


@dataclass
class ParametrosPlanPago:
    monto_desembolso: float
    tasa_interes_anual: float
    fecha_desembolso: date
    num_cuotas: int
    dias_gracia: int
    tipo_periodo: int
    dia_fec_pago: int
    fecha_primera_cuota: date
    nro_cuotas_gracia: int = 0
    forma_calculo_tasa: int = 1
    id_seguro_desgravamen: int = 9
    id_plan_seguro: Optional[int] = None
    max_dias_primera_cuota: int = 30
    n_dec_redon_calc_ppg: int = 1


# ══════════════════════════════════════════════════════════════════════
# 3. PARSER DE TEXTO
# ══════════════════════════════════════════════════════════════════════

def _parsear_fecha(s: str) -> date:
    """Acepta DD/MM/YYYY o YYYY-MM-DD."""
    s = s.strip()
    if "/" in s:
        partes = s.split("/")
        if len(partes[0]) == 4:
            return date(int(partes[0]), int(partes[1]), int(partes[2]))
        return date(int(partes[2]), int(partes[1]), int(partes[0]))
    if "-" in s:
        partes = s.split("-")
        if len(partes[0]) == 4:
            return date(int(partes[0]), int(partes[1]), int(partes[2]))
        return date(int(partes[2]), int(partes[1]), int(partes[0]))
    raise ValueError(f'Formato de fecha no reconocido: "{s}"')


def _parsear_tipo_periodo(s: str) -> int:
    """Convierte 'Fecha Fija' / 'Periodo Fijo' / '1' / '2' → int."""
    s = s.strip().lower()
    if s in ("1", "fecha fija", "fecha_fija", "fechafija"):
        return 1
    if s in ("2", "periodo fijo", "periodo_fijo", "periodofijo"):
        return 2
    raise ValueError(
        f'tipo_periodo "{s}" no reconocido. '
        f'Use "Fecha Fija", "Periodo Fijo", 1 o 2.'
    )


# ══════════════════════════════════════════════════════════════════════
# 4. UTILIDADES
# ══════════════════════════════════════════════════════════════════════

def _calcular_ted(tasa_anual: float, forma: int) -> Decimal:
    uno = Decimal(1)
    tea = _d(tasa_anual)
    if forma == 1:
        return (uno + tea) ** (uno / Decimal(360)) - uno
    elif forma == 2:
        return (uno + tea) ** (uno / Decimal(30)) - uno
    raise ValueError(f"forma_calculo_tasa={forma} inválido.")


def _fecha_valida(dia: int, mes: int, anio: int) -> date:
    d = dia
    while d >= 1:
        try:
            return date(anio, mes, d)
        except ValueError:
            d -= 1
    raise ValueError(f"Fecha inválida: {dia}/{mes}/{anio}")


def calcular_dias_gracia_extra(
    fecha_desembolso: date,
    fecha_primera_cuota: date,
    max_dias: int = 30
) -> int:
    dias = (fecha_primera_cuota - fecha_desembolso).days
    if dias <= max_dias:
        return 0
    gracia = 0
    while (dias - gracia) > max_dias:
        gracia += 1
    return gracia


# ══════════════════════════════════════════════════════════════════════
# 5. CRONOGRAMA DE FECHAS
# ══════════════════════════════════════════════════════════════════════

def _cronograma_fecha_fija(params: ParametrosPlanPago, gracia_extra: int):
    """
    tipo_periodo = 1 — Fecha Fija.
    Cada cuota vence el mismo día del mes (dia_fec_pago).
    gracia_extra se suma a dias_acu de la cuota 1 cuando la primera
    cuota supera max_dias_primera_cuota.
    """
    fechas = []
    dias_acu = 0
    for i in range(1, params.num_cuotas + 1):
        if i == 1:
            fecha_cuota = params.fecha_primera_cuota
            dias = (fecha_cuota - params.fecha_desembolso).days
            dias_acu += dias + gracia_extra
        else:
            fa = fechas[-1][0]
            nm = fa.month + 1
            na = fa.year
            if nm > 12:
                nm = 1; na += 1
            fecha_cuota = _fecha_valida(params.dia_fec_pago, nm, na)
            dias = (fecha_cuota - fa).days
            dias_acu += dias
        fechas.append((fecha_cuota, dias, dias_acu))
    return fechas


def _cronograma_periodo_fijo(params: ParametrosPlanPago):
    """
    tipo_periodo = 2 — Periodo Fijo.

    Equivalente exacto al bloque #region Periodo Fijo del C#:

        if (i == 1):
            nDiaAcumul += nDiaGraCta + nDiaFecPag
            dFecNewCuo  = dFecPrimeraCuota          ← viene del parámetro
            dias        = nDiaFecPag + nDiaGraCta
            dias_acu    = nDiaAcumul

        else:
            nDiaAcumul += nDiaFecPag
            dFecNewCuo  = dFecNewCuo.AddDays(nDiaFecPag)
            dias        = (dFecNewCuo - fechaAnterior).days   → siempre == nDiaFecPag
            dias_acu    = nDiaAcumul

    NOTAS vs. Fecha Fija:
      • dia_fec_pago actúa como CANTIDAD DE DÍAS entre cuotas (no día del mes).
      • gracia_extra NO se aplica: los días son fijos por definición del período.
      • dias_gracia sí se suma en la cuota 1 (igual que en C#).
    """
    fechas  = []
    dias_acu = 0
    fecha_cuota = params.fecha_primera_cuota          # viene del parámetro, igual que C#

    for i in range(1, params.num_cuotas + 1):
        if i == 1:
            # C#: fila["dias"] = nDiaFecPag + nDiaGraCta
            dias      = params.dia_fec_pago + params.dias_gracia
            dias_acu += params.dia_fec_pago + params.dias_gracia
        else:
            # C#: dFecNewCuo = dFecNewCuo.AddDays(nDiaFecPag)
            #     fila["dias"] = (dFecNewCuo - fechaAnterior).Days  → == nDiaFecPag
            fecha_cuota  = fecha_cuota + timedelta(days=params.dia_fec_pago)
            dias          = params.dia_fec_pago          # siempre igual a dia_fec_pago
            dias_acu     += params.dia_fec_pago

        fechas.append((fecha_cuota, dias, dias_acu))

    return fechas


# ══════════════════════════════════════════════════════════════════════
# 6. FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

def generar_plan_pagos(params: ParametrosPlanPago) -> list[CuotaPlan]:
    monto_d = _d(params.monto_desembolso)
    if (params.id_seguro_desgravamen == _ID_DESGRAV_INDIVIDUAL
            and monto_d > _MONTO_LIMITE_ESPECIAL):
        seg_especial = obtener_seguro_por_id(_ID_DESGRAV_INDIVIDUAL_ESPECIAL)
        print(
            f"  [AUTO] Monto S/{params.monto_desembolso:,.2f} > S/10,000 → "
            f"Desgravamen cambiado a [{seg_especial.id_tipo_seguro}] "
            f"{seg_especial.nombre} (prima={seg_especial.n_valor})"
        )
        params.id_seguro_desgravamen = _ID_DESGRAV_INDIVIDUAL_ESPECIAL

    TED   = _calcular_ted(params.tasa_interes_anual, params.forma_calculo_tasa)
    MONTO = _d(params.monto_desembolso)
    DEC_CUOTA = params.n_dec_redon_calc_ppg

    seg_desgrav_obj = obtener_seguro_por_id(params.id_seguro_desgravamen)
    plan_obj = (
        obtener_seguro_por_id(params.id_plan_seguro)
        if params.id_plan_seguro is not None else None
    )

    # ── Cronograma de fechas ──────────────────────────────────────────
    if params.tipo_periodo == 1:
        # Fecha Fija: gracia_extra aplica cuando 1ra cuota supera max_dias
        gracia_extra = calcular_dias_gracia_extra(
            params.fecha_desembolso,
            params.fecha_primera_cuota,
            params.max_dias_primera_cuota
        )
        if gracia_extra > 0:
            print(f"  [GRACIA] 1ra cuota supera {params.max_dias_primera_cuota} días → "
                  f"{gracia_extra} día(s) de gracia extra.\n")
        cronograma = _cronograma_fecha_fija(params, gracia_extra)

    elif params.tipo_periodo == 2:
        # Periodo Fijo: días son constantes; gracia_extra NO aplica
        # (en C# no existe el concepto de gracia_extra para este tipo)
        cronograma = _cronograma_periodo_fijo(params)

    else:
        raise ValueError("tipo_periodo debe ser 1 (Fecha Fija) o 2 (Periodo Fijo).")

    # ── Factores de recuperación de capital ──────────────────────────
    frcs: list[Decimal] = []
    fac_acumul = Decimal(0)
    for (_, __, da) in cronograma:
        frc = Decimal(1) / (Decimal(1) + TED) ** da
        frcs.append(frc)
        fac_acumul += frc

    cuota_base = _r2(MONTO / fac_acumul)

    # ── Algoritmo iterativo de convergencia ──────────────────────────
    MAX_ITER    = 20
    ERR_MAX     = _d("0.09") * params.num_cuotas
    cuota_iter  = cuota_base
    mejor_plan: list[CuotaPlan] = []
    menor_diff  = _d("9999999")
    potenc_dos  = Decimal(0)
    razon_busq  = Decimal(0)
    flag_factor = False
    itera_true  = 0
    ind_sal_ite = False
    num_sal_ite = 0

    for iteracion in range(MAX_ITER):
        plan_iter: list[CuotaPlan] = []
        saldo = _r2(MONTO)

        for idx, (fecha, dias, dias_acu_i) in enumerate(cronograma):
            num_cuota = idx + 1
            frc = frcs[idx]

            cuota_redond = _round(cuota_iter, DEC_CUOTA)
            interes = _r2(saldo * ((Decimal(1) + TED) ** dias - Decimal(1)))
            seg_desgrav = calcular_prima_seguro(seg_desgrav_obj, saldo, dias)

            prima_plan = (
                calcular_prima_seguro(plan_obj, saldo, dias)
                if plan_obj is not None else Decimal("0.00")
            )

            if num_cuota == 1 and params.dias_gracia > 0 and plan_obj is not None:
                prima_plan += _r2(plan_obj.n_valor / _d(30) * _d(params.dias_gracia))

            seg_comi = _r2(seg_desgrav + prima_plan)

            if params.nro_cuotas_gracia >= num_cuota:
                capital = Decimal("0.00")
            else:
                capital = _r2(cuota_redond - interes - seg_comi)

            imp_cuota = _r2(capital + interes + seg_comi)

            plan_iter.append(CuotaPlan(
                cuota=num_cuota, fecha=fecha, dias=dias, dias_acu=dias_acu_i,
                frc=frc, sal_cap=_r2(saldo), capital=capital, interes=interes,
                seguro_desgravamen=seg_desgrav, prima_plan=prima_plan,
                seg_comi=seg_comi, imp_cuota=imp_cuota,
            ))
            saldo = saldo - capital

        saldo_final = _r2(saldo)
        diff = abs(plan_iter[-1].sal_cap - plan_iter[-1].capital)
        if diff <= menor_diff:
            menor_diff = diff
            mejor_plan = list(plan_iter)

        if abs(saldo_final) <= ERR_MAX:
            break

        if itera_true > 0:
            if saldo_final < 0:
                potenc_dos  = potenc_dos / 2
                cuota_iter  = cuota_base - razon_busq
                flag_factor = True
            else:
                if not flag_factor:
                    potenc_dos *= 2
        else:
            potenc_dos = Decimal(2)

        itera_true += 1
        razon_busq  = _r10(saldo_final * potenc_dos / _d(cronograma[-1][2]))
        cuota_iter  = cuota_iter + razon_busq

        if razon_busq == 0:
            if not ind_sal_ite:
                ind_sal_ite = True
                num_sal_ite = iteracion
            cuota_iter += _d("0.01")
        if ind_sal_ite and iteracion == num_sal_ite + 1:
            break

    # ── Ajuste exacto de última cuota (igual que C#) ──────────────────
    if mejor_plan:
        ult = mejor_plan[-1]
        s   = ult.sal_cap
        i   = _r2(s * ((Decimal(1) + TED) ** ult.dias - Decimal(1)))
        c   = _r2(s)
        sd  = calcular_prima_seguro(seg_desgrav_obj, s, ult.dias)
        pp  = (calcular_prima_seguro(plan_obj, s, ult.dias) if plan_obj else Decimal("0.00"))
        sc  = _r2(sd + pp)
        imp = _r2(c + i + sc)
        mejor_plan[-1] = CuotaPlan(
            cuota=ult.cuota, fecha=ult.fecha, dias=ult.dias, dias_acu=ult.dias_acu,
            frc=ult.frc, sal_cap=s, capital=c, interes=i,
            seguro_desgravamen=sd, prima_plan=pp, seg_comi=sc, imp_cuota=imp,
        )

    return mejor_plan


# ══════════════════════════════════════════════════════════════════════
# 7. IMPRIMIR PLAN DE PAGOS
# ══════════════════════════════════════════════════════════════════════

def imprimir_plan_pagos(plan: list[CuotaPlan], params: ParametrosPlanPago):
    seg_obj  = obtener_seguro_por_id(params.id_seguro_desgravamen)
    plan_obj = (obtener_seguro_por_id(params.id_plan_seguro)
                if params.id_plan_seguro is not None else None)
    tipo_str = "Fecha Fija" if params.tipo_periodo == 1 else "Periodo Fijo"
    tea_pct  = params.tasa_interes_anual * 100
    W = 138
    print("=" * W)
    print("  CAJA LOS ANDES  —  PLAN DE PAGOS")
    print(f"  Monto: S/ {params.monto_desembolso:,.2f}   TEA: {tea_pct:.4f}%   "
          f"Cuotas: {params.num_cuotas}   Tipo: {tipo_str} "
          f"({'día ' + str(params.dia_fec_pago) if params.tipo_periodo == 1 else str(params.dia_fec_pago) + ' días'})")
    print(f"  Desembolso: {params.fecha_desembolso:%d/%m/%Y}   "
          f"1ra cuota: {params.fecha_primera_cuota:%d/%m/%Y}   "
          f"nDecRedonCalcPpg: {params.n_dec_redon_calc_ppg}")
    print(f"  Desgravamen: [{seg_obj.id_tipo_seguro}] {seg_obj.nombre}  "
          f"(Prima={seg_obj.n_valor})  →  Fórmula: Saldo × Tasa × (días/30)")
    if plan_obj:
        print(f"  Plan seguro: [{plan_obj.id_tipo_seguro}] {plan_obj.nombre}  "
              f"(S/{plan_obj.n_valor}/mes)")
    else:
        print("  Plan seguro: Sin plan adicional")
    print("=" * W)

    hdr = ("{:>5}  {:<12}  {:>5}  {:>10}  {:>9}  {:>8}  "
           "{:>11}  {:>11}  {:>9}  {:>11}")
    print(hdr.format("Cuota", "Fecha Pago", "Días", "Sal. Cap.",
                     "Capital", "Interés", "Seg.Desgrav", "Prima Plan",
                     "Seg|Comi", "Monto Cuota"))
    print("-" * W)

    tot_cap = tot_int = tot_sd = tot_pp = tot_sc = tot_imp = Decimal(0)
    rfmt = ("{:>5}  {:<12}  {:>5}  {:>10}  {:>9}  {:>8}  "
            "{:>11}  {:>11}  {:>9}  {:>11}")

    for c in plan:
        print(rfmt.format(
            c.cuota, c.fecha.strftime("%d/%m/%Y"), c.dias,
            f"{c.sal_cap:.2f}", f"{c.capital:.2f}", f"{c.interes:.2f}",
            f"{c.seguro_desgravamen:.2f}", f"{c.prima_plan:.2f}",
            f"{c.seg_comi:.2f}", f"{c.imp_cuota:.2f}",
        ))
        tot_cap += c.capital; tot_int += c.interes
        tot_sd  += c.seguro_desgravamen; tot_pp += c.prima_plan
        tot_sc  += c.seg_comi; tot_imp += c.imp_cuota

    print("-" * W)
    print(hdr.format("TOTAL", "", "", "",
                     f"{tot_cap:.2f}", f"{tot_int:.2f}",
                     f"{tot_sd:.2f}", f"{tot_pp:.2f}",
                     f"{tot_sc:.2f}", f"{tot_imp:.2f}"))
    print("=" * W)


# ══════════════════════════════════════════════════════════════════════
# 8. CONVERSIÓN A JSON
# ══════════════════════════════════════════════════════════════════════

def _plan_a_json(plan: list[CuotaPlan]) -> list[dict]:
    result = []
    tot_cap = tot_int = tot_sd = tot_pp = tot_sc = tot_imp = Decimal(0)

    for c in plan:
        result.append({
            "cuota":      c.cuota,
            "fechaPago":  c.fecha.strftime("%d/%m/%Y"),
            "dias":       c.dias,
            "salCap":     float(c.sal_cap),
            "capital":    float(c.capital),
            "interes":    float(c.interes),
            "segDesgrav": float(c.seguro_desgravamen),
            "primaPlan":  float(c.prima_plan),
            "segComi":    float(c.seg_comi),
            "montoCuota": float(c.imp_cuota),
        })
        tot_cap += c.capital;  tot_int += c.interes
        tot_sd  += c.seguro_desgravamen;  tot_pp += c.prima_plan
        tot_sc  += c.seg_comi;  tot_imp += c.imp_cuota

    result.append({
        "cuota":      "TOTAL",
        "fechaPago":  None,
        "dias":       None,
        "salCap":     None,
        "capital":    float(_r2(tot_cap)),
        "interes":    float(_r2(tot_int)),
        "segDesgrav": float(_r2(tot_sd)),
        "primaPlan":  float(_r2(tot_pp)),
        "segComi":    float(_r2(tot_sc)),
        "montoCuota": float(_r2(tot_imp)),
    })
    return result


# ══════════════════════════════════════════════════════════════════════
# 9. planpagogenerado  — API pública
# ══════════════════════════════════════════════════════════════════════

def planpagogenerado(
    monto_desembolso:        float,
    tasa_interes_anual:      float,
    fecha_desembolso:        str | date,
    num_cuotas:              int,
    dia_fec_pago:            int,
    fecha_primera_cuota:     str | date,
    tipo_periodo:            str | int   = "Fecha Fija",
    dias_gracia:             int         = 0,
    nro_cuotas_gracia:       int         = 0,
    forma_calculo_tasa:      int         = 1,
    cseguro_desgravamen:     str | int   = "SEGURO DESGRAVAMEN INDIVIDUAL",
    cplan_seguro:            str | int   = "NINGUNO",
    max_dias_primera_cuota:  int         = 30,
    n_dec_redon_calc_ppg:    int         = 1,
    cuotasgracia:            int         = 0,
) -> list[dict]:
    # Normalizar fechas
    if isinstance(fecha_desembolso, str):
        fecha_desembolso = _parsear_fecha(fecha_desembolso)
    if isinstance(fecha_primera_cuota, str):
        fecha_primera_cuota = _parsear_fecha(fecha_primera_cuota)

    # Normalizar tipo_periodo
    if isinstance(tipo_periodo, str):
        tipo_periodo = _parsear_tipo_periodo(tipo_periodo)

    # Normalizar tasa (41.99 → 0.4199, ya 0.4199 → se deja igual)
    tasa = tasa_interes_anual / 100.0 if tasa_interes_anual > 1 else tasa_interes_anual

    # Resolver seguros
    if cseguro_desgravamen is None:
        id_seg = _ID_DESGRAV_INDIVIDUAL
    else:
        resuelto = resolver_seguro(cseguro_desgravamen)
        id_seg = resuelto if resuelto is not None else 8

    id_plan = resolver_seguro(cplan_seguro)

    # Regla especial INDIVIDUAL → ESPECIAL si monto > 10,000
    monto_d = _d(monto_desembolso)
    if id_seg == _ID_DESGRAV_INDIVIDUAL and monto_d > _MONTO_LIMITE_ESPECIAL:
        seg_especial = obtener_seguro_por_id(_ID_DESGRAV_INDIVIDUAL_ESPECIAL)
        print(
            f"  [AUTO] Monto S/{monto_desembolso:,.2f} > S/10,000 → "
            f"Desgravamen cambiado a [{seg_especial.id_tipo_seguro}] "
            f"{seg_especial.nombre} (prima={seg_especial.n_valor})"
        )
        id_seg = _ID_DESGRAV_INDIVIDUAL_ESPECIAL

    p = ParametrosPlanPago(
        monto_desembolso       = monto_desembolso,
        tasa_interes_anual     = tasa,
        fecha_desembolso       = fecha_desembolso,
        num_cuotas             = num_cuotas,
        dias_gracia            = dias_gracia,
        tipo_periodo           = tipo_periodo,
        dia_fec_pago           = dia_fec_pago,
        fecha_primera_cuota    = fecha_primera_cuota,
        nro_cuotas_gracia      = nro_cuotas_gracia,
        forma_calculo_tasa     = forma_calculo_tasa,
        id_seguro_desgravamen  = id_seg,
        id_plan_seguro         = id_plan,
        max_dias_primera_cuota = max_dias_primera_cuota,
        n_dec_redon_calc_ppg   = n_dec_redon_calc_ppg,
    )

    plan = generar_plan_pagos(p)
    imprimir_plan_pagos(plan, p)
    return _plan_a_json(plan)


# ══════════════════════════════════════════════════════════════════════
# 10. CLASE CalculoPlanPago
# ══════════════════════════════════════════════════════════════════════

class CalculoPlanPago:
    @staticmethod
    def planpagogenerado(
        monto_desembolso,
        tasa_interes_anual,
        fecha_desembolso,
        num_cuotas,
        dia_fec_pago,
        fecha_primera_cuota,
        tipo_periodo            = "Fecha Fija",
        dias_gracia: int        = 0,
        nro_cuotas_gracia: int  = 0,
        forma_calculo_tasa: int = 1,
        cseguro_desgravamen     = "SEGURO DESGRAVAMEN INDIVIDUAL",
        cplan_seguro            = "NINGUNO",
        max_dias_primera_cuota: int = 30,
        n_dec_redon_calc_ppg: int   = 1,
        cuotasgracia: int           = 0,
    ) -> list[dict]:
        return planpagogenerado(
            monto_desembolso       = monto_desembolso,
            tasa_interes_anual     = tasa_interes_anual,
            fecha_desembolso       = fecha_desembolso,
            num_cuotas             = num_cuotas,
            dia_fec_pago           = dia_fec_pago,
            fecha_primera_cuota    = fecha_primera_cuota,
            tipo_periodo           = tipo_periodo,
            dias_gracia            = dias_gracia,
            nro_cuotas_gracia      = nro_cuotas_gracia,
            forma_calculo_tasa     = forma_calculo_tasa,
            cseguro_desgravamen    = cseguro_desgravamen,
            cplan_seguro           = cplan_seguro,
            max_dias_primera_cuota = max_dias_primera_cuota,
            n_dec_redon_calc_ppg   = n_dec_redon_calc_ppg,
            cuotasgracia           = cuotasgracia,
        )

    @staticmethod
    def imprimirJson(dataPlanPago: dict):
        jsonPlanPago = CalculoPlanPago.planpagogenerado(
            monto_desembolso        = dataPlanPago["monto_desembolso"],
            tasa_interes_anual      = dataPlanPago["tasa_interes_anual"],
            fecha_desembolso        = dataPlanPago["fecha_desembolso"],
            num_cuotas              = dataPlanPago["num_cuotas"],
            dia_fec_pago            = dataPlanPago["dia_fec_pago"],
            fecha_primera_cuota     = dataPlanPago["fecha_primera_cuota"],
            tipo_periodo            = dataPlanPago.get("tipo_periodo",            "Fecha Fija"),
            dias_gracia             = dataPlanPago.get("dias_gracia",             0),
            nro_cuotas_gracia       = dataPlanPago.get("nro_cuotas_gracia",       0),
            forma_calculo_tasa      = dataPlanPago.get("forma_calculo_tasa",      1),
            cseguro_desgravamen     = dataPlanPago.get("cseguro_desgravamen",     "SEGURO DESGRAVAMEN INDIVIDUAL"),
            cplan_seguro            = dataPlanPago.get("cplan_seguro",            "NINGUNO"),
            max_dias_primera_cuota  = dataPlanPago.get("max_dias_primera_cuota",  30),
            n_dec_redon_calc_ppg    = dataPlanPago.get("n_dec_redon_calc_ppg",    1),
            cuotasgracia            = dataPlanPago.get("cuotasgracia",            0),
        )
        print()
        print("  JSON retornado por planpagogenerado():")
        print(json.dumps(jsonPlanPago, indent=2, ensure_ascii=False))
        return jsonPlanPago


# ══════════════════════════════════════════════════════════════════════
# 11. EJECUCIÓN DIRECTA — pruebas de ambos tipos
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # ── CASO 1: Fecha Fija (igual al original) ────────────────────────
    print("  CASO 1 — FECHA FIJA")
    jsonFF = planpagogenerado(
        monto_desembolso        = 1001.00,
        tasa_interes_anual      = 59.99,
        fecha_desembolso        = "29/01/2026",
        num_cuotas              = 12,
        tipo_periodo            = "Fecha Fija",
        dia_fec_pago            = 24,
        fecha_primera_cuota     = "24/03/2026",
        cseguro_desgravamen     = "SEGURO DESGRAVAMEN INDIVIDUAL",
        cplan_seguro            = "PLAN 1: A. EDUCATIVA",
        max_dias_primera_cuota  = 54,
    )

    print("  CASO 2 — PERIODO FIJO (30 días entre cuotas)")
    jsonPF = planpagogenerado(
        monto_desembolso        = 3001.00,
        tasa_interes_anual      = 77.99,
        fecha_desembolso        = "29/01/2026",
        num_cuotas              = 12,
        tipo_periodo            = "Periodo Fijo",   # ← NUEVO
        dia_fec_pago            = 30,               # ← días entre cuotas (no día del mes)
        fecha_primera_cuota     = "28/02/2026",     # desembolso + 30 días
        cseguro_desgravamen     = "SEGURO DESGRAVAMEN INDIVIDUAL",
        cplan_seguro            = "NINGUNO",
    )

    print("\n  JSON CASO 2 — PERIODO FIJO:")
    #print(json.dumps(jsonPF, indent=2, ensure_ascii=False))

  