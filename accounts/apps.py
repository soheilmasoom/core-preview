from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class AccountConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    
    def ready(self):
        import sys
        if 'runserver' not in sys.argv:
            return
        
        try:
            from accounts.utils.firebase_service import FirebaseService
            FirebaseService.initialize()
            logger.info("Firebase Admin SDK initialized successfully in AppConfig")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Admin SDK in AppConfig: {e}")
            if not __debug__:
                raise
