"""Umbrales HU0007-4 aplicados a métricas guardadas, sin mezclar bloques."""

import math


def evaluar_validacion_modelo(tipo, metricas, criterios):
    """Devuelve estado, criterios y razones; 2025 no decide por defecto.

    El protocolo temporal sigue siendo el existente. Esta función verifica
    sus resultados guardados; no evalúa el booster final sobre entrenamiento.
    La selección de bloques y umbrales se conserva en cada versión.
    """
    if tipo == "persistencia":
        return {"estado_validacion": "referencia", "disponible": True,
                "motivo": "Línea base de comparación, sin validación como modelo operativo", "bloques": {}}
    resultados = {}
    bloques = criterios.get("bloques", [])
    if tipo not in {"clasificacion", "regresion"} or not bloques:
        return {"estado_validacion": "experimental", "disponible": False,
                "motivo": "No hay criterios de validación completos", "bloques": {}}
    for nombre in bloques:
        fold = metricas.get("bloques", {}).get(nombre)
        checks, motivos = {}, []
        if not isinstance(fold, dict):
            motivos.append("No hay métricas guardadas para el bloque requerido")
        else:
            if tipo == "clasificacion":
                valores = fold.get(tipo, {}).get("alerta_directa", {})
                pares = [(m, valores.get(m), criterios.get(c)) for m, c in
                         (("recall", "recall_minimo"), ("precision", "precision_minima"), ("f1", "f1_minimo"))]
            else:
                valores = fold.get(tipo, {}).get("conteos", {})
                referencia = fold.get("persistencia", {}).get("conteos", {})
                factor = criterios.get("proporcion_error_persistencia")
                pares = []
                for m in ("mae", "rmse"):
                    base = referencia.get(m)
                    limite = factor * base if _finito(factor) and _finito(base) and base >= 0 else None
                    pares.append((m, valores.get(m), limite))
            for metrica, valor, limite in pares:
                disponible = _finito(valor) and _finito(limite) and valor >= 0 and limite >= 0
                cumple = disponible and (valor >= limite if tipo == "clasificacion" else valor <= limite)
                checks[metrica] = {"valor": valor, "limite": limite,
                                  "disponible": disponible, "cumple": cumple}
                if not disponible:
                    motivos.append(f"Métrica o referencia no disponible: {metrica}")
                elif not cumple:
                    motivos.append(f"No cumple el umbral de {metrica}")
        resultados[nombre] = {"cumple": bool(checks) and all(c["cumple"] for c in checks.values()),
                              "criterios": checks, "motivos": motivos}
    aprobado = all(b["cumple"] for b in resultados.values())
    completo = all(b["criterios"] and all(c["disponible"] for c in b["criterios"].values()) for b in resultados.values())
    return {"estado_validacion": "validado" if aprobado else "experimental",
            "disponible": completo, "motivo": None if aprobado else "; ".join(
                f"{nombre}: {motivo}" for nombre, b in resultados.items() for motivo in b["motivos"]),
            "bloques": resultados}


def _finito(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)
