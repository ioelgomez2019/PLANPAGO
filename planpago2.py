"""
╔══════════════════════════════════════════════════════════════════════╗
║          PLAN DE PAGOS - CAJA LOS ANDES                             ║
║          Cuotas Constantes (Sistema Francés)                        ║
╠══════════════════════════════════════════════════════════════════════╣
║  CORRECCIONES aplicadas (vs versión anterior):                       ║
║                                                                      ║
║  1. SEGURO DESGRAVAMEN — proporcional a los días de la cuota:        ║
║     seguro = sal_cap × (tasa_mensual / 30) × dias_cuota             ║
║     → cuotas de 28 días pagan menos seguro que cuotas de 31 días    ║
║                                                                      ║
║  2. CUOTA TOTAL CONSTANTE — el seguro SE INCLUYE dentro de la       ║
║     cuota constante que busca la iteración:                          ║
║     cuota_total = capital + interés + seguro  (siempre igual)        ║
║     capital = cuota_total − interés − seguro                        ║
║     → la iteración ajusta cuota_total (no solo cap+int)             ║
║                                                                      ║
║  3. DÍAS DE GRACIA — automáticos si 1ra cuota supera 30 días del    ║
║     desembolso (se suman al dias_acu de todas las cuotas).           ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from datetime import date, timedelta
from dataclasses import dataclass
import math


# ══════════════════════════════════════════════════════════════════════
# 1. ESTRUCTURAS DE DATOS
# ══════════════════════════════════════════════════════════════════════

@dataclass
class CuotaPlan:
    """Una fila completa del plan de pagos."""
    cuota: int
    fecha: date
    dias: int              # días entre esta cuota y la anterior (o desembolso)
    dias_acu: int          # días acumulados desde el desembolso
    frc: float             # Factor de Recuperación de Capital
    sal_cap: float         # Saldo capital al inicio de la cuota
    capital: float         # Amortización de capital
    interes: float         # Interés devengado
    seguro_desgravamen: float  # Seguro desgravamen (proporcional a días)
    comisiones: float      # = seguro_desgravamen (+ otras comisiones futuras)
    imp_cuota: float       # Importe total = capital + interés + comisiones


@dataclass
class ParametrosPlanPago:
    """
    Parámetros de entrada para generar el plan de pagos.

    Parámetro                  Descripción                              Ejemplo
    ──────────────────────────  ──────────────────────────────────────── ──────────
    monto_desembolso            Monto neto entregado al cliente          10000.00
    tasa_interes_anual          TEA como fracción decimal                0.4999
    fecha_desembolso            Fecha de desembolso                      date(2026,1,29)
    num_cuotas                  Número total de cuotas                   12
    dias_gracia                 Días de gracia iniciales (normalmente 0) 0
    tipo_periodo                1 = Fecha Fija | 2 = Periodo Fijo        1
    dia_fec_pago                tipo=1 → día del mes (ej. 26)            26
                                tipo=2 → cada N días (ej. 30)
    fecha_primera_cuota         Fecha exacta de la primera cuota         date(2026,2,26)
    nro_cuotas_gracia           Cuotas donde no se amortiza capital      0
    forma_calculo_tasa          1 = base 360 días | 2 = base 30 días     1
    tasa_desgravamen_mensual    Tasa mensual del seguro (fracción)       0.001650
                                Si es 0.0 no se aplica seguro.
                                IMPORTANTE: el seguro es PROPORCIONAL a
                                los días de cada cuota: se divide entre
                                30 y se multiplica por los días reales.
    max_dias_primera_cuota      Máximo días 1ra cuota antes de sumar     30
                                días de gracia automáticos (1,2,3...)
    """
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
    tasa_desgravamen_mensual: float = 0.0
    max_dias_primera_cuota: int = 30


# ══════════════════════════════════════════════════════════════════════
# 2. TASA EFECTIVA DIARIA
# ══════════════════════════════════════════════════════════════════════

def calcular_ted(tasa_anual: float, forma: int) -> float:
    """
    Convierte la TEA a tasa efectiva diaria (TED).
      forma=1 → base 360:  TED = (1+TEA)^(1/360) − 1
      forma=2 → base 30:   TED = (1+TEA)^(1/30)  − 1
    """
    if forma == 1:
        return math.pow(1.0 + tasa_anual, 1.0 / 360.0) - 1.0
    elif forma == 2:
        return math.pow(1.0 + tasa_anual, 1.0 / 30.0) - 1.0
    else:
        raise ValueError(f"forma_calculo_tasa={forma} inválido. Use 1 o 2.")


def _fecha_valida(dia: int, mes: int, anio: int) -> date:
    """
    Retorna date(anio, mes, dia). Si el día no existe en ese mes
    retrocede hasta el último día válido (ej. 31-feb → 28-feb).
    """
    d = dia
    while d >= 1:
        try:
            return date(anio, mes, d)
        except ValueError:
            d -= 1
    raise ValueError(f"No se pudo crear fecha válida: {dia}/{mes}/{anio}")


# ══════════════════════════════════════════════════════════════════════
# 3. DÍAS DE GRACIA AUTOMÁTICOS
# ══════════════════════════════════════════════════════════════════════

def calcular_dias_gracia_extra(
    fecha_desembolso: date,
    fecha_primera_cuota: date,
    max_dias: int = 30
) -> int:
    """
    Si (fecha_primera_cuota − fecha_desembolso) supera max_dias,
    calcula los días de gracia extra a sumar al acumulado de días.

    ¿Cómo afecta?
    → Se suman al dias_acu de la 1ra cuota (y por propagación a todas).
    → Cada FRC = 1/(1+TED)^dias_acu es menor → Σ FRC baja → cuota sube.
    → El cliente paga más por cuota pero el saldo parte en la misma fecha.
    """
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
    """
    Tipo periodo = 1 (Fecha Fija): mismo día del mes cada cuota.
    gracia_extra se suma al dias_acu de la 1ra cuota.
    Retorna lista de (fecha, dias, dias_acumulados).
    """
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
    """
    Tipo periodo = 2 (Periodo Fijo): cada cuota separada N días fijos.
    gracia_extra se suma al dias_acu de la 1ra cuota.
    Retorna lista de (fecha, dias, dias_acumulados).
    """
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
# 5. SEGURO DESGRAVAMEN (PROPORCIONAL A DÍAS)
# ══════════════════════════════════════════════════════════════════════

def calcular_seguro(sal_cap: float, tasa_mensual: float, dias: int) -> float:
    """
    Seguro desgravamen proporcional a los días de la cuota.

    FÓRMULA:
        tasa_diaria = tasa_mensual / 30
        seguro = round(sal_cap × tasa_diaria × dias, 2)

    POR QUÉ proporcional:
    ─────────────────────
    La tasa 0.1650% es mensual (base 30 días). Si la cuota tiene más
    o menos días, el seguro se ajusta proporcionalmente:
      • Cuota de 28 días → 0.1650% × 28/30 = 0.1540% del saldo
      • Cuota de 30 días → 0.1650% × 30/30 = 0.1650% del saldo
      • Cuota de 31 días → 0.1650% × 31/30 = 0.1705% del saldo

    IMPACTO EN EL PLAN:
    ────────────────────
    El seguro forma parte de la cuota_total constante:
        cuota_total = capital + interés + seguro  (siempre igual)
        capital = cuota_total − interés − seguro
    Como el saldo baja mes a mes, el seguro también baja.
    El capital amortizado varía (más capital cuando menos seguro/interés).
    """
    if tasa_mensual <= 0:
        return 0.0
    tasa_diaria = tasa_mensual / 30.0
    return round(sal_cap * tasa_diaria * dias, 2)


# ══════════════════════════════════════════════════════════════════════
# 6. FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

def generar_plan_pagos(params: ParametrosPlanPago) -> list[CuotaPlan]:
    """
    Genera el plan de pagos completo con cuotas constantes.

    La cuota constante incluye capital + interés + seguro desgravamen.
    La iteración busca el valor de cuota_total tal que el saldo
    al final de la última cuota sea ≈ 0.
    """
    TED = calcular_ted(params.tasa_interes_anual, params.forma_calculo_tasa)
    DEC = 2

    # Días de gracia automáticos
    gracia_extra = calcular_dias_gracia_extra(
        params.fecha_desembolso,
        params.fecha_primera_cuota,
        params.max_dias_primera_cuota
    )
    if gracia_extra > 0:
        print(f"  [GRACIA] 1ra cuota supera {params.max_dias_primera_cuota} días → "
              f"{gracia_extra} día(s) de gracia extra aplicados.\n")

    # Cronograma de fechas
    if params.tipo_periodo == 1:
        cronograma = _cronograma_fecha_fija(params, gracia_extra)
    elif params.tipo_periodo == 2:
        cronograma = _cronograma_periodo_fijo(params, gracia_extra)
    else:
        raise ValueError("tipo_periodo debe ser 1 (Fecha Fija) o 2 (Periodo Fijo).")

    # FRC acumulado (solo para cuota_base inicial, SIN seguro)
    frcs = []
    fac_acumul = 0.0
    for (_, __, da) in cronograma:
        frc = 1.0 / math.pow(1.0 + TED, da)
        frcs.append(frc)
        fac_acumul += frc

    # Cuota base inicial = Monto / Σ FRC  (sin seguro, solo como punto de partida)
    cuota_base = round(params.monto_desembolso / fac_acumul, DEC)

    # ── Iteración bisección adaptativa ───────────────────────────────
    # cuota_iter es la CUOTA TOTAL (capital + interés + seguro)
    # capital = cuota_iter − interés − seguro  (el seguro se descuenta del cap)
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

            # Interés del período
            interes = round(saldo * (math.pow(1.0 + TED, dias) - 1.0), DEC)

            # Seguro proporcional a los días
            seg = calcular_seguro(saldo, params.tasa_desgravamen_mensual, dias)

            # Capital = cuota_total − interés − seguro
            if params.nro_cuotas_gracia >= num_cuota:
                capital = 0.0   # cuota de gracia: solo paga interés + seguro
            else:
                capital = round(cuota_redond - interes - seg, DEC)

            comisiones = seg
            imp_cuota  = round(capital + interes + comisiones, DEC)

            plan_iter.append(CuotaPlan(
                cuota              = num_cuota,
                fecha              = fecha,
                dias               = dias,
                dias_acu           = dias_acu_i,
                frc                = frcs[idx],
                sal_cap            = round(saldo, DEC),
                capital            = round(capital, DEC),
                interes            = round(interes, DEC),
                seguro_desgravamen = seg,
                comisiones         = comisiones,
                imp_cuota          = imp_cuota,
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
        dias_acu_total = cronograma[-1][2]
        razon_busq     = round(saldo_final * potenc_dos / dias_acu_total, 10)
        cuota_iter     = cuota_iter + razon_busq

        if razon_busq == 0:
            if not ind_sal_ite:
                ind_sal_ite = True
                num_sal_ite = iteracion
            cuota_iter += 0.01

        if ind_sal_ite and iteracion == num_sal_ite + 1:
            break

    # ── Ajuste exacto última cuota ────────────────────────────────────
    if mejor_plan:
        ult         = mejor_plan[-1]
        saldo_ult   = ult.sal_cap
        interes_ult = round(saldo_ult * (math.pow(1.0 + TED, ult.dias) - 1.0), DEC)
        capital_ult = round(saldo_ult, DEC)
        seg_ult     = calcular_seguro(saldo_ult, params.tasa_desgravamen_mensual, ult.dias)
        comis_ult   = seg_ult
        imp_ult     = round(capital_ult + interes_ult + comis_ult, DEC)

        mejor_plan[-1] = CuotaPlan(
            cuota              = ult.cuota,
            fecha              = ult.fecha,
            dias               = ult.dias,
            dias_acu           = ult.dias_acu,
            frc                = ult.frc,
            sal_cap            = saldo_ult,
            capital            = capital_ult,
            interes            = interes_ult,
            seguro_desgravamen = seg_ult,
            comisiones         = comis_ult,
            imp_cuota          = imp_ult,
        )

    return mejor_plan


# ══════════════════════════════════════════════════════════════════════
# 7. IMPRIMIR PLAN DE PAGOS
# ══════════════════════════════════════════════════════════════════════

def imprimir_plan_pagos(plan: list[CuotaPlan], params: ParametrosPlanPago):
    """
    Imprime el plan de pagos en formato tabular.
    Columnas: cuota | fecha | frecuencia (días) | sal_cap | capital |
              interés | seg_desgrav | comisiones | imp_cuota
    (idéntico al layout de la imagen de referencia)
    """
    tipo_str    = "Fecha Fija" if params.tipo_periodo == 1 else "Periodo Fijo"
    tea_pct     = params.tasa_interes_anual * 100
    desgrav_pct = params.tasa_desgravamen_mensual * 100

    gracia_extra = calcular_dias_gracia_extra(
        params.fecha_desembolso, params.fecha_primera_cuota, params.max_dias_primera_cuota
    )

    W = 118
    print("=" * W)
    print("  CAJA LOS ANDES  —  PLAN DE PAGOS")
    print(f"  Monto desembolsado     : S/ {params.monto_desembolso:,.2f}")
    print(f"  TEA                    : {tea_pct:.4f} %")
    print(f"  Seg. Desgravamen mens. : {desgrav_pct:.4f} %  "
          f"(proporcional a los días de cada cuota: tasa/30 × días)")
    print(f"  Fecha desembolso       : {params.fecha_desembolso.strftime('%d/%m/%Y')}")
    print(f"  Primera cuota          : {params.fecha_primera_cuota.strftime('%d/%m/%Y')}")
    print(f"  N° cuotas              : {params.num_cuotas}")
    print(f"  Tipo periodo           : {tipo_str}  |  Día/periodo: {params.dia_fec_pago}")
    if gracia_extra > 0:
        print(f"  Días gracia aplicados  : {gracia_extra} días extra "
              f"(1ra cuota superó {params.max_dias_primera_cuota} días)")
    print("=" * W)

    hdr = "{:>5}  {:<12}  {:>11}  {:>10}  {:>9}  {:>8}  {:>11}  {:>11}  {:>10}"
    print(hdr.format("Cuota", "Fecha Pago", "Frecuencia", "Sal. Cap.",
                     "Capital", "Interés", "Seg.|Comi.", "Comisiones", "Monto Cuota"))
    print("-" * W)

    tot_cap = tot_int = tot_seg = tot_com = tot_imp = 0.0
    row_fmt = "{:>5}  {:<12}  {:>11}  {:>10.2f}  {:>9.2f}  {:>8.2f}  {:>11.2f}  {:>11.2f}  {:>10.2f}"

    for c in plan:
        print(row_fmt.format(
            c.cuota,
            c.fecha.strftime("%d/%m/%Y"),
            c.dias,
            c.sal_cap,
            c.capital,
            c.interes,
            c.seguro_desgravamen,
            c.comisiones,
            c.imp_cuota,
        ))
        tot_cap += c.capital
        tot_int += c.interes
        tot_seg += c.seguro_desgravamen
        tot_com += c.comisiones
        tot_imp += c.imp_cuota

    print("-" * W)
    print(hdr.format("TOTAL", "", "",
                     f"{tot_cap:,.2f}", f"{tot_cap:,.2f}",
                     f"{tot_int:,.2f}", f"{tot_seg:,.2f}",
                     f"{tot_com:,.2f}", f"{tot_imp:,.2f}"))
    print("=" * W)


# ══════════════════════════════════════════════════════════════════════
# 8. EJEMPLOS DE USO
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # ─────────────────────────────────────────────────────────────────
    # EJEMPLO 1: Replica exacta de la imagen
    #   Monto=10000, TEA=49.99%, 12 cuotas, Fecha Fija día 26
    #   Desembolso 29-ene-2026, 1ra cuota 26-feb-2026 (28 días)
    # ─────────────────────────────────────────────────────────────────
    print("\n>>> EJEMPLO 1 — Replica imagen (TEA 49.99%, 10000, 12 cuotas, día 26)\n")
    p1 = ParametrosPlanPago(
        monto_desembolso        = 10000.00,
        tasa_interes_anual      = 49.99 / 100.0,
        fecha_desembolso        = date(2026, 1, 29),
        num_cuotas              = 12,
        dias_gracia             = 0,
        tipo_periodo            = 1,               # Fecha Fija
        dia_fec_pago            = 24,
        fecha_primera_cuota     = date(2026, 2, 24),
        nro_cuotas_gracia       = 0,
        forma_calculo_tasa      = 1,
        tasa_desgravamen_mensual= 0.1650 / 100,    # 0.1650% mensual
        max_dias_primera_cuota  = 26,
    )
    plan1 = generar_plan_pagos(p1)
    imprimir_plan_pagos(plan1, p1)

    # # ─────────────────────────────────────────────────────────────────
    # # EJEMPLO 2: Fecha Fija día 24 — caso original (5000, 10 cuotas)
    # # ─────────────────────────────────────────────────────────────────
    # print("\n>>> EJEMPLO 2 — Fecha Fija día 24 (5000, TEA 56.99%, 10 cuotas)\n")
    # p2 = ParametrosPlanPago(
    #     monto_desembolso        = 5000.00,
    #     tasa_interes_anual      = 56.99 / 100.0,
    #     fecha_desembolso        = date(2026, 1, 29),
    #     num_cuotas              = 10,
    #     dias_gracia             = 0,
    #     tipo_periodo            = 1,
    #     dia_fec_pago            = 24,
    #     fecha_primera_cuota     = date(2026, 2, 24),
    #     nro_cuotas_gracia       = 0,
    #     forma_calculo_tasa      = 1,
    #     tasa_desgravamen_mensual= 0.1650 / 100,
    #     max_dias_primera_cuota  = 30,
    # )
    # plan2 = generar_plan_pagos(p2)
    # imprimir_plan_pagos(plan2, p2)

    # # ─────────────────────────────────────────────────────────────────
    # # EJEMPLO 3: 1ra cuota supera 30 días → días de gracia automáticos
    # # ─────────────────────────────────────────────────────────────────
    # print("\n>>> EJEMPLO 3 — 1ra cuota supera 30 días (gracia automática)\n")
    # p3 = ParametrosPlanPago(
    #     monto_desembolso        = 5000.00,
    #     tasa_interes_anual      = 56.99 / 100.0,
    #     fecha_desembolso        = date(2026, 1, 1),
    #     num_cuotas              = 10,
    #     dias_gracia             = 0,
    #     tipo_periodo            = 1,
    #     dia_fec_pago            = 24,
    #     fecha_primera_cuota     = date(2026, 2, 24),  # 54 días → gracia=24
    #     nro_cuotas_gracia       = 0,
    #     forma_calculo_tasa      = 1,
    #     tasa_desgravamen_mensual= 0.1650 / 100,
    #     max_dias_primera_cuota  = 30,
    # )
    # plan3 = generar_plan_pagos(p3)
    # imprimir_plan_pagos(plan3, p3)

    # # ─────────────────────────────────────────────────────────────────
    # # EJEMPLO 4: Periodo Fijo (cada 30 días)
    # # ─────────────────────────────────────────────────────────────────
    # print("\n>>> EJEMPLO 4 — Periodo Fijo (cada 30 días)\n")
    # p4 = ParametrosPlanPago(
    #     monto_desembolso        = 5000.00,
    #     tasa_interes_anual      = 56.99 / 100.0,
    #     fecha_desembolso        = date(2026, 1, 29),
    #     num_cuotas              = 10,
    #     dias_gracia             = 0,
    #     tipo_periodo            = 2,
    #     dia_fec_pago            = 30,
    #     fecha_primera_cuota     = date(2026, 2, 28),
    #     nro_cuotas_gracia       = 0,
    #     forma_calculo_tasa      = 1,
    #     tasa_desgravamen_mensual= 0.1650 / 100,
    #     max_dias_primera_cuota  = 30,
    # )
    # plan4 = generar_plan_pagos(p4)
    # imprimir_plan_pagos(plan4, p4)

    # # ─────────────────────────────────────────────────────────────────
    # # EJEMPLO 5: Sin seguro desgravamen (para comparar)
    # # ─────────────────────────────────────────────────────────────────
    # print("\n>>> EJEMPLO 5 — Sin seguro desgravamen\n")
    # p5 = ParametrosPlanPago(
    #     monto_desembolso        = 10000.00,
    #     tasa_interes_anual      = 49.99 / 100.0,
    #     fecha_desembolso        = date(2026, 1, 29),
    #     num_cuotas              = 12,
    #     dias_gracia             = 0,
    #     tipo_periodo            = 1,
    #     dia_fec_pago            = 26,
    #     fecha_primera_cuota     = date(2026, 2, 26),
    #     nro_cuotas_gracia       = 0,
    #     forma_calculo_tasa      = 1,
    #     tasa_desgravamen_mensual= 0.0,             # sin seguro
    #     max_dias_primera_cuota  = 30,
    # )
    # plan5 = generar_plan_pagos(p5)
    # imprimir_plan_pagos(plan5, p5)