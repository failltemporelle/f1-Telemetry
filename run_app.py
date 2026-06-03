"""
F1 Télémétrie — Application macOS
Capture les données UDP de F1 25, les diffuse en WebSocket et ouvre le dashboard.
"""
import asyncio, datetime, json, os, socket, struct, sys
import threading, time, webbrowser
import tkinter as tk
from tkinter import scrolledtext
import websockets

# ── Ressources PyInstaller ─────────────────────────────────────────────────────
def resource_path(rel):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

# ── Configuration ──────────────────────────────────────────────────────────────
UDP_PORT  = 20777
WS_PORT   = 8080
HTTP_PORT = 7777
DASHBOARD = f"http://localhost:{HTTP_PORT}/dashboard.html"

# ── Constantes F1 ──────────────────────────────────────────────────────────────
TRACKS = {
    0:"Melbourne",1:"Paul Ricard",2:"Shanghai",3:"Sakhir (Bahrain)",
    4:"Catalunya",5:"Monaco",6:"Montreal",7:"Silverstone",
    8:"Hockenheim",9:"Hungaroring",10:"Spa",11:"Monza",
    12:"Singapore",13:"Suzuka",14:"Abu Dhabi",15:"Texas",
    16:"Brazil",17:"Austria",18:"Sochi",19:"Mexico",
    20:"Baku (Azerbaijan)",21:"Sakhir Short",22:"Silverstone Short",
    23:"Texas Short",24:"Suzuka Short",25:"Hanoi",26:"Zandvoort",
    27:"Imola",28:"Portimão",29:"Jeddah",30:"Miami",
    31:"Las Vegas",32:"Losail"
}
TEAMS = {
    0:"Mercedes",1:"Ferrari",2:"Red Bull Racing",3:"Williams",
    4:"Aston Martin",5:"Alpine",6:"RB",7:"Haas",
    8:"McLaren",9:"Sauber",41:"F1 Generic",104:"F1 Custom Team",
    143:"Art GP '23",144:"Campos '23",145:"Carlin '23",
    146:"PHM '23",147:"Dams '23",148:"Hitech '23",
    149:"MP Motorsport '23",150:"Prema '23",151:"Trident '23",
    152:"Van Amersfoort Racing '23",153:"Virtuosi '23"
}
WEATHER_MAP  = {0:'DÉGAGÉ',1:'NUAGEUX',2:'COUVERT',3:'PLUIE LÉGÈRE',4:'PLUIE',5:'ORAGE'}
SESSION_MAP  = {0:'INCONNU',1:'P1',2:'P2',3:'P3',4:'P COURT',5:'Q1',6:'Q2',7:'Q3',
                8:'Q COURT',9:'SUPERPOLE',10:'COURSE',11:'COURSE 2',12:'COURSE 3',13:'TIME TRIAL'}
VISUAL_TYRE_MAP = {16:'S',17:'M',18:'H',7:'I',8:'W'}
ERS_MODE_NAMES  = {0:'NONE',1:'MEDIUM',2:'HOTLAP',3:'OVERTAKE'}

PACKET_HEADER_FORMAT  = "<HBBBBBQfII2B"
HEADER_SIZE           = struct.calcsize(PACKET_HEADER_FORMAT)
CAR_TELEMETRY_SIZE    = 60
FULL_CAR_TELEM_FORMAT = "<HfffBbHBBH4H4B4BH4f4B"
TIME_TRIAL_SET_FORMAT = "<BBIIIIBBBBBB"
TIME_TRIAL_SET_SIZE   = struct.calcsize(TIME_TRIAL_SET_FORMAT)

# ── WebSocket server ───────────────────────────────────────────────────────────
connected_clients = set()
ws_loop           = None
_telem_lock       = threading.Lock()
_latest_telem     = [None]
_telem_scheduled  = [False]

def _flush_telem():
    with _telem_lock:
        msg = _latest_telem[0]
        _latest_telem[0]    = None
        _telem_scheduled[0] = False
    if msg and connected_clients:
        websockets.broadcast(connected_clients, msg)

def broadcast_telemetry(data_dict):
    if ws_loop is None or not connected_clients:
        return
    msg_type = data_dict.get('type', '')
    message  = json.dumps(data_dict)
    if msg_type in ('telemetry', 'map_update'):
        with _telem_lock:
            _latest_telem[0] = message
            if not _telem_scheduled[0]:
                _telem_scheduled[0] = True
                ws_loop.call_soon_threadsafe(_flush_telem)
    else:
        clients = set(connected_clients)
        ws_loop.call_soon_threadsafe(websockets.broadcast, clients, message)

async def _ws_handler(websocket):
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

async def _ws_serve():
    global ws_loop
    ws_loop = asyncio.get_running_loop()
    async with websockets.serve(_ws_handler, "0.0.0.0", WS_PORT):
        await asyncio.Future()

def run_ws_server():
    try:
        asyncio.run(_ws_serve())
    except OSError as e:
        print(f"[WS] Port {WS_PORT} déjà utilisé : {e}")

# ── HTTP server ────────────────────────────────────────────────────────────────
def run_http_server():
    import http.server
    _dir = resource_path('.')

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=_dir, **kwargs)
        def log_message(self, *args):
            pass  # silence les logs HTTP

    httpd = http.server.HTTPServer(("0.0.0.0", HTTP_PORT), QuietHandler)
    httpd.serve_forever()

# ── Formatage temps ────────────────────────────────────────────────────────────
def ms_to_ss_mms(ms):
    return f"{ms//1000:02d}:{ms%1000:03d}"

def ms_to_mm_ss_mms(ms):
    m = ms // 60000; s = (ms % 60000) // 1000; r = ms % 1000
    return f"{m:02d}:{s:02d}:{r:03d}"

def ms_to_delta(ms):
    sign = '+' if ms >= 0 else '-'
    v = abs(ms)
    return f"{sign}{v//1000}.{v%1000:03d}"

# ── GUI ────────────────────────────────────────────────────────────────────────
class F1App:
    BG    = '#080809'
    S1    = '#0f0f11'
    S2    = '#161618'
    RED   = '#e8002d'
    GREEN = '#16a34a'
    T1    = '#e2e2e4'
    T2    = '#71717a'
    T3    = '#3f3f46'

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("F1 Télémétrie")
        self.root.geometry("480x340")
        self.root.configure(bg=self.BG)
        self.root.resizable(False, False)
        # Fermeture propre
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._start_servers()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # --- Header ---
        hdr = tk.Frame(self.root, bg=self.S1, height=48)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)

        tk.Label(hdr, text='F1', bg=self.RED, fg='white',
                 font=('Courier', 9, 'bold'), width=3).place(relx=0, rely=0.5, anchor='w', x=14)
        tk.Label(hdr, text='TÉLÉMÉTRIE', bg=self.S1, fg=self.T1,
                 font=('Courier', 11, 'bold')).place(relx=0, rely=0.5, anchor='w', x=52)

        # --- Status bar ---
        sb = tk.Frame(self.root, bg=self.S2, height=34)
        sb.pack(fill='x')
        sb.pack_propagate(False)

        self.dot_lbl = tk.Label(sb, text='●', bg=self.S2, fg=self.RED, font=('Courier', 10))
        self.dot_lbl.place(relx=0, rely=0.5, anchor='w', x=14)
        self.status_lbl = tk.Label(sb, text='EN ATTENTE DE F1', bg=self.S2, fg=self.T2,
                                    font=('Courier', 9))
        self.status_lbl.place(relx=0, rely=0.5, anchor='w', x=32)
        self.packets_lbl = tk.Label(sb, text='', bg=self.S2, fg=self.T3, font=('Courier', 8))
        self.packets_lbl.place(relx=1, rely=0.5, anchor='e', x=-14)

        # --- Dashboard link ---
        lf = tk.Frame(self.root, bg=self.BG)
        lf.pack(fill='x', padx=16, pady=(10, 4))

        tk.Label(lf, text='DASHBOARD', bg=self.BG, fg=self.T3,
                 font=('Courier', 8)).pack(anchor='w')

        row = tk.Frame(lf, bg=self.BG)
        row.pack(fill='x', pady=(2, 0))

        url_lbl = tk.Label(row, text=DASHBOARD, bg=self.BG, fg=self.T1,
                            font=('Courier', 10), cursor='hand2')
        url_lbl.pack(side='left')
        url_lbl.bind('<Button-1>', lambda _: webbrowser.open(DASHBOARD))

        tk.Button(row, text='Ouvrir  ↗', bg=self.RED, fg='white',
                  font=('Courier', 8), relief='flat', cursor='hand2', bd=0,
                  padx=8, pady=2,
                  command=lambda: webbrowser.open(DASHBOARD)).pack(side='right')

        # --- Separator ---
        tk.Frame(self.root, bg=self.S2, height=1).pack(fill='x', pady=(8, 0))

        # --- Log ---
        self.log_widget = scrolledtext.ScrolledText(
            self.root, bg=self.S1, fg=self.T3, insertbackground=self.T3,
            font=('Courier', 9), relief='flat', state='disabled',
            selectbackground=self.S2
        )
        self.log_widget.pack(fill='both', expand=True)

    # ── Helpers UI thread-safe ─────────────────────────────────────────────────
    def _log(self, msg):
        def _do():
            self.log_widget.configure(state='normal')
            self.log_widget.insert(tk.END, msg + '\n')
            self.log_widget.see(tk.END)
            self.log_widget.configure(state='disabled')
        self.root.after(0, _do)

    def _set_status(self, text, color):
        self.root.after(0, lambda: [
            self.status_lbl.configure(text=text, fg=color),
            self.dot_lbl.configure(fg=color)
        ])

    def _set_packets(self, text):
        self.root.after(0, lambda: self.packets_lbl.configure(text=text))

    # ── Démarrage des serveurs ─────────────────────────────────────────────────
    def _start_servers(self):
        threading.Thread(target=run_ws_server,  daemon=True).start()
        threading.Thread(target=run_http_server, daemon=True).start()
        threading.Thread(target=self._udp_loop,  daemon=True).start()
        self._log('✓  Serveur WebSocket  →  port 8080')
        self._log('✓  Serveur HTTP       →  port 7777')
        self._log('⏳  En attente des données F1 (UDP 20777)…')
        self._log('')
        # Ouvrir le navigateur seulement quand le serveur HTTP est prêt
        threading.Thread(target=self._open_when_ready, daemon=True).start()

    def _open_when_ready(self):
        """Attend que le serveur HTTP réponde, puis ouvre le navigateur."""
        import urllib.request
        for _ in range(40):          # 20 secondes max
            try:
                urllib.request.urlopen(f"http://localhost:{HTTP_PORT}/", timeout=1)
                self.root.after(0, lambda: webbrowser.open(DASHBOARD))
                return
            except Exception:
                time.sleep(0.5)
        # Fallback : ouvre quand même après timeout
        self.root.after(0, lambda: webbrowser.open(DASHBOARD))

    # ── Boucle UDP ─────────────────────────────────────────────────────────────
    def _udp_loop(self):
        # État local
        max_speed = 0; current_lap = 0; currents1 = 0; currents2 = 0
        current_lap_time = 0; track_name = "Inconnu"; team_name = "Inconnu"
        pos_x = 0.0; pos_y = 0.0; pos_z = 0.0; previous_gear = -2
        gear_counts = {-1:0,0:0,1:0,2:0,3:0,4:0,5:0,6:0,7:0,8:0}
        last_map_time = 0; car_position = 0; gap_ahead = 0.0; gap_behind = 0.0
        fuel_in_tank = 0.0; fuel_remaining_laps = 0.0; drs_allowed = 0
        ers_pct = 0.0; ers_mode_str = '—'; tyre_compound = 'M'
        brake_fl = 0; brake_fr = 0; brake_rl = 0; brake_rr = 0
        tyre_fl = 0; tyre_fr = 0; tyre_rl = 0; tyre_rr = 0
        engine_temp = 0; drs_active = 0
        track_temp = 0; air_temp = 0; weather_str = '—'; session_type = '—'
        pb_lap_ms = 0; pb_s1_ms = 0; pb_s2_ms = 0; pb_s3_ms = 0
        first_received = False; packet_count = 0; last_ui_update = 0

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("0.0.0.0", UDP_PORT))
        except OSError as e:
            self._log(f'❌  Impossible d\'écouter le port {UDP_PORT} : {e}')
            return

        while True:
            data, addr = sock.recvfrom(2048)
            data_length = len(data)

            if not first_received:
                first_received = True
                self._set_status('EN DIRECT', self.GREEN)
                self._log(f'🎉  Données reçues de {addr[0]}')

            packet_count += 1
            now = time.time()
            if now - last_ui_update > 0.5:
                self._set_packets(f'{packet_count} paquets reçus')
                last_ui_update = now

            if data_length < HEADER_SIZE:
                continue

            header = struct.unpack(PACKET_HEADER_FORMAT, data[:HEADER_SIZE])
            (packet_format, game_year, major_ver, minor_ver,
             packet_ver, packet_id, session_uid, session_time,
             frame_id, overall_frame_id, player_car_index, secondary_car_index) = header

            # ── Paquet 0 : Position ──────────────────────────────────────────
            if packet_id == 0:
                offset = HEADER_SIZE + (player_car_index * 60)
                pos_x, pos_y, pos_z = struct.unpack_from("<fff", data, offset)
                if time.time() - last_map_time >= 0.1:
                    broadcast_telemetry({"type":"map_update","x":round(pos_x,3),"z":round(pos_z,3)})
                    last_map_time = time.time()

            # ── Paquet 6 : Télémétrie voiture ────────────────────────────────
            elif packet_id == 6:
                offset = HEADER_SIZE + (player_car_index * CAR_TELEMETRY_SIZE)
                try:
                    car_data = struct.unpack_from(FULL_CAR_TELEM_FORMAT, data, offset)
                except struct.error:
                    car_data = struct.unpack_from("<HfffBbH", data, offset) + (0,) * 24

                speed    = car_data[0]; throttle = car_data[1]; steer = car_data[2]
                brake    = car_data[3]; gear     = car_data[5]; rpm   = car_data[6]
                drs_active = car_data[7]
                brake_rl = car_data[10]; brake_rr = car_data[11]
                brake_fl = car_data[12]; brake_fr = car_data[13]
                tyre_rl  = car_data[14]; tyre_rr  = car_data[15]
                tyre_fl  = car_data[16]; tyre_fr  = car_data[17]
                engine_temp = car_data[22]

                if gear != previous_gear:
                    if gear in gear_counts: gear_counts[gear] += 1
                    previous_gear = gear
                max_speed = max(max_speed, speed)

                broadcast_telemetry({
                    "type": "telemetry",
                    "Time": datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "Lap": current_lap, "Speed": speed, "Gear": gear, "RPM": rpm,
                    "Throttle": round(throttle, 3), "Brake": round(brake, 3),
                    "Steer": round(steer, 3),
                    "PosX": round(pos_x, 3), "PosY": round(pos_y, 3), "PosZ": round(pos_z, 3),
                    "Track": track_name, "Team": team_name,
                    "DRS": bool(drs_active),
                    "BrakeFL": brake_fl, "BrakeFR": brake_fr,
                    "BrakeRL": brake_rl, "BrakeRR": brake_rr,
                    "TyreFL": {"temp": tyre_fl, "wear": 0, "compound": tyre_compound},
                    "TyreFR": {"temp": tyre_fr, "wear": 0, "compound": tyre_compound},
                    "TyreRL": {"temp": tyre_rl, "wear": 0, "compound": tyre_compound},
                    "TyreRR": {"temp": tyre_rr, "wear": 0, "compound": tyre_compound},
                    "EngineTemp": engine_temp,
                    "Position": car_position, "GapAhead": gap_ahead, "GapBehind": gap_behind,
                    "Fuel": round(fuel_in_tank, 2), "FuelLaps": round(fuel_remaining_laps, 1),
                    "ERS": round(ers_pct, 1), "ERSMode": ers_mode_str,
                    "TrackTemp": track_temp, "AirTemp": air_temp,
                    "Weather": weather_str, "SessionType": session_type,
                })

            # ── Paquet 1 : Session ───────────────────────────────────────────
            elif packet_id == 1:
                weather_id   = struct.unpack_from("<B", data, HEADER_SIZE + 0)[0]
                track_temp   = struct.unpack_from("<b", data, HEADER_SIZE + 1)[0]
                air_temp     = struct.unpack_from("<b", data, HEADER_SIZE + 2)[0]
                session_id   = struct.unpack_from("<B", data, HEADER_SIZE + 6)[0]
                track_id     = struct.unpack_from("<b", data, HEADER_SIZE + 7)[0]
                weather_str  = WEATHER_MAP.get(weather_id, '—')
                session_type = SESSION_MAP.get(session_id, '—')
                track_name   = TRACKS.get(track_id, "Inconnu")

            # ── Paquet 4 : Participants ──────────────────────────────────────
            elif packet_id == 4:
                p_off   = HEADER_SIZE + 1 + (player_car_index * 54)
                team_id = struct.unpack_from("B", data, p_off + 3)[0]
                team_name = TEAMS.get(team_id, "Inconnu")

            # ── Paquet 2 : Données de tour ───────────────────────────────────
            elif packet_id == 2:
                if game_year in (24, 25):
                    lap_data_size = 57; s2_offset = 11; lap_num_offset = 33; delta_offset = 14
                elif game_year == 23:
                    lap_data_size = 50; s2_offset = 11; lap_num_offset = 31; delta_offset = 13
                else:
                    lap_data_size = 43; s2_offset = 10; lap_num_offset = 25; delta_offset = 12

                offset = HEADER_SIZE + (player_car_index * lap_data_size)
                last_lap_time_ms    = struct.unpack_from("<I", data, offset)[0]
                sector_1_time_ms    = struct.unpack_from("<H", data, offset + 8)[0]
                sector_2_time_ms    = struct.unpack_from("<H", data, offset + s2_offset)[0]
                current_lap_number  = struct.unpack_from("<B", data, offset + lap_num_offset)[0]
                current_lap  = current_lap_number
                car_position = struct.unpack_from("<B", data, offset + lap_num_offset - 1)[0]

                raw_ahead  = struct.unpack_from("<H", data, offset + delta_offset)[0]
                gap_ahead  = round(raw_ahead / 1000.0, 3)
                gap_behind = 0.0
                if car_position > 0:
                    max_cars = min(22, (len(data) - HEADER_SIZE) // lap_data_size)
                    for ci in range(max_cars):
                        ci_off = HEADER_SIZE + (ci * lap_data_size)
                        if ci_off + lap_data_size > len(data): break
                        ci_pos = struct.unpack_from("<B", data, ci_off + lap_num_offset - 1)[0]
                        if ci_pos == car_position + 1:
                            gap_behind = round(struct.unpack_from("<H", data, ci_off + delta_offset)[0] / 1000.0, 3)
                            break

                if sector_1_time_ms != 0:
                    currents1 = sector_1_time_ms; current_lap_time = current_lap_number
                if sector_2_time_ms != 0:
                    currents2 = sector_2_time_ms

                if current_lap_time < current_lap_number and current_lap_time != 0:
                    sector_3_time_ms = last_lap_time_ms - (currents1 + currents2)
                    is_new_pb = pb_lap_ms > 0 and last_lap_time_ms < pb_lap_ms
                    delta_lap = ms_to_delta(last_lap_time_ms - pb_lap_ms) if pb_lap_ms > 0 else None
                    delta_s1  = ms_to_delta(currents1 - pb_s1_ms)         if pb_s1_ms > 0  else None
                    delta_s2  = ms_to_delta(currents2 - pb_s2_ms)         if pb_s2_ms > 0  else None
                    delta_s3  = ms_to_delta(sector_3_time_ms - pb_s3_ms)  if pb_s3_ms > 0  else None
                    if is_new_pb:
                        pb_lap_ms = last_lap_time_ms; pb_s1_ms = currents1
                        pb_s2_ms  = currents2;        pb_s3_ms = sector_3_time_ms
                    broadcast_telemetry({
                        "type": "lap_summary", "LapNumber": current_lap_number - 1,
                        "LapTime": ms_to_mm_ss_mms(last_lap_time_ms),
                        "Sector1": ms_to_ss_mms(currents1), "Sector2": ms_to_ss_mms(currents2),
                        "Sector3": ms_to_ss_mms(sector_3_time_ms),
                        "MaxSpeed": max_speed, "Track": track_name, "Team": team_name,
                        "Gears": dict(gear_counts),
                        "DeltaLap": delta_lap, "DeltaS1": delta_s1,
                        "DeltaS2": delta_s2,   "DeltaS3": delta_s3,
                        "IsNewPB": is_new_pb,
                    })
                    self._log(f'🏁  Tour {current_lap_number - 1}  —  {ms_to_mm_ss_mms(last_lap_time_ms)}'
                              + (' ★ NOUVEAU RECORD' if is_new_pb else ''))
                    currents1 = 0; currents2 = 0; current_lap_time = 0; max_speed = 0
                    gear_counts = {-1:0,0:0,1:0,2:0,3:0,4:0,5:0,6:0,7:0,8:0}

            # ── Paquet 7 : Statut voiture ─────────────────────────────────────
            elif packet_id == 7:
                if game_year in (24, 25):
                    car_status_size = 55; ers_store_offset = 37; ers_mode_offset = 41
                else:
                    car_status_size = 47; ers_store_offset = 29; ers_mode_offset = 33
                st_off = HEADER_SIZE + (player_car_index * car_status_size)
                if len(data) >= st_off + car_status_size:
                    fuel_in_tank        = struct.unpack_from("<f", data, st_off + 5)[0]
                    fuel_remaining_laps = struct.unpack_from("<f", data, st_off + 13)[0]
                    drs_allowed         = struct.unpack_from("<B", data, st_off + 22)[0]
                    visual_cmp          = struct.unpack_from("<B", data, st_off + 26)[0]
                    ers_raw             = struct.unpack_from("<f", data, st_off + ers_store_offset)[0]
                    ers_deploy          = struct.unpack_from("<B", data, st_off + ers_mode_offset)[0]
                    ers_pct       = round(min(100.0, ers_raw / 4_000_000 * 100), 1)
                    ers_mode_str  = ERS_MODE_NAMES.get(ers_deploy, '—')
                    tyre_compound = VISUAL_TYRE_MAP.get(visual_cmp, 'M')

            # ── Paquet 14 : Time Trial PB ─────────────────────────────────────
            elif packet_id == 14:
                pb_offset = HEADER_SIZE + TIME_TRIAL_SET_SIZE
                if len(data) >= pb_offset + TIME_TRIAL_SET_SIZE:
                    pb_raw = struct.unpack_from(TIME_TRIAL_SET_FORMAT, data, pb_offset)
                    (_, _, lap_ms, s1_ms, s2_ms, s3_ms, _, _, _, _, _, pb_valid) = pb_raw
                    if pb_valid and lap_ms > 0:
                        pb_lap_ms = lap_ms; pb_s1_ms = s1_ms
                        pb_s2_ms  = s2_ms;  pb_s3_ms = s3_ms
                        broadcast_telemetry({
                            "type":    "personal_best",
                            "LapTime": ms_to_mm_ss_mms(pb_lap_ms),
                            "Sector1": ms_to_ss_mms(pb_s1_ms),
                            "Sector2": ms_to_ss_mms(pb_s2_ms),
                            "Sector3": ms_to_ss_mms(pb_s3_ms),
                        })

    # ── Fermeture ──────────────────────────────────────────────────────────────
    def _on_close(self):
        self.root.destroy()
        os._exit(0)

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    F1App().run()
