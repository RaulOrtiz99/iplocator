"""
upload_csv.py  – Vista Django para procesar un CSV de IPs
- Omite la columna “Condado”.
- Añade columna “Frecuencia de visita”.
- Devuelve un CSV con resultados y un resumen de frecuencias.
"""

import csv
import ipaddress
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Tuple

import requests
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

API_KEY = "3b5c89838fc09c"
IPINFO_URL = "https://ipinfo.io/{ip}?token={token}"

# --- Estado global de progreso (lo consumes desde /status) ------------------ #
processing_state = {
    "total_ips": 0,
    "processed_ips": 0,
    "current_ip": "",
    "progress": 0,
    "completed": False,
}


# --------------------------------------------------------------------------- #
# Utilidades                                                                  #
# --------------------------------------------------------------------------- #
def is_valid_ip(ip: str) -> bool:
    """Valida IPv4 pública (descarta privadas/reservadas)."""
    try:
        addr = ipaddress.ip_address(ip)
        return addr.version == 4 and not (addr.is_private or addr.is_reserved)
    except ValueError:
        return False


def extract_unique_ips(rows: Iterable[list[str]]) -> Tuple[set[str], list[str]]:
    """Devuelve (ips_únicas, lista_de_errores) a partir de un iterable de filas."""
    ips, errors = set(), []
    for idx, row in enumerate(rows, start=1):
        if len(row) < 2:
            errors.append(f"Fila {idx}: incompleta → {row}")
            continue

        candidate = row[1].strip()
        # Cabeceras típicas
        if candidate.lower() in {"ip", "ip address", "email"}:
            continue
        if "@" in candidate or not is_valid_ip(candidate):
            errors.append(f"Fila {idx}: IP inválida/ignorada → {candidate}")
            continue

        ips.add(candidate)
    return ips, errors


def fetch_geo(ip: str) -> dict:
    """Consulta ipinfo y devuelve los campos de interés (maneja excepciones)."""
    try:
        r = requests.get(IPINFO_URL.format(ip=ip, token=API_KEY), timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        # Si falla, devolvemos dict vacío; el llamador decide qué hacer.
        return {}


# --------------------------------------------------------------------------- #
# End‑points                                                                  #
# --------------------------------------------------------------------------- #
@csrf_exempt
def get_processing_status(request):
    return JsonResponse(processing_state)


@csrf_exempt
def upload_csv(request):
    if request.method != "POST":
        return render(request, "upload.html")

    file = request.FILES.get("csv_file")
    if not file:
        return JsonResponse({"error": "No se subió ningún archivo."}, status=400)

    # -------------------- 1. Lectura CSV y filtrado de IPs ------------------ #
    decoded = file.read().decode("utf‑8").splitlines()
    ips, row_errors = extract_unique_ips(csv.reader(decoded))

    processing_state.update(
        total_ips=len(ips),
        processed_ips=0,
        current_ip="",
        progress=0,
        completed=False,
    )

    # -------------------- 2. Consulta ipinfo y construcción ----------------- #
    results: list[list[str]] = []
    location_freq: defaultdict[str, int] = defaultdict(int)

    for n, ip in enumerate(ips, start=1):
        geo = fetch_geo(ip)

        city = geo.get("city", "")
        region = geo.get("region", "")
        postal = geo.get("postal", "")
        lat, lon = ("", "")
        if loc := geo.get("loc", ""):
            lat, lon = (loc.split(",") + [""])[:2]

        location_key = f"{city}, {region}"
        location_freq[location_key] += 1
        freq = location_freq[location_key]

        results.append([ip, city, region, postal, lat, lon, str(freq)])

        # Progreso en caliente
        processing_state.update(
            processed_ips=n,
            current_ip=ip,
            progress=int(n / len(ips) * 100),
        )

    processing_state["completed"] = True

    # -------------------- 3. Respuesta CSV (stream) ------------------------- #
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=processed_results.csv"
    writer = csv.writer(response)

    # Cabecera SIN “Condado” + frecuencia
    writer.writerow(
        [
            "IP",
            "Ciudad",
            "Estado/Región",
            "Código Postal",
            "Latitud",
            "Longitud",
            "Frecuencia de Visita",
        ]
    )
    writer.writerows(results)

    # Espacio + tabla de frecuencias
    writer.writerow([])
    writer.writerow(["Análisis de Frecuencia por Lugar"])
    writer.writerow(["Lugar (Ciudad, Región)", "Visitas"])
    for place, count in sorted(location_freq.items(), key=lambda x: x[1], reverse=True):
        writer.writerow([place, count])

    # -------------------- 4. Errores opcionales ----------------------------- #
    if row_errors:
        writer.writerow([])
        writer.writerow(["Errores de Parsing"])
        writer.writerows([[err] for err in row_errors])

    return response


print("pruebas finalizadas")