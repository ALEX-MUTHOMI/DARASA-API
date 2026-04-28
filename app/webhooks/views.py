import json
import logging

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from core.security import verify_webhook_signature, verify_webhook_timestamp

logger = logging.getLogger(__name__)
_MAX_WEBHOOK_PAYLOAD_BYTES = 5 * 1024 * 1024
_WEBHOOK_REPLAY_WINDOW_SECONDS = getattr(settings, "WEBHOOK_REPLAY_WINDOW_SECONDS", 300)

class CloudflareWebhookView(APIView):
    """
    Ingests Cloudflare R2 webhooks.
    Validates timestamp-bound HMAC signatures.
    Domain-specific asset logic has been purged for Darasa API pivot.
    """
    authentication_classes = [] # Disable global auth
    permission_classes = []     # Disable global permissions
    throttle_classes = []       # Disable rate limiting for webhooks (Cloudflare IPs)

    def post(self, request, *args, **kwargs):
        # 1. Size Limit before parsing (Memory Exhaustion DoS Protection)
        content_length = request.META.get('CONTENT_LENGTH')
        if content_length and int(content_length) > _MAX_WEBHOOK_PAYLOAD_BYTES:
            logger.warning("Webhook payload too large.")
            return Response({"error": "Payload too large"}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Get Raw Payload
        payload_bytes = request.body
        
        # 3. Retrieve Signature
        cloudflare_signature = request.META.get('HTTP_X_CLOUDFLARE_SIGNATURE')
        if not cloudflare_signature:
            logger.warning("Missing Cloudflare Signature")
            return Response({"error": "Missing signature"}, status=status.HTTP_403_FORBIDDEN)

        # 4. Replay Protection (fail closed) with canonical timestamp validation
        webhook_timestamp_str = (
            request.META.get('HTTP_WEBHOOK_TIMESTAMP')
            or request.META.get('HTTP_X_WEBHOOK_TIMESTAMP')
        )
        timestamp_valid, timestamp_reason, canonical_timestamp = verify_webhook_timestamp(
            webhook_timestamp_str,
            max_age_seconds=_WEBHOOK_REPLAY_WINDOW_SECONDS,
        )
        if not timestamp_valid:
            logger.warning("Webhook timestamp rejected. reason=%s", timestamp_reason)
            return Response({"error": "Invalid timestamp"}, status=status.HTTP_403_FORBIDDEN)

        # 5. Validate HMAC over "<timestamp>.<raw_payload>"
        signature_valid, signature_reason = verify_webhook_signature(
            payload_bytes,
            canonical_timestamp,
            cloudflare_signature,
            secret_setting="CLOUDFLARE_WEBHOOK_SECRET",
        )
        if not signature_valid:
            if signature_reason in ("secret_not_configured", "secret_encoding_error"):
                logger.critical(
                    "[WEBHOOK] CLOUDFLARE_WEBHOOK_SECRET is not configured correctly. "
                    "reason=%s",
                    signature_reason,
                )
                return Response({"error": "Server misconfiguration"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            logger.warning("Invalid Cloudflare Signature. reason=%s", signature_reason)
            return Response({"error": "Invalid signature"}, status=status.HTTP_403_FORBIDDEN)

        # 6. Parse JSON Payload
        try:
            payload = json.loads(payload_bytes)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook payload")
            return Response({"error": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST)

        action = payload.get('action')
        r2_object_key = payload.get('r2_object_key')

        # 7. Action Filter
        if action != 'PutObject':
            logger.info(f"Ignoring non-PutObject action: {action}")
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        logger.info("Webhook successfully validated for %s. Awaiting new school domain models.", r2_object_key)
        return Response({"status": "success"}, status=status.HTTP_200_OK)
