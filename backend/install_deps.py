#!/usr/bin/env python3
"""Script pour installer les dépendances manquantes"""

import subprocess
import sys

def install_package(package):
    """Installer un package avec pip"""
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "install", package], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ {package} installé avec succès")
            return True
        else:
            print(f"✗ Erreur installation {package}: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Erreur: {e}")
        return False

def main():
    """Installer les dépendances manquantes"""
    print("=== INSTALLATION DÉPENDANCES MANQUANTES ===")
    
    packages = [
        "email-validator==2.0.0"
    ]
    
    success_count = 0
    for package in packages:
        if install_package(package):
            success_count += 1
    
    print(f"\n=== RÉSULTATS: {success_count}/{len(packages)} packages installés ===")
    
    if success_count == len(packages):
        print("🎉 Toutes les dépendances sont installées!")
    else:
        print("❌ Certaines installations ont échoué")

if __name__ == "__main__":
    main()
