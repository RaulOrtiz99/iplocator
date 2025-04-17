import csv
import ipaddress
from collections import defaultdict
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
# Funciones utilitarias                                                       #
# --------------------------------------------------------------------------- #
def is_valid_ip(ip: str) -> bool:
    """Valida IPv4 pública (descarta privadas/reservadas)."""
    try:
        addr = ipaddress.ip_address(ip)
        return addr.version == 4 and not (addr.is_private or addr.is_reserved)
    except ValueError:
        return False

def extract_unique_ips(rows: Iterable[list[str]]) -> Tuple[set[str], list[str]]:
    """Extrae IPs válidas y devuelve un conjunto y una lista de errores (si los hay)."""
    ips, errors = set(), []
    for idx, row in enumerate(rows, start=1):
        if len(row) < 2:
            errors.append(f"Fila {idx}: incompleta → {row}")
            continue

        candidate = row[1].strip()
        # Omitir cabeceras comunes
        if candidate.lower() in {"ip", "ip address", "email"}:
            print(f"Fila {idx}: cabecera detectada, se ignora: {candidate}")
            continue
        if "@" in candidate or not is_valid_ip(candidate):
            errors.append(f"Fila {idx}: IP inválida/ignorada → {candidate}")
            continue

        ips.add(candidate)
    return ips, errors

def fetch_geo(ip: str) -> dict:
    """Consulta a ipinfo.io y devuelve los datos de geolocalización para la IP."""
    try:
        r = requests.get(IPINFO_URL.format(ip=ip, token=API_KEY), timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error al consultar {ip}: {e}")
        return {}

# --------------------------------------------------------------------------- #
# End‑points                                                                  #
# --------------------------------------------------------------------------- #
@csrf_exempt
def get_processing_status(request):
    """Devuelve el estado de procesamiento como JSON."""
    return JsonResponse(processing_state)

@csrf_exempt
def upload_csv(request):
    """Recibe un archivo CSV, filtra las IPs, obtiene geolocalización y genera un CSV de salida."""
    if request.method != "POST":
        return render(request, "upload.html")

    file = request.FILES.get("csv_file")
    if not file:
        return JsonResponse({"error": "No se subió ningún archivo."}, status=400)

    # -------------------- 1. Leer el CSV y filtrar IPs ---------------------- #
    decoded = file.read().decode("utf-8").splitlines()
    ips, row_errors = extract_unique_ips(csv.reader(decoded))
    
    total = len(ips)
    print(f"Total de IPs válidas sin duplicados: {total}")
    processing_state.update(
        total_ips=total,
        processed_ips=0,
        current_ip="",
        progress=0,
        completed=False,
    )

    # -------------------- 2. Consultar ipinfo y construir datos ------------ #
    results = []  # Para IPs
    location_freq = defaultdict(int)  # Para conteo de visitas por estado/región

    # Recorrer IPs, pedir datos y acumular frecuencias
    for n, ip in enumerate(ips, start=1):
        print(f"Procesando IP {ip} ({n}/{total})...")
        geo = fetch_geo(ip)

        # Extraer campos de geolocalización
        city = geo.get("city", "")
        region = geo.get("region", "")
        postal = geo.get("postal", "")
        lat, lon = ("", "")
        if (loc := geo.get("loc", "")):
            lat, lon = (loc.split(",") + [""])[:2]

        # Usar solo el estado/región (no ciudad) para el conteo como en la imagen
        if region:  # Solo contamos si hay región/estado
            location_freq[region] += 1

        # Construir fila de IPs
        results.append([ip, city, region, postal, lat, lon, ""])

        # Consola: Progreso
        processing_state.update(
            processed_ips=n,
            current_ip=ip,
            progress=int(n / total * 100),
        )
        print(f"Progreso: {processing_state['progress']}% - {n} procesadas, {total - n} restantes.")
    
    processing_state["completed"] = True
    print("Procesamiento finalizado.")

    # -------------------- 3. Generar CSV de Respuesta ----------------------- #
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="processed_results.csv"'
    writer = csv.writer(response)

    # Cabecera
    writer.writerow([
        "IP",
        "Ciudad",
        "Estado/Región",
        "Código Postal",
        "Latitud",
        "Longitud",
        "Frecuencia de Visita"
    ])
    writer.writerows(results)

    # Espacio
    writer.writerow([])

    # Sección final EXACTAMENTE como en la imagen
    writer.writerow(["Análisis de Frecuencia por Ciudad"])  # Cambiado de "Condado" a "Ciudad"
    writer.writerow(["Ciudad", "Frecuencia"])  # Cambiado de "Condado" a "Ciudad"
    
    # Ordenar por frecuencia descendente y escribir
    for condado, freq in sorted(location_freq.items(), key=lambda x: x[1], reverse=True):
        writer.writerow([condado, freq])

    # Si hubo errores de parsing, los agregamos al final
    if row_errors:
        writer.writerow([])
        writer.writerow(["Errores de Parsing"])
        writer.writerows([[err] for err in row_errors])

    return response  

print("le agregue un ptrintaso") 