"""
Patch pour corriger l'erreur bcrypt __about__ avec passlib
"""
import sys

def patch_bcrypt():
    """Applique un patch pour corriger l'erreur __about__ de bcrypt"""
    try:
        import bcrypt
        
        # Créer l'attribut __about__ manquant si nécessaire
        if not hasattr(bcrypt, '__about__'):
            class About:
                __version__ = getattr(bcrypt, '__version__', '4.0.1')
            
            bcrypt.__about__ = About()
            print(f"✓ Patch bcrypt appliqué - version: {bcrypt.__about__.__version__}")
        
        return True
        
    except ImportError:
        print("✗ bcrypt non installé")
        return False
    except Exception as e:
        print(f"✗ Erreur lors du patch bcrypt: {e}")
        return False

# Appliquer le patch automatiquement lors de l'import
if __name__ != "__main__":
    patch_bcrypt()
