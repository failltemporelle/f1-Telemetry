#!/bin/bash
# ── Build F1 Télémétrie.app ───────────────────────────────────────────────────
set -e

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🏎  Build F1 Télémétrie.app"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Aller dans le dossier du projet
cd "$(dirname "$0")"

# Vérifier Python
if ! command -v python3 &>/dev/null; then
    echo "❌  Python 3 non trouvé. Installe-le via https://python.org"
    exit 1
fi

echo "📦  Installation des dépendances..."
pip3 install -q websockets pyinstaller

echo ""
echo "🔨  Construction du .app (peut prendre 1-2 minutes)..."
python3 -m PyInstaller F1Telemetry.spec --clean --noconfirm

echo ""
echo "🔏  Signature ad-hoc du .app..."
xattr -cr "dist/F1 Télémétrie.app"
codesign -s - --force --all-architectures --deep "dist/F1 Télémétrie.app" 2>/dev/null \
    && echo "✓  Signature OK" || echo "⚠️  Signature échouée (l'app devrait quand même fonctionner)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅  Terminé !"
echo ""
echo "  Le .app est dans :"
echo "  $(pwd)/dist/F1 Télémétrie.app"
echo ""
echo "  👉  Clic droit → Ouvrir (première fois seulement)"
echo "  👉  Tu peux le glisser dans Applications"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Ouvrir le dossier dist dans le Finder
open dist/
