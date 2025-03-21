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

## **Visualisation des données**

Avec ce site web, https://fanciful-druid-e5b8c4.netlify.app/ il est possible de visuliser ces différents temps par tour et secteur.
![CleanShot 2025-03-21 at 13 51 59@2x](https://github.com/user-attachments/assets/24b3386b-e427-4e8a-942b-9f273d4a561b)
![CleanShot 2025-03-21 at 13 52 15@2x](https://github.com/user-attachments/assets/1127e052-244c-44bc-b468-9e66d974dc2a)
![CleanShot 2025-03-21 at 13 52 30@2x](https://github.com/user-attachments/assets/e1bbbf96-a3fa-4815-874d-bf9749e18de0)
![CleanShot 2025-03-21 at 13 52 40@2x](https://github.com/user-attachments/assets/5f76f4c0-c0a1-42b2-ac10-e7085730ef8b)


