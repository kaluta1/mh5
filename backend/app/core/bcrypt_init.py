"""
Module d'initialisation bcrypt pour corriger l'erreur __about__
À importer avant tout usage de passlib dans l'application
"""

def init_bcrypt():
    """Initialise bcrypt avec le patch __about__ si nécessaire"""
    try:
        import bcrypt
        
        # Vérifier et créer __about__ si manquant
        if not hasattr(bcrypt, '__about__'):
            class About:
                def __init__(self):
                    self.__version__ = getattr(bcrypt, '__version__', '4.0.1')
            
            bcrypt.__about__ = About()
        
        return True
        
    except ImportError:
        return False
    except Exception:
        return False

# Appliquer le patch automatiquement à l'import
init_bcrypt()
