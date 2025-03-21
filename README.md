# 🏎️ F1 2024 – Collecte de Données de Télémétrie (UDP)

Ce script Python permet de recevoir, analyser et enregistrer en temps réel les données de télémétrie du jeu **F1 2024** (ou versions compatibles) via le protocole **UDP**.  
Les informations collectées incluent : les temps au tour, les temps par secteur, la vitesse maximale, le circuit courant, ainsi que l’écurie du joueur.

---

## 📄 Fonctionnalités

- Réception des paquets UDP envoyés par le jeu F1.
- Décodage des données binaires selon les formats de paquets (`PacketCarTelemetryData`, `PacketLapData`, `PacketSessionData`, `PacketParticipantsData`).
- Enregistrement automatique des tours complets dans un fichier CSV (`f1_telemetry.csv`) avec :
  - Date du tour
  - Nom du circuit
  - Écurie du joueur
  - Temps au tour
  - Temps de chaque secteur
  - Vitesse maximale atteinte dans le tour

---

## 📂 Fichier généré

- `f1_telemetry.csv` : contient toutes les données de télémétrie des tours terminés.

Exemple de ligne :
```csv
Date,Circuit,Écurie,Lap Time (s),Sector 1 (s),Sector 2 (s),Sector 3 (s),Max Speed (km/h)
21/03/2025,Monza,Ferrari,01:25:478,00:28:120,00:29:543,00:27:815,312
