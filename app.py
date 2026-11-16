"""Dr. Proceso · Versión 4. Ejecutar: streamlit run app.py"""
import csv
import io
import unicodedata
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

import streamlit as st


COLUMNAS = (
    "caso", "paso", "rol", "responsable", "fecha_hora", "solicitante",
    "centro_costo", "proveedor", "monto_usd", "comentario",
)
MENSAJE_PROTECCION = (
    "Este archivo no está protegido. Pásalo primero por tu Protector"
)


class ArchivoNoProtegido(ValueError):
    pass


def normalizar(texto):
    return "".join(
        caracter for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    ).strip().lower()


def validar_y_cargar(contenido):
    # UTF-8 estricto; admite también la marca BOM de algunos exportadores.
    texto = contenido.decode("utf-8-sig")
    # Comprobación global previa: nunca se muestra contenido del archivo.
    if "@" in texto:
        raise ArchivoNoProtegido

    lector = csv.reader(io.StringIO(texto, newline=""), strict=True)
    cabecera = next(lector, None)
    if cabecera is None:
        raise ValueError("El archivo está vacío.")

    nombres = [normalizar(nombre) for nombre in cabecera]
    if any(
        termino in nombre
        for nombre in nombres
        for termino in ("cedula", "correo", "telefono")
    ):
        raise ArchivoNoProtegido

    if len(nombres) != len(set(nombres)):
        raise ValueError("El archivo contiene nombres de columnas duplicados.")
    if set(nombres) != set(COLUMNAS):
        raise ValueError("El CSV debe contener exactamente las columnas indicadas.")

    indice_caso = nombres.index("caso")
    registros = []
    for fila in lector:
        # Las líneas completamente vacías no representan movimientos.
        if not fila:
            continue
        if len(fila) != len(cabecera):
            raise ValueError("Hay filas con una cantidad incorrecta de columnas.")
        caso = fila[indice_caso]
        if not caso.strip():
            raise ValueError("Todos los movimientos deben tener un caso informado.")
        # Se mantienen los identificadores como texto: 001 y 1 son distintos.
        registros.append(dict(zip(nombres, fila)))
    return registros


def leer_fecha(valor):
    """ISO 8601 o día/mes/año, con hora; no se adivina mes/día."""
    valor = valor.strip()
    try:
        fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if "T" not in valor and " " not in valor:
            raise ValueError
        return fecha
    except ValueError:
        pass
    for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                    "%d/%m/%Y %H:%M:%S.%f"):
        try:
            return datetime.strptime(valor, formato)
        except ValueError:
            continue
    raise ValueError(
        "Hay fechas vacías o inválidas. Usa AAAA-MM-DD HH:MM:SS "
        "o DD/MM/AAAA HH:MM:SS (también se admite ISO 8601)."
    )


def construir_radiografia(registros):
    eventos = defaultdict(list)
    zonas = set()
    for orden, registro in enumerate(registros):
        if not registro["paso"].strip():
            raise ValueError("Todos los movimientos deben tener un paso informado.")
        fecha = leer_fecha(registro["fecha_hora"])
        con_zona = fecha.utcoffset() is not None
        zonas.add(con_zona)
        if con_zona:
            fecha = fecha.astimezone(timezone.utc)
        eventos[registro["caso"]].append((fecha, orden, registro["paso"]))
    if len(zonas) > 1:
        raise ValueError(
            "El archivo mezcla fechas con y sin zona horaria. Unifica su formato."
        )

    frecuencias = Counter()
    empates = False
    for movimientos in eventos.values():
        movimientos.sort(key=lambda evento: (evento[0], evento[1]))
        if len({evento[0] for evento in movimientos}) < len(movimientos):
            empates = True
        # La tupla conserva pasos repetidos y evita colisiones al agrupar.
        frecuencias[tuple(evento[2] for evento in movimientos)] += 1

    total = len(eventos)
    tabla = [
        {
            "Camino real (secuencia exacta)": json.dumps(camino, ensure_ascii=False),
            "Solicitudes": cantidad,
            "Porcentaje (%)": cantidad / total * 100,
        }
        for camino, cantidad in sorted(
            frecuencias.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    return tabla, empates


def calcular_devoluciones(registros):
    """Cuenta cada caso una sola vez, aunque tenga varias devoluciones."""
    casos = {fila["caso"] for fila in registros}
    devueltos = {
        fila["caso"] for fila in registros
        if fila["paso"] == "Devolver al solicitante"
    }
    total = len(casos)
    porcentaje = len(devueltos) / total * 100 if total else 0.0
    return len(devueltos), total, porcentaje


def calcular_tiempos(registros):
    """Días transcurridos de 24 horas, incluyendo fines de semana y feriados."""
    eventos = defaultdict(list)
    zonas = set()
    for orden, fila in enumerate(registros):
        if not fila["paso"].strip():
            raise ValueError("Todos los movimientos deben tener un paso informado.")
        fecha = leer_fecha(fila["fecha_hora"])
        con_zona = fecha.utcoffset() is not None
        zonas.add(con_zona)
        if con_zona:
            fecha = fecha.astimezone(timezone.utc)
        eventos[fila["caso"]].append((fecha, orden, fila["paso"]))
    if len(zonas) > 1:
        raise ValueError(
            "El archivo mezcla fechas con y sin zona horaria. Unifica su formato."
        )

    duraciones = []
    esperas = defaultdict(list)
    casos_por_paso = defaultdict(set)
    detalle = []
    for caso, movimientos in eventos.items():
        movimientos.sort(key=lambda evento: (evento[0], evento[1]))
        duraciones.append((movimientos[-1][0] - movimientos[0][0]).total_seconds() / 86400)
        # Se excluye el primer movimiento de cada caso de los promedios de espera.
        for anterior, actual in zip(movimientos, movimientos[1:]):
            dias = (actual[0] - anterior[0]).total_seconds() / 86400
            paso = actual[2]
            esperas[paso].append(dias)
            casos_por_paso[paso].add(caso)
            detalle.append({
                "Caso": caso,
                "Paso anterior": anterior[2],
                "Paso": paso,
                "Fecha y hora": actual[0].isoformat(sep=" "),
                "Espera (días)": dias,
            })

    tabla = [
        {
            "Paso": paso,
            "Espera promedio (días)": sum(valores) / len(valores),
            "Intervalos": len(valores),
            "Solicitudes": len(casos_por_paso[paso]),
        }
        for paso, valores in esperas.items()
    ]
    tabla.sort(key=lambda fila: (-fila["Espera promedio (días)"], fila["Paso"]))
    mayor = tabla[0]["Espera promedio (días)"] if tabla else None
    for fila in tabla:
        fila["Cuello de botella"] = (
            "Mayor espera promedio"
            if mayor is not None and mayor > 0
            and abs(fila["Espera promedio (días)"] - mayor) < 1e-12
            else ""
        )
    resumen = {
        "promedio": sum(duraciones) / len(duraciones) if duraciones else 0.0,
        "minima": min(duraciones, default=0.0),
        "maxima": max(duraciones, default=0.0),
        "un_movimiento": sum(len(movimientos) == 1 for movimientos in eventos.values()),
    }
    return resumen, tabla, detalle


def main():
    st.set_page_config(page_title="Dr. Proceso", page_icon="🩺", layout="wide")
    st.title("🩺 Dr. Proceso")
    st.caption("Radiografía del proceso · Versión 4")
    cargar, radiografia = st.tabs(["Cargar", "Radiografía"])
    registros = None

    with cargar:
        st.write("Sube tu archivo CSV protegido, codificado en UTF-8 y separado por comas.")
        st.caption("Columnas: " + ", ".join(COLUMNAS))
        archivo = st.file_uploader("Elegir archivo CSV", type=["csv"])
        if archivo is not None:
            try:
                registros = validar_y_cargar(archivo.getvalue())
            except ArchivoNoProtegido:
                st.error(MENSAJE_PROTECCION)
                st.stop()
            except UnicodeDecodeError:
                st.error("No se pudo leer el archivo. Guarda el CSV en UTF-8.")
                st.stop()
            except csv.Error:
                st.error("El CSV tiene un formato inválido. Revisa separadores y comillas.")
                st.stop()
            except ValueError as error:
                st.error(str(error))
                st.stop()

            st.success("Archivo aceptado: superó la validación de protección de esta versión.")
            izquierda, derecha = st.columns(2)
            izquierda.metric("Solicitudes (casos únicos)",
                             len({fila["caso"] for fila in registros}))
            derecha.metric("Movimientos (filas)", len(registros))

    with radiografia:
        if registros is None:
            st.info("Sube un CSV protegido en la pestaña Cargar.")
        elif not registros:
            st.info("El archivo no contiene movimientos.")
        else:
            try:
                tabla, empates = construir_radiografia(registros)
                tiempos, esperas, detalle = calcular_tiempos(registros)
            except ValueError as error:
                st.error(str(error))
                return
            devueltos, total, porcentaje = calcular_devoluciones(registros)
            st.metric("Solicitudes con devolución al solicitante", f"{porcentaje:.2f}%")
            st.caption(
                f"{devueltos} de {total} solicitudes únicas tuvieron al menos un paso "
                "llamado «Devolver al solicitante». Cada solicitud se cuenta una sola vez."
            )
            st.subheader("Duración total por solicitud")
            promedio, minima, maxima = st.columns(3)
            promedio.metric("Promedio (días calendario)", f"{tiempos['promedio']:.2f}")
            minima.metric("Mínima (días calendario)", f"{tiempos['minima']:.2f}")
            maxima.metric("Máxima (días calendario)", f"{tiempos['maxima']:.2f}")
            st.caption(
                "Duración observada: último movimiento menos primer movimiento de cada caso. "
                "El promedio da el mismo peso a cada solicitud. Días de 24 horas, "
                "con fracciones, fines de semana y feriados; no implica que el caso esté cerrado."
            )
            if tiempos["un_movimiento"]:
                st.caption(
                    f"{tiempos['un_movimiento']} solicitudes tienen un solo movimiento: "
                    "su duración observada es 0 y no aportan intervalos de espera."
                )
            st.subheader("Espera promedio por paso")
            st.caption(
                "Espera = fecha y hora del movimiento menos la del anterior del mismo caso. "
                "Se atribuye al paso de llegada y se excluye el primer movimiento. "
                "El promedio incluye todas las apariciones de cada paso."
            )
            if esperas:
                cuellos = [fila["Paso"] for fila in esperas if fila["Cuello de botella"]]
                if cuellos:
                    st.warning(
                        "Cuello de botella por mayor espera promedio: "
                        + json.dumps(cuellos, ensure_ascii=False)
                        + f" · {esperas[0]['Espera promedio (días)']:.2f} días. "
                        "Es una señal para investigar; el intervalo puede incluir trabajo y espera."
                    )
                else:
                    st.info("Todos los intervalos son 0; no se distingue un cuello de botella.")
                st.dataframe(
                    esperas, hide_index=True, use_container_width=True,
                    column_config={
                        "Espera promedio (días)": st.column_config.NumberColumn(
                            "Espera promedio (días)", format="%.4f"
                        ),
                    },
                )
                with st.expander("Ver tiempos entre movimientos"):
                    st.dataframe(
                        detalle, hide_index=True, use_container_width=True,
                        column_config={
                            "Espera (días)": st.column_config.NumberColumn(
                                "Espera (días)", format="%.4f"
                            ),
                        },
                    )
            else:
                st.info("No hay casos con dos o más movimientos para calcular esperas.")

            st.subheader("Caminos reales del proceso")
            st.caption(
                "Cada lista muestra los pasos en orden cronológico. "
                "Se agrupan secuencias exactas, conservando pasos repetidos. "
                "El porcentaje se calcula sobre todas las solicitudes."
            )
            if empates:
                st.warning(
                    "Hay movimientos del mismo caso con igual fecha y hora. "
                    "En esos empates se conserva el orden de las filas del CSV."
                )
            st.dataframe(
                tabla, hide_index=True, use_container_width=True,
                column_config={
                    "Porcentaje (%)": st.column_config.NumberColumn(
                        "Porcentaje (%)", format="%.2f"
                    ),
                },
            )
            st.caption(f"{len(tabla)} caminos · {sum(f['Solicitudes'] for f in tabla)} solicitudes")


if __name__ == "__main__":
    main()
