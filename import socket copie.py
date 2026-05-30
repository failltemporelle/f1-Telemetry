import socket
import struct
import csv
import os
import datetime
import time

# Imports pour le WebSocket en temps réel
import asyncio
import websockets
import json
import threading

# Configuration UDP
UDP_IP = "0.0.0.0"
UDP_PORT = 20777

# Fichier CSV
CSV_FILE = "f1_telemetry.csv"
FIELDNAMES = ["Date", "Circuit", "Écurie", "Lap Time (s)", "Sector 1 (s)", "Sector 2 (s)", "Sector 3 (s)", "Max Speed (km/h)", "Gear R", "Gear N", "Gear 1", "Gear 2", "Gear 3", "Gear 4", "Gear 5", "Gear 6", "Gear 7", "Gear 8"]
# Vérifier si le fichier existe, sinon le créer avec les en-têtes
file_exists = os.path.isfile(CSV_FILE)
with open(CSV_FILE, mode="a", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
    if not file_exists:
        writer.writeheader()
# Fichier CSV Télémétrie LIVE (Moteur, Freinage, Positions...)
LIVE_CSV_FILE = "f1_live_telemetry.csv"
LIVE_FIELDNAMES = ["Time", "Lap", "Speed", "Gear", "RPM", "Throttle", "Brake", "Steer", "PosX", "PosY", "PosZ"]
live_file_exists = os.path.isfile(LIVE_CSV_FILE)
live_file = open(LIVE_CSV_FILE, mode="a", newline="")
live_writer = csv.DictWriter(live_file, fieldnames=LIVE_FIELDNAMES)
if not live_file_exists:
    live_writer.writeheader()


# --- SERVEUR WEBSOCKET ---
connected_clients = set()
ws_loop = None

async def ws_handler(websocket):
    # Désactive l'algorithme de Nagle : réduit la latence TCP de ~200 ms
    try:
        sock = websocket.transport.get_extra_info('socket')
        if sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)

HTTP_PORT = 7777

async def start_ws_server():
    global ws_loop
    ws_loop = asyncio.get_running_loop()
    async with websockets.serve(ws_handler, "0.0.0.0", 8080):
        await asyncio.Future()

def run_ws_server():
    asyncio.run(start_ws_server())

def run_http_server():
    import http.server, functools
    script_dir = os.path.dirname(os.path.abspath(__file__))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=script_dir)
    httpd = http.server.HTTPServer(("0.0.0.0", HTTP_PORT), handler)
    httpd.serve_forever()

ws_thread   = threading.Thread(target=run_ws_server,   daemon=True)
http_thread = threading.Thread(target=run_http_server, daemon=True)
ws_thread.start()
http_thread.start()

# ── Envoi WebSocket sans file d'attente ───────────────────────────────────
# Pour la télémétrie haute fréquence (60 Hz) on ne garde que le DERNIER
# paquet : si l'event-loop est légèrement en retard, les paquets intermédiaires
# sont simplement écrasés, pas empilés. On évite ainsi le décalage croissant.
_telem_lock      = threading.Lock()
_latest_telem    = [None]   # paquet le plus récent (telemetry / map_update)
_telem_scheduled = [False]  # True = un _flush déjà planifié dans la loop

def _flush_telem():
    """Appelé dans le thread asyncio. Envoie le dernier paquet et libère le slot."""
    with _telem_lock:
        msg = _latest_telem[0]
        _latest_telem[0]    = None
        _telem_scheduled[0] = False
    if msg and connected_clients:
        websockets.broadcast(connected_clients, msg)

def broadcast_telemetry(data_dict):
    """Envoie les données JSON en direct à tous les dashboards web connectés."""
    if ws_loop is None or not connected_clients:
        return

    msg_type = data_dict.get('type', '')
    message  = json.dumps(data_dict)

    if msg_type in ('telemetry', 'map_update'):
        # Haute fréquence : on écrase le paquet précédent, pas de file.
        with _telem_lock:
            _latest_telem[0] = message
            if not _telem_scheduled[0]:
                _telem_scheduled[0] = True
                ws_loop.call_soon_threadsafe(_flush_telem)
    else:
        # Événements rares (lap_summary, personal_best…) : envoi immédiat.
        clients = set(connected_clients)
        ws_loop.call_soon_threadsafe(websockets.broadcast, clients, message)
# -------------------------

# Création du socket UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

local_ip = socket.gethostbyname(socket.gethostname())
print(f"✅ Socket UDP prêt sur le port {UDP_PORT}.")
print(f"🌐 Dashboard accessible sur : http://{local_ip}:{HTTP_PORT}/dashboard.html")
print(f"📡 En attente des données de télémétrie F1...")

# Format du PacketHeader
PACKET_HEADER_FORMAT = "<HBBBBBQfII2B"
HEADER_SIZE = struct.calcsize(PACKET_HEADER_FORMAT)

# Format du PacketCarTelemetryData
CAR_TELEMETRY_SIZE = 60  # Taille standard pour un bloc "CarTelemetryData" sur F1 22 / F1 23

# La taille d'un bloc LapData varie selon la version du jeu (F1 22, 23, 24...)
# Nous la calculerons dyamiquement au lieu de la figer avec un calcsize inexact.


# Dictionnaires des circuits et écuries
TRACKS = {
    0: "Melbourne", 1: "Paul Ricard", 2: "Shanghai", 3: "Sakhir (Bahrain)",
    4: "Catalunya", 5: "Monaco", 6: "Montreal", 7: "Silverstone",
    8: "Hockenheim", 9: "Hungaroring", 10: "Spa", 11: "Monza",
    12: "Singapore", 13: "Suzuka", 14: "Abu Dhabi", 15: "Texas",
    16: "Brazil", 17: "Austria", 18: "Sochi", 19: "Mexico",
    20: "Baku (Azerbaijan)", 21: "Sakhir Short", 22: "Silverstone Short",
    23: "Texas Short", 24: "Suzuka Short", 25: "Hanoi", 26: "Zandvoort",
    27: "Imola", 28: "Portimão", 29: "Jeddah", 30: "Miami",
    31: "Las Vegas", 32: "Losail"
}

TEAMS = {
    0: "Mercedes", 1: "Ferrari", 2: "Red Bull Racing", 3: "Williams",
    4: "Aston Martin", 5: "Alpine", 6: "RB", 7: "Haas",
    8: "McLaren", 9: "Sauber", 41: "F1 Generic", 104: "F1 Custom Team",
    143: "Art GP '23", 144: "Campos '23", 145: "Carlin '23",
    146: "PHM '23", 147: "Dams '23", 148: "Hitech '23",
    149: "MP Motorsport '23", 150: "Prema '23", 151: "Trident '23",
    152: "Van Amersfoort Racing '23", 153: "Virtuosi '23"
}

WEATHER_MAP = {
    0: 'DÉGAGÉ', 1: 'LÉGÈRES NUAGES', 2: 'COUVERT',
    3: 'PLUIE LÉGÈRE', 4: 'PLUIE', 5: 'ORAGE'
}

SESSION_MAP = {
    0: 'INCONNU', 1: 'P1', 2: 'P2', 3: 'P3', 4: 'P COURT',
    5: 'Q1', 6: 'Q2', 7: 'Q3', 8: 'Q COURT', 9: 'SUPERPOLE',
    10: 'COURSE', 11: 'COURSE 2', 12: 'COURSE 3', 13: 'TIME TRIAL'
}

# visualTyreCompound byte → short code  (F1 23/24/25)
VISUAL_TYRE_MAP = { 16: 'S', 17: 'M', 18: 'H', 7: 'I', 8: 'W' }

# ersDeployMode byte → display string
ERS_MODE_NAMES = { 0: 'NONE', 1: 'MEDIUM', 2: 'HOTLAP', 3: 'OVERTAKE' }

# Full 60-byte CarTelemetryData struct format (F1 22 / 23 / 24 / 25)
# speed(H) throttle(f) steer(f) brake(f) clutch(B) gear(b) engineRPM(H)
# drs(B) revLightsPct(B) revLightsBit(H)
# brakesTemp[RL,RR,FL,FR](4H)  tyreSurfTemp[RL,RR,FL,FR](4B)
# tyreInnerTemp[RL,RR,FL,FR](4B)  engineTemp(H)
# tyrePressure[RL,RR,FL,FR](4f)  surfaceType[RL,RR,FL,FR](4B)
FULL_CAR_TELEM_FORMAT = "<HfffBbHBBH4H4B4BH4f4B"



# Format Time Trial (paquet ID 14)
TIME_TRIAL_SET_FORMAT = "<BBIIIIBBBBBB"
TIME_TRIAL_SET_SIZE = struct.calcsize(TIME_TRIAL_SET_FORMAT)

# Fonctions de formatage des temps
def ms_to_ss_mms(milliseconds):
    seconds = milliseconds // 1000
    ms = milliseconds % 1000
    return f"{seconds:02d}:{ms:03d}"

def ms_to_mm_ss_mms(milliseconds):
    minutes = milliseconds // 60000
    seconds = (milliseconds % 60000) // 1000
    ms = milliseconds % 1000
    return f"{minutes:02d}:{seconds:02d}:{ms:03d}"

def ms_to_delta(milliseconds):
    sign = "+" if milliseconds >= 0 else "-"
    ms = abs(milliseconds)
    s = ms // 1000
    ms = ms % 1000
    return f"{sign}{s}.{ms:03d}"

# Variables pour suivre les données
max_speed = 0
current_lap = 0
last_lap_time = 0
currents1 = 0
currents2 = 0
last_lap = 0
current_lap_time = 0
final_lap = 0
track_name = "Inconnu"
team_name = "Inconnu"
pos_x = 0.0
pos_y = 0.0
pos_z = 0.0
previous_gear = -2
gear_counts = { -1: 0, 0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0 }
last_map_time = 0

# ── Race / Status data  (updated from packet_id 7) ──────────────────────────
car_position        = 0
gap_ahead           = 0.0   # écart avec la voiture devant (secondes)
gap_behind          = 0.0   # écart avec la voiture derrière (secondes)
fuel_in_tank        = 0.0
fuel_remaining_laps = 0.0
drs_allowed         = 0
ers_pct             = 0.0
ers_mode_str        = '—'
tyre_compound       = 'M'
tyres_age_laps      = 0

# ── Brake / tyre temps  (updated from packet_id 6, 60 Hz) ───────────────────
brake_fl = 0; brake_fr = 0; brake_rl = 0; brake_rr = 0
tyre_fl  = 0; tyre_fr  = 0; tyre_rl  = 0; tyre_rr  = 0
engine_temp = 0
drs_active  = 0

# ── Session info  (updated from packet_id 1) ────────────────────────────────
track_temp   = 0
air_temp     = 0
weather_str  = '—'
session_type = '—'

# Record personnel (Time Trial - paquet ID 14)
pb_lap_ms = 0
pb_s1_ms = 0
pb_s2_ms = 0
pb_s3_ms = 0



try:
    first_packet_received = False
    print("🟢 Prêt à traiter les paquets. N'oubliez pas d'activer la télémétrie UDP dans le jeu F1 !")
    while True:
        data, addr = sock.recvfrom(2048)
        data_length = len(data)

        if not first_packet_received:
            print(f"\n🎉 SUCCÈS ! Première donnée reçue de {addr} (Taille: {data_length} octets).")
            print("🚀 La connexion est bien fonctionnelle et les données arrivent ! \n")
            first_packet_received = True

        # Log pour vérifier chaque paquet (à décommenter si besoin, mais attention la console va défiler très vite !)
        # print(f"📦 Paquet de {data_length} octets reçu de {addr}")

        if data_length < HEADER_SIZE:
            continue  # Paquet trop court

        # Lecture du header
        header = struct.unpack(PACKET_HEADER_FORMAT, data[:HEADER_SIZE])
        (
            packet_format, game_year, major_ver, minor_ver, 
            packet_ver, packet_id, session_uid, session_time, 
            frame_id, overall_frame_id, player_car_index, secondary_car_index
        ) = header

        # Décommentez la ligne suivante pour voir les ID des paquets correctement traités en direct
        # print(f"🔍 Traitement du paquet ID: {packet_id} (Temps de session: {session_time:.2f}s)")

        if packet_id == 0:  # PacketMotionData
            offset = HEADER_SIZE + (player_car_index * 60)
            # Extrait les 3 floats (worldPositionX, worldPositionY, worldPositionZ)
            pos_x, pos_y, pos_z = struct.unpack_from("<fff", data, offset)

            # --- Mini-Map Throttling 10Hz ---
            current_time_sec = time.time()
            if current_time_sec - last_map_time >= 0.1:  # 10 updates / sec
                map_data = {
                    "type": "map_update",
                    "x": round(pos_x, 3),
                    "z": round(pos_z, 3)
                }
                broadcast_telemetry(map_data)
                last_map_time = current_time_sec

        elif packet_id == 6:  # PacketCarTelemetryData
            # Extraction des données du joueur
            offset = HEADER_SIZE + (player_car_index * CAR_TELEMETRY_SIZE)

            # Unpack du struct complet de 60 octets (F1 22/23/24/25)
            try:
                car_data = struct.unpack_from(FULL_CAR_TELEM_FORMAT, data, offset)
            except struct.error:
                # Paquet trop court : on se rabat sur le sous-ensemble minimal
                car_data = struct.unpack_from("<HfffBbH", data, offset) + (0,) * 24

            speed    = car_data[0]   # Vitesse en km/h
            throttle = car_data[1]   # Accélération (0.0 à 1.0)
            steer    = car_data[2]   # Direction (-1.0 à 1.0)
            brake    = car_data[3]   # Freinage (0.0 à 1.0)
            clutch   = car_data[4]   # Embrayage (0 à 100)
            gear     = car_data[5]   # Rapport de boîte
            rpm      = car_data[6]   # Régime moteur

            # Champs étendus (indices 7-22)
            drs_active  = car_data[7]
            # brakesTemperature wheel order: [10]=RL [11]=RR [12]=FL [13]=FR
            brake_rl = car_data[10]; brake_rr = car_data[11]
            brake_fl = car_data[12]; brake_fr = car_data[13]
            # tyreSurfaceTemperature wheel order: [14]=RL [15]=RR [16]=FL [17]=FR
            tyre_rl = car_data[14]; tyre_rr = car_data[15]
            tyre_fl = car_data[16]; tyre_fr = car_data[17]
            engine_temp = car_data[22]

            # Logique de comptage des rapports
            if gear != previous_gear:
                if gear in gear_counts:
                    gear_counts[gear] += 1
                previous_gear = gear

            max_speed = max(max_speed, speed)  # Mettre à jour la vitesse max

            # Affichage en temps réel avec \r (Refresh live sans spammer la console)
            print(f"\r🏎️  {speed:3d}km/h G{gear} {rpm:5d}rpm Acc{throttle*100:3.0f}% Fr{brake*100:3.0f}%"
                  f" | 🌡️ PnFL:{tyre_fl}° PnFR:{tyre_fr}° PnRL:{tyre_rl}° PnRR:{tyre_rr}° Mot:{engine_temp}°"
                  f" | P{car_position} +{gap_ahead:.3f}s -{gap_behind:.3f}s"
                  f" | ERS:{ers_pct:.0f}% Carbu:{fuel_in_tank:.1f}kg [{tyre_compound}]",
                  end="", flush=True)
            
            # Enregistrement dans le CSV Live (à haute fréquence, typiquement 20 ou 60 Hz)
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            live_data = {
                "type": "telemetry",
                "Time": current_time,
                "Lap": current_lap,
                "Speed": speed,
                "Gear": gear,
                "RPM": rpm,
                "Throttle": round(throttle, 3),
                "Brake": round(brake, 3),
                "Steer": round(steer, 3),
                "PosX": round(pos_x, 3),
                "PosY": round(pos_y, 3),
                "PosZ": round(pos_z, 3),
                "Track": track_name,
                "Team": team_name,
                # ── Télémétrie étendue (packet 6) ─────────────────────────
                "DRS":     bool(drs_active),
                "BrakeFL": brake_fl, "BrakeFR": brake_fr,
                "BrakeRL": brake_rl, "BrakeRR": brake_rr,
                "TyreFL":  {"temp": tyre_fl, "wear": 0, "compound": tyre_compound},
                "TyreFR":  {"temp": tyre_fr, "wear": 0, "compound": tyre_compound},
                "TyreRL":  {"temp": tyre_rl, "wear": 0, "compound": tyre_compound},
                "TyreRR":  {"temp": tyre_rr, "wear": 0, "compound": tyre_compound},
                "EngineTemp": engine_temp,
                # ── Statut voiture (packet 7) ─────────────────────────────
                "Position":   car_position,
                "GapAhead":   gap_ahead,
                "GapBehind":  gap_behind,
                "Fuel":       round(fuel_in_tank, 2),
                "FuelLaps": round(fuel_remaining_laps, 1),
                "ERS":      round(ers_pct, 1),
                "ERSMode":  ers_mode_str,
                # ── Session (packet 1) ────────────────────────────────────
                "TrackTemp":   track_temp,
                "AirTemp":     air_temp,
                "Weather":     weather_str,
                "SessionType": session_type,
            }
            
            # On retire les clefs absentes du CSV Live avant l'écriture
            csv_live_data = {k: live_data[k] for k in LIVE_FIELDNAMES}
            
            # Diffusion WebSockets en temps réel
            broadcast_telemetry(live_data)
            
        elif packet_id == 1:  # PacketSessionData
            weather_id   = struct.unpack_from("<B", data, HEADER_SIZE + 0)[0]
            track_temp   = struct.unpack_from("<b", data, HEADER_SIZE + 1)[0]
            air_temp     = struct.unpack_from("<b", data, HEADER_SIZE + 2)[0]
            session_id   = struct.unpack_from("<B", data, HEADER_SIZE + 6)[0]
            track_id     = struct.unpack_from("<b", data, HEADER_SIZE + 7)[0]
            weather_str  = WEATHER_MAP.get(weather_id, '—')
            session_type = SESSION_MAP.get(session_id, '—')
            track_name   = TRACKS.get(track_id, "Inconnu")
        
        elif packet_id == 4:  # PacketParticipantsData - Récupérer l'écurie du joueur
            participant_offset = HEADER_SIZE + 1 + (player_car_index * 54)  # Offset pour l'équipe
            team_id = struct.unpack_from("B", data, participant_offset + 3)[0]
            team_name = TEAMS.get(team_id, "Inconnu")
            
        

        elif packet_id == 2:
            # Détermination de la taille du LapData et des offsets selon le jeu
            # Offset du delta devant (deltaToCarInFrontInMS, uint16) dans le struct LapData :
            #   F1 24/25 : offset 14  (sector2TimeMinutes byte ajouté avant)
            #   F1 23    : offset 13  (pas de sector2TimeMinutes)
            #   F1 22    : offset 12  (pas de sector1/2TimeMinutes)
            if game_year in (24, 25):
                lap_data_size  = 57
                s2_offset      = 11
                lap_num_offset = 33
                delta_offset   = 14
            elif game_year == 23:
                lap_data_size  = 50
                s2_offset      = 11
                lap_num_offset = 31
                delta_offset   = 13
            else:
                lap_data_size  = 43
                s2_offset      = 10
                lap_num_offset = 25
                delta_offset   = 12

            offset = HEADER_SIZE + (player_car_index * lap_data_size)

            # Utilisation d'offsets exacts de la documentation F1 pour éviter les erreurs de format (décalages de bytes)
            last_lap_time_ms = struct.unpack_from("<I", data, offset)[0]
            current_lap_time_ms = struct.unpack_from("<I", data, offset + 4)[0]
            sector_1_time_ms = struct.unpack_from("<H", data, offset + 8)[0]
            sector_2_time_ms = struct.unpack_from("<H", data, offset + s2_offset)[0]
            current_lap_number = struct.unpack_from("<B", data, offset + lap_num_offset)[0]

            current_lap  = current_lap_number  # Mise à jour de la variable globale pour le Dashboard et CSV Live
            car_position = struct.unpack_from("<B", data, offset + lap_num_offset - 1)[0]

            # ── Calcul des écarts (gap ahead / gap behind) ───────────────────
            # Écart avec la voiture devant (champ deltaToCarInFrontInMS du joueur)
            raw_ahead = struct.unpack_from("<H", data, offset + delta_offset)[0]
            gap_ahead = round(raw_ahead / 1000.0, 3)

            # Écart derrière = deltaToCarInFrontInMS de la voiture qui est en
            # (car_position + 1), c'est-à-dire le pilote directement derrière.
            gap_behind = 0.0
            if car_position > 0:                        # 0 = données indisponibles
                max_cars = min(22, (len(data) - HEADER_SIZE) // lap_data_size)
                for ci in range(max_cars):
                    ci_off = HEADER_SIZE + (ci * lap_data_size)
                    if ci_off + lap_data_size > len(data):
                        break
                    ci_pos = struct.unpack_from("<B", data, ci_off + lap_num_offset - 1)[0]
                    if ci_pos == car_position + 1:
                        raw_behind = struct.unpack_from("<H", data, ci_off + delta_offset)[0]
                        gap_behind = round(raw_behind / 1000.0, 3)
                        break
            
            today_date = datetime.datetime.now().strftime("%d/%m/%Y")
            
            if sector_1_time_ms != 0: 
                currents1 = sector_1_time_ms 
                current_lap_time = current_lap_number 
                
            if sector_2_time_ms !=0: 
                currents2 = sector_2_time_ms 
                
            if current_lap_time < current_lap_number and current_lap_time != 0: 
                sector_3_time_ms = last_lap_time_ms - (currents1 + currents2)  # Secteur 3 calculé
                final_lap = currents1 + currents2 + sector_3_time_ms
                print(f"\n🏁 TIME: {final_lap} S1: {currents1}s | S2: {currents2}s | S3: {sector_3_time_ms}s | 🚀 Vitesse max : {max_speed} km/h")
                
                # --- Écriture CSV ---
                with open(CSV_FILE, mode="a", newline="") as file:
                        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
                        writer.writerow(
                            {
                                "Date": today_date,
                                "Circuit": track_name,
                                "Écurie": team_name,
                                "Lap Time (s)": ms_to_mm_ss_mms(last_lap_time_ms),
                                "Sector 1 (s)": ms_to_ss_mms(currents1),
                                "Sector 2 (s)": ms_to_ss_mms(currents2),
                                "Sector 3 (s)": ms_to_ss_mms(sector_3_time_ms),
                                "Max Speed (km/h)": max_speed,
                                "Gear R": gear_counts.get(-1, 0),
                                "Gear N": gear_counts.get(0, 0),
                                "Gear 1": gear_counts.get(1, 0),
                                "Gear 2": gear_counts.get(2, 0),
                                "Gear 3": gear_counts.get(3, 0),
                                "Gear 4": gear_counts.get(4, 0),
                                "Gear 5": gear_counts.get(5, 0),
                                "Gear 6": gear_counts.get(6, 0),
                                "Gear 7": gear_counts.get(7, 0),
                                "Gear 8": gear_counts.get(8, 0)
                            }
                        )
                
                # --- Calcul deltas vs Record Personnel ---
                is_new_pb = pb_lap_ms > 0 and last_lap_time_ms < pb_lap_ms
                delta_lap  = ms_to_delta(last_lap_time_ms - pb_lap_ms) if pb_lap_ms > 0 else None
                delta_s1   = ms_to_delta(currents1 - pb_s1_ms)         if pb_s1_ms > 0 else None
                delta_s2   = ms_to_delta(currents2 - pb_s2_ms)         if pb_s2_ms > 0 else None
                delta_s3   = ms_to_delta(sector_3_time_ms - pb_s3_ms)  if pb_s3_ms > 0 else None

                if is_new_pb:
                    pb_lap_ms = last_lap_time_ms
                    pb_s1_ms  = currents1
                    pb_s2_ms  = currents2
                    pb_s3_ms  = sector_3_time_ms

                # --- Envoi au Dashboard WS ---
                lap_summary_data = {
                    "type": "lap_summary",
                    "LapNumber": current_lap_number - 1,
                    "LapTime": ms_to_mm_ss_mms(last_lap_time_ms),
                    "Sector1": ms_to_ss_mms(currents1),
                    "Sector2": ms_to_ss_mms(currents2),
                    "Sector3": ms_to_ss_mms(sector_3_time_ms),
                    "MaxSpeed": max_speed,
                    "Gears": dict(gear_counts),
                    "Track": track_name,
                    "Team": team_name,
                    "DeltaLap": delta_lap,
                    "DeltaS1": delta_s1,
                    "DeltaS2": delta_s2,
                    "DeltaS3": delta_s3,
                    "IsNewPB": is_new_pb
                }
                broadcast_telemetry(lap_summary_data)

                # Réinitialisation
                final_lap = 0
                currents1 = 0
                currents2 = 0
                current_lap_time = 0
                max_speed = 0
                gear_counts = { -1: 0, 0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0 }

        elif packet_id == 7:  # PacketCarStatusData
            # Taille du struct CarStatusData par voiture selon l'année du jeu
            # F1 24/25 : 55 octets (2 floats enginePower ajoutés avant ERS)
            # F1 23 et antérieur : 47 octets
            if game_year in (24, 25):
                car_status_size  = 55
                ers_store_offset = 37   # offset dans le struct du joueur
                ers_mode_offset  = 41
            else:
                car_status_size  = 47
                ers_store_offset = 29
                ers_mode_offset  = 33

            st_off = HEADER_SIZE + (player_car_index * car_status_size)
            if len(data) >= st_off + car_status_size:
                fuel_in_tank        = struct.unpack_from("<f", data, st_off +  5)[0]
                fuel_remaining_laps = struct.unpack_from("<f", data, st_off + 13)[0]
                drs_allowed         = struct.unpack_from("<B", data, st_off + 22)[0]
                visual_cmp          = struct.unpack_from("<B", data, st_off + 26)[0]
                tyres_age_laps      = struct.unpack_from("<B", data, st_off + 27)[0]
                ers_raw             = struct.unpack_from("<f", data, st_off + ers_store_offset)[0]
                ers_deploy          = struct.unpack_from("<B", data, st_off + ers_mode_offset)[0]

                ers_pct      = round(min(100.0, ers_raw / 4_000_000 * 100), 1)
                ers_mode_str = ERS_MODE_NAMES.get(ers_deploy, '—')
                tyre_compound = VISUAL_TYRE_MAP.get(visual_cmp, 'M')

        elif packet_id == 14:  # PacketTimeTrialData - Record Personnel
            pb_offset = HEADER_SIZE + TIME_TRIAL_SET_SIZE
            if len(data) >= pb_offset + TIME_TRIAL_SET_SIZE:
                pb_raw = struct.unpack_from(TIME_TRIAL_SET_FORMAT, data, pb_offset)
                (_, _, lap_ms, s1_ms, s2_ms, s3_ms, _, _, _, _, _, pb_valid) = pb_raw
                if pb_valid and lap_ms > 0:
                    pb_lap_ms = lap_ms
                    pb_s1_ms  = s1_ms
                    pb_s2_ms  = s2_ms
                    pb_s3_ms  = s3_ms
                    broadcast_telemetry({
                        "type": "personal_best",
                        "LapTime": ms_to_mm_ss_mms(pb_lap_ms),
                        "Sector1": ms_to_ss_mms(pb_s1_ms),
                        "Sector2": ms_to_ss_mms(pb_s2_ms),
                        "Sector3": ms_to_ss_mms(pb_s3_ms)
                    })

except KeyboardInterrupt:
    print("\n🛑 Arrêt du script.")
    live_file.flush()
    live_file.close()
    sock.close()