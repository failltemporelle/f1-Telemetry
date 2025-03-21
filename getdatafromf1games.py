import socket
import struct
import csv
import os
import datetime

# Configuration UDP
UDP_IP = "0.0.0.0"
UDP_PORT = 20777

# Fichier CSV
CSV_FILE = "f1_telemetry.csv"
FIELDNAMES = ["Date", "Circuit", "Écurie", "Lap Time (s)", "Sector 1 (s)", "Sector 2 (s)", "Sector 3 (s)", "Max Speed (km/h)"]
# Vérifier si le fichier existe, sinon le créer avec les en-têtes
file_exists = os.path.isfile(CSV_FILE)
with open(CSV_FILE, mode="a", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
    if not file_exists:
        writer.writeheader()

# Création du socket UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print(f"📡 En attente des données de télémétrie sur {UDP_IP}:{UDP_PORT}...")

# Format du PacketHeader
PACKET_HEADER_FORMAT = "<HBBBBBQfII2B"
HEADER_SIZE = struct.calcsize(PACKET_HEADER_FORMAT)

# Format du PacketCarTelemetryData
CAR_TELEMETRY_FORMAT = "<HffffBbhHBBHHHHBBBBHHHBBBB"
CAR_TELEMETRY_SIZE = struct.calcsize(CAR_TELEMETRY_FORMAT)

# Format du PacketLapData (corrigé pour respecter ton fichier)
LAP_DATA_FORMAT = "<I I H B H B H B H B f f f B B B B B B B B B B B B B B B B B H H B f B"
LAP_DATA_SIZE = struct.calcsize(LAP_DATA_FORMAT)

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
    143: "Art GP ‘23", 144: "Campos ‘23", 145: "Carlin ‘23",
    146: "PHM ‘23", 147: "Dams ‘23", 148: "Hitech ‘23",
    149: "MP Motorsport ‘23", 150: "Prema ‘23", 151: "Trident ‘23",
    152: "Van Amersfoort Racing ‘23", 153: "Virtuosi ‘23"
}



# Variables pour suivre les données
max_speed = 0  # Vitesse maximale atteinte dans le tour
last_lap_time = None  # Dernier temps de tour enregistré
current_lap = 0  # Lap actuel du joueur
sector_1_time = None  # Temps du secteur 1
sector_2_time = None  # Temps du secteur 2
sector_3_time = None  # Temps du secteur 3
last_lap_time = 0 
currents1 = 0 
currents2 = 0 
last_lap = 0
current_lap_time = 0
final_lap = 0
track_name = "Inconnu"
team_name = "Inconnu"



try:
    while True:
        data, addr = sock.recvfrom(2048)
        data_length = len(data)

        if data_length < HEADER_SIZE:
            continue  # Paquet trop court

        # Lecture du header
        header = struct.unpack(PACKET_HEADER_FORMAT, data[:HEADER_SIZE])
        (
            packet_format, game_year, major_ver, minor_ver, 
            packet_ver, packet_id, session_uid, session_time, 
            frame_id, overall_frame_id, player_car_index, secondary_car_index
        ) = header

        if packet_id == 6:  # PacketCarTelemetryData
            # Extraction des données du joueur
            offset = HEADER_SIZE + (player_car_index * CAR_TELEMETRY_SIZE)
            car_data = struct.unpack(CAR_TELEMETRY_FORMAT, data[offset:offset + CAR_TELEMETRY_SIZE])

            speed = car_data[0]  # Vitesse en km/h
            max_speed = max(max_speed, speed)  # Mettre à jour la vitesse max
            
            
        elif packet_id == 1:  # PacketSessionData - Récupérer le circuit
            track_id = struct.unpack_from("b", data, HEADER_SIZE + 7)[0]  # Extraction de trackId
            track_name = TRACKS.get(track_id, "Inconnu")
        
        elif packet_id == 4:  # PacketParticipantsData - Récupérer l'écurie du joueur
            participant_offset = HEADER_SIZE + 1 + (player_car_index * 54)  # Offset pour l'équipe
            team_id = struct.unpack_from("B", data, participant_offset + 3)[0]
            team_name = TEAMS.get(team_id, "Inconnu")
            
        

        elif packet_id == 2:  
        
        
            offset = HEADER_SIZE + (player_car_index * LAP_DATA_SIZE)
            lap_data = struct.unpack(LAP_DATA_FORMAT, data[offset:offset + LAP_DATA_SIZE])
            last_lap_time_ms = lap_data[0] # Dernier temps au tour en millisecondes
            current_lap = lap_data[1]
            sector_1_time_ms = lap_data[2]  # Secteur 1 en millisecondes
            sector_2_time_ms = lap_data[4]  # Secteur 2 en millisecondes
            sector_3_time_ms = current_lap - (sector_1_time_ms + sector_2_time_ms)  # Secteur 3 calculé
            current_lap_number = lap_data[14]  # Numéro du tour actuel du joueur
            
            
            def ms_to_ss_mms(milliseconds):
                seconds = milliseconds // 1000
                ms = milliseconds % 1000
                return f"{seconds:02d}:{ms:03d}"
            
            def ms_to_mm_ss_mms(milliseconds):
                minutes = milliseconds // 60000
                seconds = (milliseconds % 60000) // 1000
                ms = milliseconds % 1000
                return f"{minutes:02d}:{seconds:02d}:{ms:03d}"
            
            today_date = datetime.datetime.now().strftime("%d/%m/%Y")
            
            if sector_1_time_ms != 0: 
                currents1 = lap_data[2]; 
                current_lap_time = lap_data[14] 
                
            if sector_2_time_ms !=0: 
                currents2 = lap_data[4]; 
                
            if current_lap_time < current_lap_number and current_lap_time != 0: 
                sector_3_time_ms = last_lap_time_ms - (currents1 + currents2)  # Secteur 3 calculé
                final_lap = currents1 + currents2 + sector_3_time_ms
                print(f"🏁 TIME: {final_lap} S1: {currents1}s | S2: {currents2}s | S3: {sector_3_time_ms}s | 🚀 Vitesse max : {max_speed} km/h")
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
                                "Max Speed (km/h)": max_speed
                            }
                        )
                # Réinitialisation
                final_lap = 0 
                currents1 = 0
                current_lap_time = 0
                max_speed = 0
                track_name = "Inconnu"
                team_name = "Inconnu"

except KeyboardInterrupt:
    print("\n🛑 Arrêt du script.")
    sock.close()