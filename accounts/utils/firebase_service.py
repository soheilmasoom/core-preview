import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
# from django.core.cache import cache

from accounts.models import FirebaseToken

logger = logging.getLogger(__name__)


@dataclass
class PushNotificationPayload:
    title: str
    body: str
    image: Optional[str] = None
    link: Optional[str] = None
    data: Optional[Dict[str, str]] = None


class FirebaseService:
    _app = None
    
    @classmethod
    def initialize(cls):
        if cls._app is not None:
            return cls._app
            
        try:
            cls._app = firebase_admin.get_app()
            logger.info("Firebase Admin SDK already initialized")
        except ValueError:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH) # check!
            cls._app = firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized successfully")
        
        return cls._app
    
    @classmethod
    def send_to_token(
        cls,
        token: str,
        payload: PushNotificationPayload,
        ttl: Optional[int] = None,
        collapse_key: Optional[str] = None
    ) -> Optional[str]:
        cls.initialize()
        
        try:
            notification = messaging.Notification(
                title=payload.title,
                body=payload.body,
                image=payload.image
            )
            
            webpush_config = None
            if payload.link:
                webpush_config = messaging.WebpushConfig(
                    fcm_options=messaging.WebpushFCMOptions(
                        link=payload.link
                    )
                )
            
            android_config = None
            if ttl or collapse_key:
                android_config = messaging.AndroidConfig(
                    ttl=ttl,
                    collapse_key=collapse_key
                )
            
            message = messaging.Message(
                token=token,
                notification=notification,
                webpush=webpush_config,
                android=android_config,
                data=payload.data
            )
            
            response = messaging.send(message)
            logger.info(f"Successfully sent message to token={token[:20]}..., message_id={response}")
            return response
            
        except messaging.UnregisteredError:
            logger.warning(f"Token unregistered: {token[:20]}...")
            FirebaseToken.objects.filter(token=token).update(
                active=False, 
                error='UNREGISTERED'
            )
            return None
            
        except messaging.InvalidArgumentError as e:
            logger.error(f"Invalid argument for token {token[:20]}...: {e}")
            FirebaseToken.objects.filter(token=token).update(
                active=False, 
                error='INVALID_ARGUMENT'
            )
            return None
            
        except messaging.SenderIdMismatchError:
            logger.error(f"Sender ID mismatch for token {token[:20]}...")
            FirebaseToken.objects.filter(token=token).update(
                active=False, 
                error='SENDER_ID_MISMATCH'
            )
            return None
            
        except Exception as e:
            logger.error(f"Error sending to token {token[:20]}...: {e}", exc_info=True)
            return None
    
    @classmethod
    def send_to_topic(
        cls,
        topic: str,
        payload: PushNotificationPayload,
        ttl: Optional[int] = None,
        collapse_key: Optional[str] = None
    ) -> Optional[str]:
        cls.initialize()
        
        try:
            notification = messaging.Notification(
                title=payload.title,
                body=payload.body,
                image=payload.image
            )
            
            webpush_config = None
            if payload.link:
                webpush_config = messaging.WebpushConfig(
                    fcm_options=messaging.WebpushFCMOptions(
                        link=payload.link
                    )
                )
            
            android_config = None
            if ttl or collapse_key:
                android_config = messaging.AndroidConfig(
                    ttl=ttl,
                    collapse_key=collapse_key
                )
            
            message = messaging.Message(
                topic=topic,
                notification=notification,
                webpush=webpush_config,
                android=android_config,
                data=payload.data
            )
            
            response = messaging.send(message)
            logger.info(f"Successfully sent message to topic={topic}, message_id={response}")
            return response
            
        except Exception as e:
            logger.error(f"Error sending to topic {topic}: {e}", exc_info=True)
            return None
    
    @classmethod
    def send_multicast(
        cls,
        tokens: List[str],
        payload: PushNotificationPayload,
        ttl: Optional[int] = None
    ) -> Dict[str, any]:
        cls.initialize()
        
        if not tokens:
            return {'success_count': 0, 'failure_count': 0, 'responses': []}
        
        tokens = tokens[:500]
        
        try:
            notification = messaging.Notification(
                title=payload.title,
                body=payload.body,
                image=payload.image
            )
            
            webpush_config = None
            if payload.link:
                webpush_config = messaging.WebpushConfig(
                    fcm_options=messaging.WebpushFCMOptions(
                        link=payload.link
                    )
                )
            
            android_config = None
            if ttl:
                android_config = messaging.AndroidConfig(ttl=ttl)
            
            multicast_message = messaging.MulticastMessage(
                tokens=tokens,
                notification=notification,
                webpush=webpush_config,
                android=android_config,
                data=payload.data
            )
            
            batch_response = messaging.send_multicast(multicast_message)
            
            logger.info(
                f"Batch send result: {batch_response.success_count} success, "
                f"{batch_response.failure_count} failed out of {len(tokens)} tokens"
            )
            
            if batch_response.failure_count > 0:
                cls._handle_batch_errors(tokens, batch_response.responses)
            
            return {
                'success_count': batch_response.success_count,
                'failure_count': batch_response.failure_count,
                'responses': batch_response.responses
            }
            
        except Exception as e:
            logger.error(f"Error in batch send: {e}", exc_info=True)
            return {'success_count': 0, 'failure_count': len(tokens), 'responses': []}
    
    @classmethod
    def _handle_batch_errors(cls, tokens: List[str], responses: List):
        invalid_tokens = []
        
        for idx, response in enumerate(responses):
            if not response.success:
                token = tokens[idx]
                error = response.exception
                
                if isinstance(error, (
                    messaging.UnregisteredError,
                    messaging.InvalidArgumentError,
                    messaging.SenderIdMismatchError
                )):
                    invalid_tokens.append(token)
                    logger.info(f"Marking token as invalid: {token[:20]}... - {type(error).__name__}")
        
        if invalid_tokens:
            FirebaseToken.objects.filter(token__in=invalid_tokens).update(
                active=False,
                error='BATCH_ERROR'
            )
            logger.info(f"Deactivated {len(invalid_tokens)} invalid tokens")
    
    @classmethod
    def subscribe_to_topic(cls, tokens: List[str], topic: str) -> Dict:
        cls.initialize()
        
        if not tokens:
            return {'success_count': 0, 'errors': []}
        
        tokens = tokens[:1000]
        
        try:
            response = messaging.subscribe_to_topic(tokens, topic)
            
            logger.info(
                f"Topic subscription result for '{topic}': "
                f"{response.success_count} success, {response.failure_count} failed"
            )
            
            if response.failure_count > 0:
                cls._handle_topic_errors(tokens, response.errors, 'subscribe', topic)
            
            return {
                'success_count': response.success_count,
                'failure_count': response.failure_count,
                'errors': response.errors
            }
            
        except Exception as e:
            logger.error(f"Error subscribing to topic {topic}: {e}", exc_info=True)
            return {'success_count': 0, 'failure_count': len(tokens), 'errors': [str(e)]}
    
    @classmethod
    def unsubscribe_from_topic(cls, tokens: List[str], topic: str) -> Dict:
        cls.initialize()
        
        if not tokens:
            return {'success_count': 0, 'errors': []}
        
        tokens = tokens[:1000]
        
        try:
            response = messaging.unsubscribe_from_topic(tokens, topic)
            
            logger.info(
                f"Topic unsubscription result for '{topic}': "
                f"{response.success_count} success, {response.failure_count} failed"
            )
            
            if response.failure_count > 0:
                cls._handle_topic_errors(tokens, response.errors, 'unsubscribe', topic)
            
            return {
                'success_count': response.success_count,
                'failure_count': response.failure_count,
                'errors': response.errors
            }
            
        except Exception as e:
            logger.error(f"Error unsubscribing from topic {topic}: {e}", exc_info=True)
            return {'success_count': 0, 'failure_count': len(tokens), 'errors': [str(e)]}
    
    @classmethod
    def _handle_topic_errors(cls, tokens: List[str], errors: List, action: str, topic: str):
        invalid_tokens = []
        
        for error in errors:
            idx = error.index
            token = tokens[idx]
            reason = error.reason
            
            logger.warning(
                f"Failed to {action} token {token[:20]}... to/from topic '{topic}': {reason}"
            )
            
            if reason in ['NOT_FOUND', 'INVALID_ARGUMENT', 'PERMISSION_DENIED']:
                invalid_tokens.append(token)
        
        if invalid_tokens:
            FirebaseToken.objects.filter(token__in=invalid_tokens).update(
                active=False,
                error=f'TOPIC_{action.upper()}_ERROR'
            )
            logger.info(f"Deactivated {len(invalid_tokens)} invalid tokens during topic {action}")


firebase_service = FirebaseService()

