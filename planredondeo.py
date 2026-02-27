"""
╔══════════════════════════════════════════════════════════════════════╗
║          PLAN DE PAGOS - CAJA LOS ANDES                             ║
║          Cuotas Constantes (Sistema Francés)                        ║
╠══════════════════════════════════════════════════════════════════════╣
║  PRECISIÓN (equivalente a C#):                                       ║
║  • Se usa decimal.Decimal con 28 dígitos de precisión               ║
║    (igual que el tipo decimal de C#)                                 ║
║  • Redondeo ROUND_HALF_UP (igual que Math.Round de C#)              ║
║  • nDecRedonCalcPpg = 1  → la cuota se redondea a 1 decimal         ║
║    al APLICAR en cada cuota (Math.Round(cuota, 1))                   ║
║    La iteración sigue trabajando con más decimales internamente.     ║
║                                                                      ║
║  TABLA DE SEGUROS:                                                   ║
║  idTipoValor=1 → tasa proporcional:  sal_cap × nValor × (dias/30)   ║
║  idTipoValor=2 → prima fija S/mes:   nValor × (dias/30)             ║
║                                                                      ║
║  Seg|Comi = seguro_desgravamen + prima_plan                          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from datetime import date, timedelta
from dataclasses import dataclass
from typing import Optional
from decimal import Decimal, ROUND_HALF_UP, getcontext
import math

# Precisión de 28 dígitos = equivalente al tipo decimal de C#
getcontext().prec = 28


# ══════════════════════════════════════════════════════════════════════
# HELPERS DE REDONDEO (reemplazan Math.Round de C#)
# ══════════════════════════════════════════════════════════════════════

def _d(value) -> Decimal:
    """Convierte float/int/str a Decimal de forma segura."""
    return Decimal(str(value))

def _round(x: Decimal, decimales: int) -> Decimal:
    """
    Equivalente a Math.Round(x, decimales) de C#.
    Usa ROUND_HALF_UP (0.5 siempre sube).
    """
    fmt = Decimal(10) ** -decimales
    return x.quantize(fmt, rounding=ROUND_HALF_UP)

# Atajos usados en todo el código
def _r2(x): return _round(x, 2)   # redondeo a 2 decimales (montos)
def _r1(x): return _round(x, 1)   # redondeo a 1 decimal  (cuota aplicada, nDecRedonCalcPpg)
def _r10(x): return _round(x, 10) # redondeo a 10 dec     (razón de búsqueda iteración)


# ══════════════════════════════════════════════════════════════════════
# 1. TABLA DE SEGUROS
# ══════════════════════════════════════════════════════════════════════

@dataclass
class TipoSeguro:
    """
    Registro de la tabla TipoSeguro de la BD.

    idTipoValor=1 → nValor es tasa directa proporcional
                    prima = sal_cap × nValor × (dias/30)
    idTipoValor=2 → nValor es prima fija mensual en soles
                    prima = nValor × (dias/30)
    """
    id_tipo_seguro: int
    nombre: str
    n_valor: Decimal
    id_tipo_valor: int


# Tabla completa (fuente: BD)
TABLA_SEGUROS: dict[int, TipoSeguro] = {
    1:  TipoSeguro(1,  "SEGURO MULTIRIESGO",                              _d("0.001150"), 1),
    2:  TipoSeguro(2,  "SEGURO VIDA",                                     _d("5.000000"), 2),
    4:  TipoSeguro(4,  "SEGURO ONCOLÓGICO",                               _d("5.000000"), 2),
    5:  TipoSeguro(5,  "PLAN 1: A. EDUCATIVA",                            _d("2.500000"), 2),
    6:  TipoSeguro(6,  "PLAN 2: A. EDUCATIVA + A. SALUD",                 _d("5.750000"), 2),
    7:  TipoSeguro(7,  "PLAN 3: A. EDUCATIVA + A. SALUD + S. INCAPACIDAD",_d("8.500000"), 2),
    8:  TipoSeguro(8,  "SIN SEGURO DESGRAVAMEN",                          _d("0.000000"), 1),
    9:  TipoSeguro(9,  "SEGURO DESGRAVAMEN INDIVIDUAL",                   _d("0.001650"), 1),
    10: TipoSeguro(10, "SEGURO DESGRAVAMEN CONYUGAL",                     _d("0.002050"), 1),
    11: TipoSeguro(11, "SEGURO DESGRAVAMEN INDIVIDUAL ESPECIAL",          _d("0.001450"), 1),
    12: TipoSeguro(12, "SEGURO DESGRAVAMEN DEVOLUCIÓN",                   _d("0.002340"), 1),
}


def obtener_seguro_por_id(id_tipo_seguro: int) -> TipoSeguro:
    """
    Retorna el TipoSeguro para el idTipoSeguro dado.

    Ejemplo
    -------
        seg = obtener_seguro_por_id(5)
        print(seg.nombre)        # "PLAN 1: A. EDUCATIVA"
        print(seg.n_valor)       # Decimal("2.5")
        print(seg.id_tipo_valor) # 2  (prima fija)
    """
    if id_tipo_seguro not in TABLA_SEGUROS:
        raise KeyError(
            f"idTipoSeguro={id_tipo_seguro} no existe. "
            f"IDs válidos: {sorted(TABLA_SEGUROS.keys())}"
        )
    return TABLA_SEGUROS[id_tipo_seguro]


def listar_seguros():
    """Imprime la tabla completa de seguros disponibles."""
    print("─" * 72)
    print(f"  {'ID':>4}  {'Nombre':<52}  {'nValor':>9}  {'Tipo'}")
    print("─" * 72)
    for s in sorted(TABLA_SEGUROS.values(), key=lambda x: x.id_tipo_seguro):
        tipo = "Tasa" if s.id_tipo_valor == 1 else f"S/{s.n_valor}/mes"
        print(f"  {s.id_tipo_seguro:>4}  {s.nombre:<52}  {float(s.n_valor):>9.6f}  {tipo}")
    print("─" * 72)


def calcular_prima_seguro(
    seguro: TipoSeguro,
    sal_cap: Decimal,
    dias: int
) -> Decimal:
    """
    Calcula la prima del seguro para una cuota, proporcional a los días.

    idTipoValor=1 (tasa sobre saldo):
        prima = round(sal_cap × nValor × dias/30, 2)

    idTipoValor=2 (prima fija mensual en soles):
        prima = round(nValor × dias/30, 2)

    Por qué proporcional a días:
        La tasa/prima es mensual (base 30 días).
        Una cuota de 28 días paga 28/30 de la prima mensual.
        Una cuota de 31 días paga 31/30 de la prima mensual.
    """
    factor = _d(dias) / _d(30)
    if seguro.id_tipo_valor == 1:
        return _r2(sal_cap * seguro.n_valor * factor)
    elif seguro.id_tipo_valor == 2:
        return _r2(seguro.n_valor * factor)
    return Decimal("0.00")


# ══════════════════════════════════════════════════════════════════════
# 2. ESTRUCTURAS DE DATOS
# ══════════════════════════════════════════════════════════════════════

@dataclass
class CuotaPlan:
    """Una fila del plan de pagos (todos los montos son Decimal)."""
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
    seg_comi: Decimal          # = seguro_desgravamen + prima_plan
    imp_cuota: Decimal         # = capital + interes + seg_comi


@dataclass
class ParametrosPlanPago:
    """
    Parámetros de entrada para generar el plan de pagos.

    Seguros
    ───────
    id_seguro_desgravamen : idTipoSeguro del desgravamen
        9  → DESGRAVAMEN INDIVIDUAL  (0.1650%)
        10 → DESGRAVAMEN CONYUGAL    (0.2050%)
        8  → SIN DESGRAVAMEN         (0.0000)
    id_plan_seguro        : idTipoSeguro del plan opcional
        5  → PLAN 1: A. EDUCATIVA    (+S/2.50/mes)
        6  → PLAN 2: + A. SALUD      (+S/5.75/mes)
        7  → PLAN 3: + S. INCAPACIDAD(+S/8.50/mes)
        None → sin plan adicional

    nDecRedonCalcPpg
    ────────────────
    Controla con cuántos decimales se redondea la cuota al aplicarla
    en cada período (Math.Round(cuota, nDecRedonCalcPpg) en C#).
    El sistema original usa 1 → cuota redondeada a 1 decimal (ej. 1039.4).
    La iteración interna sigue usando más decimales para mayor precisión.
    """
    monto_desembolso: float
    tasa_interes_anual: float
    fecha_desembolso: date
    num_cuotas: int
    dias_gracia: int
    tipo_periodo: int                   # 1=Fecha Fija | 2=Periodo Fijo
    dia_fec_pago: int
    fecha_primera_cuota: date
    nro_cuotas_gracia: int = 0
    forma_calculo_tasa: int = 1         # 1=base 360 | 2=base 30
    id_seguro_desgravamen: int = 9      # DESGRAVAMEN INDIVIDUAL por defecto
    id_plan_seguro: Optional[int] = None
    max_dias_primera_cuota: int = 30
    n_dec_redon_calc_ppg: int = 1       # ← nDecRedonCalcPpg de C# (1 = 1 decimal)


# ══════════════════════════════════════════════════════════════════════
# 3. UTILIDADES
# ══════════════════════════════════════════════════════════════════════

def _calcular_ted(tasa_anual: float, forma: int) -> Decimal:
    """
    Calcula la Tasa Efectiva Diaria con precisión Decimal.
      forma=1 → base 360:  TED = (1+TEA)^(1/360) − 1
      forma=2 → base 30:   TED = (1+TEA)^(1/30)  − 1
    """
    uno = Decimal(1)
    tea = _d(tasa_anual)
    if forma == 1:
        return (uno + tea) ** (uno / Decimal(360)) - uno
    elif forma == 2:
        return (uno + tea) ** (uno / Decimal(30)) - uno
    raise ValueError(f"forma_calculo_tasa={forma} inválido. Use 1 o 2.")


def _fecha_valida(dia: int, mes: int, anio: int) -> date:
    """Retorna la fecha; retrocede el día si no existe en el mes (ej. 31-feb → 28-feb)."""
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
    """
    Si (fecha_primera_cuota − fecha_desembolso) > max_dias,
    retorna los días de gracia extra a sumar al acumulado.
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
# 5. FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

def generar_plan_pagos(params: ParametrosPlanPago) -> list[CuotaPlan]:
    """
    Genera el plan de pagos con precisión equivalente a C#.

    Diferencias clave vs versión float:
    ────────────────────────────────────
    1. Todos los cálculos usan decimal.Decimal (28 dígitos).
    2. La cuota se aplica redondeada a n_dec_redon_calc_ppg decimales
       (Math.Round(cuota, nDecRedonCalcPpg) en C#).
       Con n_dec_redon_calc_ppg=1: cuota de 1039.3657... → se aplica como 1039.4
    3. La iteración usa la cuota interna con más precisión para converger;
       solo al aplicar en cada período se redondea a 1 decimal.
    """
    TED = _calcular_ted(params.tasa_interes_anual, params.forma_calculo_tasa)
    MONTO = _d(params.monto_desembolso)
    DEC_CUOTA = params.n_dec_redon_calc_ppg  # nDecRedonCalcPpg

    seg_desgrav_obj = obtener_seguro_por_id(params.id_seguro_desgravamen)
    plan_obj = (
        obtener_seguro_por_id(params.id_plan_seguro)
        if params.id_plan_seguro is not None else None
    )

    gracia_extra = calcular_dias_gracia_extra(
        params.fecha_desembolso,
        params.fecha_primera_cuota,
        params.max_dias_primera_cuota
    )
    if gracia_extra > 0:
        print(f"  [GRACIA] 1ra cuota supera {params.max_dias_primera_cuota} días → "
              f"{gracia_extra} día(s) de gracia extra.\n")

    if params.tipo_periodo == 1:
        cronograma = _cronograma_fecha_fija(params, gracia_extra)
    elif params.tipo_periodo == 2:
        cronograma = _cronograma_periodo_fijo(params, gracia_extra)
    else:
        raise ValueError("tipo_periodo debe ser 1 o 2.")

    # FRC acumulado
    frcs: list[Decimal] = []
    fac_acumul = Decimal(0)
    for (_, __, da) in cronograma:
        frc = Decimal(1) / (Decimal(1) + TED) ** da
        frcs.append(frc)
        fac_acumul += frc

    # Cuota base inicial (2 decimales internos para la iteración)
    cuota_base = _r2(MONTO / fac_acumul)

    # ── Iteración bisección adaptativa ───────────────────────────────
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

            # ← nDecRedonCalcPpg: redondear cuota al aplicar en la cuota
            cuota_redond = _round(cuota_iter, DEC_CUOTA)

            interes = _r2(saldo * ((Decimal(1) + TED) ** dias - Decimal(1)))

            seg_desgrav = calcular_prima_seguro(seg_desgrav_obj, saldo, dias)
            prima_plan  = (
                calcular_prima_seguro(plan_obj, saldo, dias)
                if plan_obj is not None else Decimal("0.00")
            )
            seg_comi = _r2(seg_desgrav + prima_plan)

            if params.nro_cuotas_gracia >= num_cuota:
                capital = Decimal("0.00")
            else:
                capital = _r2(cuota_redond - interes - seg_comi)

            imp_cuota = _r2(capital + interes + seg_comi)

            plan_iter.append(CuotaPlan(
                cuota              = num_cuota,
                fecha              = fecha,
                dias               = dias,
                dias_acu           = dias_acu_i,
                frc                = frc,
                sal_cap            = _r2(saldo),
                capital            = capital,
                interes            = interes,
                seguro_desgravamen = seg_desgrav,
                prima_plan         = prima_plan,
                seg_comi           = seg_comi,
                imp_cuota          = imp_cuota,
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

    # Ajuste exacto última cuota
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
# 6. IMPRIMIR PLAN DE PAGOS
# ══════════════════════════════════════════════════════════════════════

def imprimir_plan_pagos(plan: list[CuotaPlan], params: ParametrosPlanPago):
    seg_obj  = obtener_seguro_por_id(params.id_seguro_desgravamen)
    plan_obj = (obtener_seguro_por_id(params.id_plan_seguro)
                if params.id_plan_seguro is not None else None)
    tipo_str = "Fecha Fija" if params.tipo_periodo == 1 else "Periodo Fijo"
    tea_pct  = params.tasa_interes_anual * 100
    gracia   = calcular_dias_gracia_extra(params.fecha_desembolso,
                                          params.fecha_primera_cuota,
                                          params.max_dias_primera_cuota)
    W = 138
    print("=" * W)
    print("  CAJA LOS ANDES  —  PLAN DE PAGOS")
    print(f"  Monto: S/ {params.monto_desembolso:,.2f}   TEA: {tea_pct:.4f}%   "
          f"Cuotas: {params.num_cuotas}   Tipo: {tipo_str} (día: {params.dia_fec_pago})")
    print(f"  Desembolso: {params.fecha_desembolso:%d/%m/%Y}   "
          f"1ra cuota: {params.fecha_primera_cuota:%d/%m/%Y}   "
          f"nDecRedonCalcPpg: {params.n_dec_redon_calc_ppg}")
    print(f"  Desgravamen: [{seg_obj.id_tipo_seguro}] {seg_obj.nombre}  "
          f"(nValor={seg_obj.n_valor})")
    if plan_obj:
        print(f"  Plan seguro: [{plan_obj.id_tipo_seguro}] {plan_obj.nombre}  "
              f"(S/{plan_obj.n_valor}/mes)")
    else:
        print("  Plan seguro: Sin plan adicional")
    if gracia > 0:
        print(f"  Días gracia extra: {gracia}")
    print("=" * W)

    hdr = ("{:>5}  {:<12}  {:>5}  {:>10}  {:>9}  {:>8}  "
           "{:>11}  {:>11}  {:>9}  {:>11}")
    print(hdr.format("Cuota", "Fecha Pago", "Frec.", "Sal. Cap.",
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
# 7. SELECCIÓN INTERACTIVA
# ══════════════════════════════════════════════════════════════════════

def seleccionar_seguro_interactivo(
    titulo: str = "Seleccione seguro",
    solo_desgravamen: bool = False,
    solo_planes: bool = False
) -> int:
    """Muestra menú y retorna el idTipoSeguro elegido."""
    print(f"\n  {'─'*62}")
    print(f"  {titulo}")
    print(f"  {'─'*62}")
    opciones = sorted(TABLA_SEGUROS.values(), key=lambda x: x.id_tipo_seguro)
    if solo_desgravamen: opciones = [s for s in opciones if s.id_tipo_valor == 1]
    if solo_planes:      opciones = [s for s in opciones if s.id_tipo_valor == 2]
    for s in opciones:
        val = f"{s.n_valor:.6f}" if s.id_tipo_valor == 1 else f"S/{s.n_valor}/mes"
        print(f"  [{s.id_tipo_seguro:>2}] {s.nombre:<54} {val}")
    print(f"  {'─'*62}")
    while True:
        try:
            eleccion = int(input("  Ingrese ID (0 = ninguno): "))
            if eleccion == 0: return 0
            return obtener_seguro_por_id(eleccion).id_tipo_seguro
        except (ValueError, KeyError):
            print(f"  ID inválido.")


# ══════════════════════════════════════════════════════════════════════
# 8. EJEMPLOS
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "═"*62)
    print("  SEGUROS DISPONIBLES")
    print("═"*62)
    listar_seguros()

    # ── DEMO 1: Replica exacta de la imagen ──────────────────────────
    print("\n>>> DEMO 1 — Replica imagen (10000, 49.99%, 12 cuotas, día 26)\n")
    p1 = ParametrosPlanPago(
        monto_desembolso       = 10000.00,
        tasa_interes_anual     = 49.99 / 100.0,
        fecha_desembolso       = date(2026, 1, 29),
        num_cuotas             = 12,
        dias_gracia            = 0,
        tipo_periodo           = 1,
        dia_fec_pago           = 24,
        fecha_primera_cuota    = date(2026, 2, 24),
        id_seguro_desgravamen  = 9,     # DESGRAVAMEN INDIVIDUAL
        id_plan_seguro         = 5,  # sin plan
        n_dec_redon_calc_ppg   = 1,     # ← nDecRedonCalcPpg = 1 (igual que C#)
    )
    imprimir_plan_pagos(generar_plan_pagos(p1), p1)

    # # ── DEMO 2: Con PLAN 1 ───────────────────────────────────────────
    # print("\n>>> DEMO 2 — Con PLAN 1: A. EDUCATIVA (+S/2.50/mes)\n")
    # p2 = ParametrosPlanPago(
    #     monto_desembolso       = 10000.00,
    #     tasa_interes_anual     = 49.99 / 100.0,
    #     fecha_desembolso       = date(2026, 1, 29),
    #     num_cuotas             = 12,
    #     dias_gracia            = 0,
    #     tipo_periodo           = 1,
    #     dia_fec_pago           = 26,
    #     fecha_primera_cuota    = date(2026, 2, 26),
    #     id_seguro_desgravamen  = 9,
    #     id_plan_seguro         = 5,     # PLAN 1
    #     n_dec_redon_calc_ppg   = 1,
    # )
    # imprimir_plan_pagos(generar_plan_pagos(p2), p2)

    # # ── DEMO 3: Con PLAN 2 ───────────────────────────────────────────
    # print("\n>>> DEMO 3 — Con PLAN 2: A. EDUCATIVA + A. SALUD (+S/5.75/mes)\n")
    # p3 = ParametrosPlanPago(
    #     monto_desembolso       = 10000.00,
    #     tasa_interes_anual     = 49.99 / 100.0,
    #     fecha_desembolso       = date(2026, 1, 29),
    #     num_cuotas             = 12,
    #     dias_gracia            = 0,
    #     tipo_periodo           = 1,
    #     dia_fec_pago           = 26,
    #     fecha_primera_cuota    = date(2026, 2, 26),
    #     id_seguro_desgravamen  = 9,
    #     id_plan_seguro         = 6,     # PLAN 2
    #     n_dec_redon_calc_ppg   = 1,
    # )
    # imprimir_plan_pagos(generar_plan_pagos(p3), p3)

    # # ── DEMO 4: Sin desgravamen + PLAN 1 ────────────────────────────
    # print("\n>>> DEMO 4 — SIN desgravamen + PLAN 1\n")
    # p4 = ParametrosPlanPago(
    #     monto_desembolso       = 10000.00,
    #     tasa_interes_anual     = 49.99 / 100.0,
    #     fecha_desembolso       = date(2026, 1, 29),
    #     num_cuotas             = 12,
    #     dias_gracia            = 0,
    #     tipo_periodo           = 1,
    #     dia_fec_pago           = 26,
    #     fecha_primera_cuota    = date(2026, 2, 26),
    #     id_seguro_desgravamen  = 8,     # SIN DESGRAVAMEN
    #     id_plan_seguro         = 5,     # PLAN 1
    #     n_dec_redon_calc_ppg   = 1,
    # )
    # imprimir_plan_pagos(generar_plan_pagos(p4), p4)

    # # ── DEMO 5: Consulta por ID ──────────────────────────────────────
    # print("\n>>> obtener_seguro_por_id() — consultas directas:")
    # for id_s in [5, 6, 7, 9, 10, 11, 12]:
    #     s = obtener_seguro_por_id(id_s)
    #     tipo = "tasa" if s.id_tipo_valor == 1 else f"S/{s.n_valor}/mes (prima fija)"
    #     print(f"   ID {id_s:>2}: {s.nombre:<54} → {tipo}")