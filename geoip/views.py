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
    """Consulta a ipinfo y devuelve los datos de geolocalización para la IP."""
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
    return JsonResponse(processing_state)

@csrf_exempt
def upload_csv(request):
    if request.method != "POST":
        return render(request, "upload.html")

    file = request.FILES.get("csv_file")
    if not file:
        return JsonResponse({"error": "No se subió ningún archivo."}, status=400)

    # -------------------- 1. Lectura CSV y filtrado de IPs -------------------- #
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

    # -------------------- 2. Consulta a ipinfo y recolección de datos ------------ #
    results: list[list[str]] = []
    location_freq: defaultdict[str, int] = defaultdict(int)
    
    for n, ip in enumerate(ips, start=1):
        print(f"Procesando IP {ip} ({n}/{total})...")
        geo = fetch_geo(ip)
        
        # Extraer campos con default a cadena vacía si no existen
        city = geo.get("city", "")
        region = geo.get("region", "")
        postal = geo.get("postal", "")
        lat, lon = ("", "")
        if (loc := geo.get("loc", "")):
            lat, lon = (loc.split(",") + [""])[:2]
        
        # Utilizar combinación ciudad – región para frecuencia de visitas
        location_key = f"{city}, {region}"
        location_freq[location_key] += 1
        freq = location_freq[location_key]
        
        results.append([ip, city, region, postal, lat, lon, str(freq)])
        print(f"Datos para {ip}: {city}, {region}, {postal}, {lat}, {lon}, Frecuencia: {freq}")
        
        # Actualizar el estado global y mostrar en consola
        processing_state.update(
            processed_ips=n,
            current_ip=ip,
            progress=int(n / total * 100),
        )
        print(f"Progreso: {processing_state['progress']}% - {n} procesadas, {total - n} restantes.")
    
    processing_state["completed"] = True
    print("Procesamiento finalizado.")

    # -------------------- 3. Respuesta CSV (stream) ----------------------------- #
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=processed_results.csv"
    writer = csv.writer(response)
    
    # Escribir cabecera sin la columna de condado, pero con frecuencia
    writer.writerow([
        "IP",
        "Ciudad",
        "Estado/Región",
        "Código Postal",
        "Latitud",
        "Longitud",
        "Frecuencia de Visita",
    ])
    writer.writerows(results)
    
    # Espacio y tabla de frecuencias, ordenado por condado y frecuencia
    writer.writerow([])
    writer.writerow(["Análisis de Frecuencia por Condado"])
    writer.writerow(["Condado", "Frecuencia"])
    for place, count in sorted(location_freq.items(), key=lambda x: x[1], reverse=True):
        writer.writerow([place, count])
    
    # Incluir errores de parsing (opcional)
    if row_errors:
        writer.writerow([])
        writer.writerow(["Errores de Parsing"])
        writer.writerows([[err] for err in row_errors])
    
    return response

print("Pruebas finalizadas")
