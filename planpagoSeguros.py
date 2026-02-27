"""
╔══════════════════════════════════════════════════════════════════════╗
║          PLAN DE PAGOS - CAJA LOS ANDES                             ║
║          Cuotas Constantes (Sistema Francés)                        ║
╠══════════════════════════════════════════════════════════════════════╣
║  TABLA DE SEGUROS:                                                   ║
║  idTipoValor=1 → tasa directa proporcional a días                   ║
║                  seguro = sal_cap × nValor × (dias/30)              ║
║  idTipoValor=2 → prima mensual fija en soles, proporcional a días   ║
║                  seguro = nValor × (dias/30)                        ║
║                                                                      ║
║  COLUMNA Seg|Comi = desgravamen + prima_plan_seleccionado           ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional
import math


# ══════════════════════════════════════════════════════════════════════
# 1. TABLA DE SEGUROS (cargada desde BD o configuración)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class TipoSeguro:
    """
    Un registro de la tabla de tipos de seguro.

    idTipoValor=1 → nValor es TASA directa (como desgravamen 0.001650)
                    cálculo: sal_cap × nValor × (dias / 30)

    idTipoValor=2 → nValor es PRIMA FIJA mensual en soles (ej. 2.50 S/)
                    cálculo: nValor × (dias / 30)
                    (proporcional a días igual que el resto)
    """
    id_tipo_seguro: int
    nombre: str
    n_valor: float
    id_tipo_valor: int   # 1 = tasa sobre saldo | 2 = prima fija en soles


# Tabla completa cargada desde la BD (puedes modificar o cargar dinámicamente)
TABLA_SEGUROS: dict[int, TipoSeguro] = {
    1:  TipoSeguro(1,  "SEGURO MULTIRIESGO",                               0.001150, 1),
    2:  TipoSeguro(2,  "SEGURO VIDA",                                       5.000000, 2),
    3:  TipoSeguro(4,  "SEGURO ONCOLÓGICO",                                 5.000000, 2),
    4:  TipoSeguro(5,  "PLAN 1: A. EDUCATIVA",                              2.500000, 2),
    5:  TipoSeguro(6,  "PLAN 2: A. EDUCATIVA + A. SALUD",                   5.750000, 2),
    6:  TipoSeguro(7,  "PLAN 3: A. EDUCATIVA + A. SALUD + S. INCAPACIDAD",  8.500000, 2),
    7:  TipoSeguro(8,  "SIN SEGURO DESGRAVAMEN",                            0.000000, 1),
    8:  TipoSeguro(9,  "SEGURO DESGRAVAMEN INDIVIDUAL",                     0.001650, 1),
    9:  TipoSeguro(10, "SEGURO DESGRAVAMEN CONYUGAL",                       0.002050, 1),
    10: TipoSeguro(11, "SEGURO DESGRAVAMEN INDIVIDUAL ESPECIAL",            0.001450, 1),
    11: TipoSeguro(12, "SEGURO DESGRAVAMEN DEVOLUCIÓN",                     0.002340, 1),
}

# Índice rápido por id_tipo_seguro real (columna idTipoSeguro de la BD)
_SEGUROS_POR_ID: dict[int, TipoSeguro] = {
    s.id_tipo_seguro: s for s in TABLA_SEGUROS.values()
}


def obtener_seguro_por_id(id_tipo_seguro: int) -> TipoSeguro:
    """
    Retorna el TipoSeguro correspondiente al idTipoSeguro de la BD.

    Uso:
        seg = obtener_seguro_por_id(5)   # PLAN 1: A. EDUCATIVA
        print(seg.nombre)                # "PLAN 1: A. EDUCATIVA"
        print(seg.n_valor)               # 2.5
        print(seg.id_tipo_valor)         # 2 (prima fija)

    Lanza KeyError si el id no existe.
    """
    if id_tipo_seguro not in _SEGUROS_POR_ID:
        ids_validos = sorted(_SEGUROS_POR_ID.keys())
        raise KeyError(
            f"idTipoSeguro={id_tipo_seguro} no encontrado. "
            f"IDs válidos: {ids_validos}"
        )
    return _SEGUROS_POR_ID[id_tipo_seguro]


def listar_seguros():
    """Imprime todos los seguros disponibles (útil para selección interactiva)."""
    print("─" * 70)
    print(f"  {'ID':>4}  {'Nombre':<50}  {'nValor':>8}  {'Tipo':>4}")
    print("─" * 70)
    for seg in sorted(_SEGUROS_POR_ID.values(), key=lambda x: x.id_tipo_seguro):
        tipo_str = "Tasa" if seg.id_tipo_valor == 1 else "Prima"
        print(f"  {seg.id_tipo_seguro:>4}  {seg.nombre:<50}  {seg.n_valor:>8.6f}  {tipo_str:>5}")
    print("─" * 70)


def calcular_prima_seguro(
    seguro: TipoSeguro,
    sal_cap: float,
    dias: int
) -> float:
    """
    Calcula el importe del seguro para una cuota.

    idTipoValor=1 (tasa sobre saldo):
        prima = round(sal_cap × nValor × dias/30, 2)

    idTipoValor=2 (prima fija mensual en soles):
        prima = round(nValor × dias/30, 2)

    En ambos casos es PROPORCIONAL a los días de la cuota:
      • 28 días → × 28/30  (paga menos)
      • 30 días → × 30/30  (paga exacto)
      • 31 días → × 31/30  (paga un poco más)
    """
    factor_dias = dias / 30.0
    if seguro.id_tipo_valor == 1:
        # Tasa sobre saldo capital
        return round(sal_cap * seguro.n_valor * factor_dias, 2)
    elif seguro.id_tipo_valor == 2:
        # Prima fija mensual en soles
        return round(seguro.n_valor * factor_dias, 2)
    else:
        return 0.0


# ══════════════════════════════════════════════════════════════════════
# 2. ESTRUCTURAS DE DATOS DEL PLAN DE PAGOS
# ══════════════════════════════════════════════════════════════════════

@dataclass
class CuotaPlan:
    """Una fila completa del plan de pagos."""
    cuota: int
    fecha: date
    dias: int
    dias_acu: int
    frc: float
    sal_cap: float
    capital: float
    interes: float
    seguro_desgravamen: float   # importe del seguro desgravamen
    prima_plan: float           # importe del plan opcional (0 si no aplica)
    seg_comi: float             # = seguro_desgravamen + prima_plan (columna Seg|Comi)
    imp_cuota: float            # capital + interés + seg_comi


@dataclass
class ParametrosPlanPago:
    """
    Parámetros de entrada para generar el plan de pagos.

    Campos clave de seguros
    ──────────────────────
    id_seguro_desgravamen   : idTipoSeguro del desgravamen a aplicar.
                              Usar 9  → DESGRAVAMEN INDIVIDUAL (0.1650%)
                              Usar 10 → DESGRAVAMEN CONYUGAL   (0.2050%)
                              Usar 8  → SIN DESGRAVAMEN        (0.0000)
    id_plan_seguro          : idTipoSeguro del plan opcional.
                              Usar 5  → PLAN 1: A. EDUCATIVA   (+2.50 S/mes)
                              Usar 6  → PLAN 2: + A. SALUD     (+5.75 S/mes)
                              Usar 7  → PLAN 3: + S. INCAP.    (+8.50 S/mes)
                              Usar None → sin plan adicional
    """
    monto_desembolso: float
    tasa_interes_anual: float
    fecha_desembolso: date
    num_cuotas: int
    dias_gracia: int
    tipo_periodo: int               # 1 = Fecha Fija | 2 = Periodo Fijo
    dia_fec_pago: int
    fecha_primera_cuota: date
    nro_cuotas_gracia: int = 0
    forma_calculo_tasa: int = 1     # 1=base 360 | 2=base 30
    id_seguro_desgravamen: int = 9  # default: DESGRAVAMEN INDIVIDUAL
    id_plan_seguro: Optional[int] = None  # None = sin plan adicional
    max_dias_primera_cuota: int = 30


# ══════════════════════════════════════════════════════════════════════
# 3. UTILIDADES
# ══════════════════════════════════════════════════════════════════════

def calcular_ted(tasa_anual: float, forma: int) -> float:
    if forma == 1:
        return math.pow(1.0 + tasa_anual, 1.0 / 360.0) - 1.0
    elif forma == 2:
        return math.pow(1.0 + tasa_anual, 1.0 / 30.0) - 1.0
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
# 4. CRONOGRAMA DE FECHAS
# ══════════════════════════════════════════════════════════════════════

def _cronograma_fecha_fija(params: ParametrosPlanPago, gracia_extra: int):
    fechas = []
    dias_acu = 0
    for i in range(1, params.num_cuotas + 1):
        if i == 1:
            fecha_cuota = params.fecha_primera_cuota
            dias = (fecha_cuota - params.fecha_desembolso).days
            dias_acu += dias + gracia_extra
        else:
            fecha_ant = fechas[-1][0]
            nuevo_mes = fecha_ant.month + 1
            nuevo_anio = fecha_ant.year
            if nuevo_mes > 12:
                nuevo_mes = 1
                nuevo_anio += 1
            fecha_cuota = _fecha_valida(params.dia_fec_pago, nuevo_mes, nuevo_anio)
            dias = (fecha_cuota - fecha_ant).days
            dias_acu += dias
        fechas.append((fecha_cuota, dias, dias_acu))
    return fechas


def _cronograma_periodo_fijo(params: ParametrosPlanPago, gracia_extra: int):
    fechas = []
    dias_acu = 0
    fecha_cuota = params.fecha_primera_cuota
    for i in range(1, params.num_cuotas + 1):
        if i == 1:
            dias = params.dia_fec_pago + params.dias_gracia
            dias_acu += params.dia_fec_pago + params.dias_gracia + gracia_extra
        else:
            dias = params.dia_fec_pago
            dias_acu += params.dia_fec_pago
            fecha_cuota = fecha_cuota + timedelta(days=params.dia_fec_pago)
        fechas.append((fecha_cuota, dias, dias_acu))
    return fechas


# ══════════════════════════════════════════════════════════════════════
# 5. FUNCIÓN PRINCIPAL: GENERAR PLAN DE PAGOS
# ══════════════════════════════════════════════════════════════════════

def generar_plan_pagos(params: ParametrosPlanPago) -> list[CuotaPlan]:
    """
    Genera el plan de pagos completo.

    Columna Seg|Comi de cada cuota:
        seg_comi = seguro_desgravamen + prima_plan

    La cuota_total constante incluye ambos seguros:
        cuota_total = capital + interés + seg_comi
        capital = cuota_total − interés − seg_comi
    """
    TED = calcular_ted(params.tasa_interes_anual, params.forma_calculo_tasa)
    DEC = 2

    # Cargar seguros seleccionados
    seg_desgrav_obj = obtener_seguro_por_id(params.id_seguro_desgravamen)
    plan_obj = (
        obtener_seguro_por_id(params.id_plan_seguro)
        if params.id_plan_seguro is not None
        else None
    )

    # Días de gracia automáticos
    gracia_extra = calcular_dias_gracia_extra(
        params.fecha_desembolso,
        params.fecha_primera_cuota,
        params.max_dias_primera_cuota
    )
    if gracia_extra > 0:
        print(f"  [GRACIA] 1ra cuota supera {params.max_dias_primera_cuota} días → "
              f"{gracia_extra} día(s) de gracia extra.\n")

    # Cronograma
    if params.tipo_periodo == 1:
        cronograma = _cronograma_fecha_fija(params, gracia_extra)
    elif params.tipo_periodo == 2:
        cronograma = _cronograma_periodo_fijo(params, gracia_extra)
    else:
        raise ValueError("tipo_periodo debe ser 1 o 2.")

    # FRC acumulado (cuota base sin seguros)
    frcs = []
    fac_acumul = 0.0
    for (_, __, da) in cronograma:
        frc = 1.0 / math.pow(1.0 + TED, da)
        frcs.append(frc)
        fac_acumul += frc

    cuota_base = round(params.monto_desembolso / fac_acumul, DEC)

    # ── Iteración bisección adaptativa ───────────────────────────────
    # cuota_iter = cuota_total (cap + int + desgravamen + plan)
    MAX_ITER    = 20
    ERR_MAX     = 0.09 * params.num_cuotas
    cuota_iter  = cuota_base
    mejor_plan: list[CuotaPlan] = []
    menor_diff  = 9_999_999.0
    potenc_dos  = 0.0
    razon_busq  = 0.0
    flag_factor = False
    itera_true  = 0
    ind_sal_ite = False
    num_sal_ite = 0

    for iteracion in range(MAX_ITER):
        plan_iter: list[CuotaPlan] = []
        saldo = round(params.monto_desembolso, DEC)

        for idx, (fecha, dias, dias_acu_i) in enumerate(cronograma):
            num_cuota    = idx + 1
            cuota_redond = round(cuota_iter, DEC)

            interes = round(saldo * (math.pow(1.0 + TED, dias) - 1.0), DEC)

            # Seguro desgravamen
            seg_desgrav = calcular_prima_seguro(seg_desgrav_obj, saldo, dias)

            # Prima del plan opcional
            prima_plan = (
                calcular_prima_seguro(plan_obj, saldo, dias)
                if plan_obj is not None else 0.0
            )

            # Total seguros (columna Seg|Comi)
            seg_comi = round(seg_desgrav + prima_plan, DEC)

            # Capital = cuota_total − interés − seg_comi
            if params.nro_cuotas_gracia >= num_cuota:
                capital = 0.0
            else:
                capital = round(cuota_redond - interes - seg_comi, DEC)

            imp_cuota = round(capital + interes + seg_comi, DEC)

            plan_iter.append(CuotaPlan(
                cuota               = num_cuota,
                fecha               = fecha,
                dias                = dias,
                dias_acu            = dias_acu_i,
                frc                 = frcs[idx],
                sal_cap             = round(saldo, DEC),
                capital             = round(capital, DEC),
                interes             = round(interes, DEC),
                seguro_desgravamen  = seg_desgrav,
                prima_plan          = prima_plan,
                seg_comi            = seg_comi,
                imp_cuota           = imp_cuota,
            ))

            saldo = saldo - capital

        saldo_final = round(saldo, DEC)
        diff = abs(plan_iter[-1].sal_cap - plan_iter[-1].capital)
        if diff <= menor_diff:
            menor_diff = diff
            mejor_plan = list(plan_iter)

        if abs(saldo_final) <= ERR_MAX:
            break

        # Ajuste bisección (idéntico al C# original)
        if itera_true > 0:
            if saldo_final < 0:
                potenc_dos  = potenc_dos / 2.0
                cuota_iter  = cuota_base - razon_busq
                flag_factor = True
            else:
                if not flag_factor:
                    potenc_dos *= 2.0
        else:
            potenc_dos = 2.0

        itera_true    += 1
        razon_busq     = round(saldo_final * potenc_dos / cronograma[-1][2], 10)
        cuota_iter     = cuota_iter + razon_busq

        if razon_busq == 0:
            if not ind_sal_ite:
                ind_sal_ite = True
                num_sal_ite = iteracion
            cuota_iter += 0.01
        if ind_sal_ite and iteracion == num_sal_ite + 1:
            break

    # Ajuste exacto última cuota
    if mejor_plan:
        ult         = mejor_plan[-1]
        saldo_ult   = ult.sal_cap
        interes_ult = round(saldo_ult * (math.pow(1.0 + TED, ult.dias) - 1.0), DEC)
        capital_ult = round(saldo_ult, DEC)
        seg_d_ult   = calcular_prima_seguro(seg_desgrav_obj, saldo_ult, ult.dias)
        prima_ult   = (
            calcular_prima_seguro(plan_obj, saldo_ult, ult.dias)
            if plan_obj is not None else 0.0
        )
        seg_comi_ult = round(seg_d_ult + prima_ult, DEC)
        imp_ult      = round(capital_ult + interes_ult + seg_comi_ult, DEC)

        mejor_plan[-1] = CuotaPlan(
            cuota               = ult.cuota,
            fecha               = ult.fecha,
            dias                = ult.dias,
            dias_acu            = ult.dias_acu,
            frc                 = ult.frc,
            sal_cap             = saldo_ult,
            capital             = capital_ult,
            interes             = interes_ult,
            seguro_desgravamen  = seg_d_ult,
            prima_plan          = prima_ult,
            seg_comi            = seg_comi_ult,
            imp_cuota           = imp_ult,
        )

    return mejor_plan


# ══════════════════════════════════════════════════════════════════════
# 6. IMPRIMIR PLAN DE PAGOS
# ══════════════════════════════════════════════════════════════════════

def imprimir_plan_pagos(plan: list[CuotaPlan], params: ParametrosPlanPago):
    """
    Imprime el plan de pagos en formato tabular.
    Columnas visibles:
      Cuota | Fecha Pago | Frecuencia | Sal.Cap | Capital | Interés |
      Seg.Desgrav | Prima Plan | Seg|Comi | Monto Cuota
    """
    seg_obj  = obtener_seguro_por_id(params.id_seguro_desgravamen)
    plan_obj = (
        obtener_seguro_por_id(params.id_plan_seguro)
        if params.id_plan_seguro is not None else None
    )
    tipo_str = "Fecha Fija" if params.tipo_periodo == 1 else "Periodo Fijo"
    tea_pct  = params.tasa_interes_anual * 100

    gracia_extra = calcular_dias_gracia_extra(
        params.fecha_desembolso,
        params.fecha_primera_cuota,
        params.max_dias_primera_cuota
    )

    W = 138
    print("=" * W)
    print("  CAJA LOS ANDES  —  PLAN DE PAGOS")
    print(f"  Monto              : S/ {params.monto_desembolso:,.2f}   |   "
          f"TEA: {tea_pct:.4f}%   |   N° Cuotas: {params.num_cuotas}")
    print(f"  Desembolso         : {params.fecha_desembolso.strftime('%d/%m/%Y')}   |   "
          f"1ra Cuota: {params.fecha_primera_cuota.strftime('%d/%m/%Y')}   |   "
          f"Tipo: {tipo_str} (día/período: {params.dia_fec_pago})")
    print(f"  Desgravamen        : [{params.id_seguro_desgravamen}] {seg_obj.nombre}  "
          f"(nValor={seg_obj.n_valor}, tipo={'tasa' if seg_obj.id_tipo_valor==1 else 'prima fija'})")
    if plan_obj:
        print(f"  Plan seguro        : [{params.id_plan_seguro}] {plan_obj.nombre}  "
              f"(nValor=S/{plan_obj.n_valor:.2f}/mes, tipo={'tasa' if plan_obj.id_tipo_valor==1 else 'prima fija'})")
    else:
        print("  Plan seguro        : Sin plan adicional")
    if gracia_extra > 0:
        print(f"  Días gracia extra  : {gracia_extra} (1ra cuota superó {params.max_dias_primera_cuota} días)")
    print("=" * W)

    hdr = ("{:>5}  {:<12}  {:>5}  {:>10}  {:>9}  {:>8}  "
           "{:>11}  {:>11}  {:>9}  {:>11}")
    print(hdr.format("Cuota", "Fecha Pago", "Frec.", "Sal. Cap.",
                     "Capital", "Interés",
                     "Seg.Desgrav", "Prima Plan", "Seg|Comi", "Monto Cuota"))
    print("-" * W)

    tot_cap = tot_int = tot_desgrav = tot_plan = tot_seg = tot_imp = 0.0
    row_fmt = ("{:>5}  {:<12}  {:>5}  {:>10.2f}  {:>9.2f}  {:>8.2f}  "
               "{:>11.2f}  {:>11.2f}  {:>9.2f}  {:>11.2f}")

    for c in plan:
        print(row_fmt.format(
            c.cuota,
            c.fecha.strftime("%d/%m/%Y"),
            c.dias,
            c.sal_cap,
            c.capital,
            c.interes,
            c.seguro_desgravamen,
            c.prima_plan,
            c.seg_comi,
            c.imp_cuota,
        ))
        tot_cap     += c.capital
        tot_int     += c.interes
        tot_desgrav += c.seguro_desgravamen
        tot_plan    += c.prima_plan
        tot_seg     += c.seg_comi
        tot_imp     += c.imp_cuota

    print("-" * W)
    print(hdr.format("TOTAL", "", "", "",
                     f"{tot_cap:,.2f}", f"{tot_int:,.2f}",
                     f"{tot_desgrav:,.2f}", f"{tot_plan:,.2f}",
                     f"{tot_seg:,.2f}", f"{tot_imp:,.2f}"))
    print("=" * W)


# ══════════════════════════════════════════════════════════════════════
# 7. SELECCIÓN INTERACTIVA DE SEGUROS (helper)
# ══════════════════════════════════════════════════════════════════════

def seleccionar_seguro_interactivo(
    titulo: str = "Seleccione un seguro",
    solo_desgravamen: bool = False,
    solo_planes: bool = False
) -> int:
    """
    Muestra el menú de seguros y pide al usuario que ingrese el ID.
    Retorna el idTipoSeguro seleccionado.

    Parámetros
    ──────────
    titulo           : texto del prompt
    solo_desgravamen : mostrar solo los de idTipoValor=1
    solo_planes      : mostrar solo los de idTipoValor=2
    """
    print(f"\n  {'─'*60}")
    print(f"  {titulo}")
    print(f"  {'─'*60}")

    opciones = sorted(_SEGUROS_POR_ID.values(), key=lambda x: x.id_tipo_seguro)
    if solo_desgravamen:
        opciones = [s for s in opciones if s.id_tipo_valor == 1]
    if solo_planes:
        opciones = [s for s in opciones if s.id_tipo_valor == 2]

    for seg in opciones:
        tipo_str = "Tasa" if seg.id_tipo_valor == 1 else "Prima S/"
        val_str  = f"{seg.n_valor:.6f}" if seg.id_tipo_valor == 1 else f"S/{seg.n_valor:.2f}/mes"
        print(f"  [{seg.id_tipo_seguro:>2}] {seg.nombre:<52} {val_str}")

    print(f"  {'─'*60}")
    while True:
        try:
            eleccion = int(input(f"  Ingrese ID: "))
            return obtener_seguro_por_id(eleccion).id_tipo_seguro
        except (ValueError, KeyError):
            ids = [s.id_tipo_seguro for s in opciones]
            print(f"  ID inválido. Opciones válidas: {ids}")


# ══════════════════════════════════════════════════════════════════════
# 8. EJEMPLOS / DEMO
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "═"*60)
    print("  SEGUROS DISPONIBLES")
    print("═"*60)
    listar_seguros()

    # ─────────────────────────────────────────────────────────────────
    # DEMO 1: Replica imagen — desgravamen individual, sin plan
    # ─────────────────────────────────────────────────────────────────
    print("\n>>> DEMO 1 — Solo desgravamen individual (sin plan)\n")
    p1 = ParametrosPlanPago(
        monto_desembolso      = 10000.00,
        tasa_interes_anual    = 49.99 / 100.0,
        fecha_desembolso      = date(2026, 1, 29),
        num_cuotas            = 12,
        dias_gracia           = 0,
        tipo_periodo          = 1,
        dia_fec_pago          = 24,
        fecha_primera_cuota   = date(2026, 2, 24),
        nro_cuotas_gracia     = 0,
        forma_calculo_tasa    = 1,
        id_seguro_desgravamen = 9,    # DESGRAVAMEN INDIVIDUAL 0.1650%
        id_plan_seguro        = 5, # plan 1
        max_dias_primera_cuota= 26,
    )
    plan1 = generar_plan_pagos(p1)
    imprimir_plan_pagos(plan1, p1)

    # # ─────────────────────────────────────────────────────────────────
    # # DEMO 2: Con PLAN 1 (A. EDUCATIVA +2.50 S/mes)
    # # ─────────────────────────────────────────────────────────────────
    # print("\n>>> DEMO 2 — Desgravamen individual + PLAN 1: A. EDUCATIVA\n")
    # p2 = ParametrosPlanPago(
    #     monto_desembolso      = 10000.00,
    #     tasa_interes_anual    = 49.99 / 100.0,
    #     fecha_desembolso      = date(2026, 1, 29),
    #     num_cuotas            = 12,
    #     dias_gracia           = 0,
    #     tipo_periodo          = 1,
    #     dia_fec_pago          = 26,
    #     fecha_primera_cuota   = date(2026, 2, 26),
    #     nro_cuotas_gracia     = 0,
    #     forma_calculo_tasa    = 1,
    #     id_seguro_desgravamen = 9,   # DESGRAVAMEN INDIVIDUAL
    #     id_plan_seguro        = 5,   # PLAN 1: A. EDUCATIVA → +2.50/mes
    #     max_dias_primera_cuota= 30,
    # )
    # plan2 = generar_plan_pagos(p2)
    # imprimir_plan_pagos(plan2, p2)

    # # ─────────────────────────────────────────────────────────────────
    # # DEMO 3: Con PLAN 2 (A. EDUCATIVA + A. SALUD +5.75 S/mes)
    # # ─────────────────────────────────────────────────────────────────
    # print("\n>>> DEMO 3 — Desgravamen individual + PLAN 2: A. EDUCATIVA + A. SALUD\n")
    # p3 = ParametrosPlanPago(
    #     monto_desembolso      = 10000.00,
    #     tasa_interes_anual    = 49.99 / 100.0,
    #     fecha_desembolso      = date(2026, 1, 29),
    #     num_cuotas            = 12,
    #     dias_gracia           = 0,
    #     tipo_periodo          = 1,
    #     dia_fec_pago          = 26,
    #     fecha_primera_cuota   = date(2026, 2, 26),
    #     nro_cuotas_gracia     = 0,
    #     forma_calculo_tasa    = 1,
    #     id_seguro_desgravamen = 9,   # DESGRAVAMEN INDIVIDUAL
    #     id_plan_seguro        = 6,   # PLAN 2: +5.75/mes
    #     max_dias_primera_cuota= 30,
    # )
    # plan3 = generar_plan_pagos(p3)
    # imprimir_plan_pagos(plan3, p3)

    # # ─────────────────────────────────────────────────────────────────
    # # DEMO 4: Sin desgravamen, solo PLAN 1
    # # ─────────────────────────────────────────────────────────────────
    # print("\n>>> DEMO 4 — SIN desgravamen + PLAN 1\n")
    # p4 = ParametrosPlanPago(
    #     monto_desembolso      = 10000.00,
    #     tasa_interes_anual    = 49.99 / 100.0,
    #     fecha_desembolso      = date(2026, 1, 29),
    #     num_cuotas            = 12,
    #     dias_gracia           = 0,
    #     tipo_periodo          = 1,
    #     dia_fec_pago          = 26,
    #     fecha_primera_cuota   = date(2026, 2, 26),
    #     nro_cuotas_gracia     = 0,
    #     forma_calculo_tasa    = 1,
    #     id_seguro_desgravamen = 8,   # SIN DESGRAVAMEN
    #     id_plan_seguro        = 5,   # PLAN 1: +2.50/mes
    #     max_dias_primera_cuota= 30,
    # )
    # plan4 = generar_plan_pagos(p4)
    # imprimir_plan_pagos(plan4, p4)

    # # ─────────────────────────────────────────────────────────────────
    # # DEMO: uso de obtener_seguro_por_id()
    # # ─────────────────────────────────────────────────────────────────
    # print("\n>>> Consulta directa de seguros por ID:")
    # for id_seg in [5, 6, 7, 9, 10]:
    #     s = obtener_seguro_por_id(id_seg)
    #     tipo = "tasa" if s.id_tipo_valor == 1 else f"S/{s.n_valor:.2f}/mes"
    #     print(f"   ID {id_seg:>2}: {s.nombre}  →  {tipo}")