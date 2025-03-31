import csv
import requests
from collections import defaultdict
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render

# Tu clave de API de IPInfo
API_KEY = '3b5c89838fc09c'

# Variable global para almacenar el estado del procesamiento
processing_state = {
    "total_ips": 0,
    "processed_ips": 0,
    "current_ip": "",
    "progress": 0,
    "completed": False,
}

# Función para validar si una cadena es una dirección IP válida
def is_valid_ip(ip):
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit() or not 0 <= int(part) <= 255:
            return False
    return True

# Vista para obtener el estado del procesamiento
@csrf_exempt
def get_processing_status(request):
    return JsonResponse(processing_state)

# Vista principal para cargar el archivo CSV
@csrf_exempt
def upload_csv(request):
    if request.method == 'POST':
        # Obtener el archivo cargado
        uploaded_file = request.FILES.get('csv_file')
        if not uploaded_file:
            return JsonResponse({'error': 'No se ha subido ningún archivo.'}, status=400)

        try:
            # Leer el archivo CSV cargado
            decoded_file = uploaded_file.read().decode('utf-8').splitlines()
            reader = csv.reader(decoded_file)

            # Extraer las IPs válidas (sin duplicados)
            ips = set()
            invalid_rows = []  # Para almacenar mensajes de error específicos
            row_count = 0

            for row in reader:
                row_count += 1
                try:
                    # Verificar que la fila tenga al menos 2 columnas
                    if len(row) < 2:
                        invalid_rows.append(f"Fila {row_count}: Fila incompleta ignorada ({row}).")
                        continue

                    # Obtener la IP de la segunda columna
                    ip = row[1].strip()

                    # Detectar si la fila es una cabecera
                    if ip.lower() in ['ip', 'ip address', 'email']:
                        print(f"Fila {row_count}: Cabecera detectada y omitida ({ip}).")
                        continue

                    # Validar la IP
                    if not ip or '@' in ip or not is_valid_ip(ip):
                        invalid_rows.append(f"Fila {row_count}: IP inválida o correo electrónico ignorado ({ip}).")
                        continue

                    # Agregar la IP válida al conjunto
                    ips.add(ip)
                except Exception as e:
                    invalid_rows.append(f"Fila {row_count}: Error al procesar fila ({row}): {str(e)}")

            print(f"IPs válidas encontradas (sin duplicados): {ips}")
            total_ips = len(ips)
            print(f"Total de IPs válidas para procesar: {total_ips}")

            # Actualizar el estado inicial del procesamiento
            processing_state["total_ips"] = total_ips
            processing_state["processed_ips"] = 0
            processing_state["current_ip"] = ""
            processing_state["progress"] = 0
            processing_state["completed"] = False

            # Consultar la API de IPInfo para obtener datos geográficos
            results = []
            county_frequency = defaultdict(int)  # Diccionario para contar frecuencia de condados
            processed_ips = 0

            for ip in ips:
                processed_ips += 1
                try:
                    print(f"Consultando API para la IP {ip}... ({processed_ips}/{total_ips})")
                    url = f'https://ipinfo.io/{ip}?token={API_KEY}'
                    response = requests.get(url)
                    data = response.json()

                    city = data.get('city', '')
                    region = data.get('region', '')
                    zip_code = data.get('postal', '')
                    loc = data.get('loc', ',').split(',')
                    lat = loc[0] if len(loc) > 0 else ''
                    long = loc[1] if len(loc) > 1 else ''

                    # Intentar obtener el condado desde el campo 'county' o inferirlo
                    county = data.get('county', '') or region  # Usar 'region' como fallback
                    county_frequency[county] += 1  # Incrementar la frecuencia del condado

                    results.append([ip, city, region, county, zip_code, lat, long])
                    print(f"Datos obtenidos para la IP {ip}: {city}, {region}, {county}, {zip_code}, {lat}, {long}")
                except Exception as e:
                    print(f"Error al procesar la IP {ip}: {e}")
                    results.append([ip, '', '', '', '', '', ''])

                # Actualizar el estado del procesamiento
                processing_state["processed_ips"] = processed_ips
                processing_state["current_ip"] = ip
                processing_state["progress"] = int((processed_ips / total_ips) * 100)

            # Marcar como completado
            processing_state["completed"] = True

            # Crear un archivo CSV con los resultados
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="processed_results.csv"'
            writer = csv.writer(response)

            # Escribir la cabecera
            writer.writerow(['Número de IP', 'Ciudad', 'Estado', 'Condado', 'Código Postal', 'Latitud', 'Longitud'])
            writer.writerows(results)

            print("Proceso completado. El archivo 'processed_results.csv' ha sido creado.")

            # Incluir un resumen de errores y frecuencia de condados en la respuesta JSON
            summary = {
                'message': 'Archivo procesado con éxito.',
                'county_frequency': dict(county_frequency),  # Convertir defaultdict a dict
            }
            if invalid_rows:
                error_summary = "Se encontraron errores en las siguientes filas:\n" + "\n".join(invalid_rows)
                print(error_summary)
                summary['errors'] = error_summary

            # Devolver el archivo CSV directamente para la autodescarga
            return response
        except Exception as e:
            print(f"Error general: {str(e)}")
            return JsonResponse({'error': str(e)}, status=400)

    # Si no es una solicitud POST, renderiza la página principal
    return render(request, 'upload.html')