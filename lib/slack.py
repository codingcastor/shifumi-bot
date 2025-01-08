import os
import hmac
import hashlib
from datetime import datetime

def verify_slack_request(timestamp, body, signature):
    """Verify that the request actually came from Slack"""
    if abs(datetime.now().timestamp() - int(timestamp)) > 60 * 5:
        return False

    sig_basestring = f"v0:{timestamp}:{body}".encode('utf-8')
    my_signature = 'v0=' + hmac.new(
        os.getenv('SLACK_SIGNING_SECRET').encode('utf-8'),
        sig_basestring,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(my_signature, signature)

