#!/usr/bin/env python3
"""Script pour convertir les fichiers Pydantic v2 en v1"""
import re
import os
from pathlib import Path

def fix_pydantic_v1(content):
    """Convertit le code Pydantic v2 en v1"""
    
    # Remplacer les imports
    content = re.sub(
        r'from pydantic import.*?field_validator',
        'from pydantic import validator',
        content,
        flags=re.DOTALL
    )
    
    # Remplacer field_validator par validator
    content = re.sub(
        r'@field_validator\((.*?)\)(?:\s+def)',
        r'@validator(\1)\n    def',
        content
    )
    
    # Remplacer model_config par Config class
    content = re.sub(
        r'model_config = ConfigDict\((.*?)\)',
        lambda m: f'class Config:\n        {m.group(1).replace(", ", chr(10) + "        ")}',
        content,
        flags=re.DOTALL
    )
    
    # Remplacer ConfigDict par dict
    content = content.replace('ConfigDict(', '{')
    content = content.replace(')', '}')
    
    return content

def process_file(filepath):
    """Traite un fichier Pydantic"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'field_validator' in content or 'model_config' in content or 'ConfigDict' in content:
            print(f"Traitement: {filepath}")
            new_content = fix_pydantic_v1(content)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"  ✓ Corrigé")
            return True
    except Exception as e:
        print(f"  ✗ Erreur: {e}")
    return False

def main():
    backend_dir = Path(".")
    schemas_dir = backend_dir / "app" / "schemas"
    
    if not schemas_dir.exists():
        print(f"Répertoire non trouvé: {schemas_dir}")
        return
    
    print("Correction des fichiers Pydantic v2 → v1...")
    count = 0
    
    for py_file in schemas_dir.glob("*.py"):
        if process_file(py_file):
            count += 1
    
    print(f"\n{count} fichier(s) corrigé(s)")

if __name__ == "__main__":
    main()
