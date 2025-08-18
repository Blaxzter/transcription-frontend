#!/usr/bin/env python3
"""
Test script to verify webhook processing with the new Wowza webhook format
"""

import json
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from main import WowzaWebhook, find_download_url, looks_ready


def test_new_webhook_format():
    """Test the new webhook format"""

    # Your provided webhook payload
    webhook_data = {
        "version": "1.0",
        "event": "completed",
        "event_id": "b34311e1-4b08-4584-a2a1-5e31d4a70104",
        "event_time": 1755533300,
        "object_type": "recording",
        "object_id": "hB3BHqRq",
        "object_data": {
            "transcoder_id": "jjl7yxvh",
            "transcoder_uptime_id": "7d0z2cls",
            "file_name": "v-58a95157-8e3c-4047-a139-acf2535da48d_720p.mp4",
            "file_size": 1999417442,
            "duration": 6008056,
            "download_url": "https://wv-cdn-00-00.wowza.com/2313b8da-7375-4995-910a-7fb80c2de4f1/v-58a95157-8e3c-4047-a139-acf2535da48d_720p.mp4",
        },
    }

    print("Testing new webhook format...")
    print(f"Input: {json.dumps(webhook_data, indent=2)}")

    # Test webhook validation
    try:
        webhook = WowzaWebhook.model_validate(webhook_data)
        print("✅ Webhook validation successful")
        print(f"   Event type: {webhook.event}")
        print(f"   Object ID: {webhook.object_id}")
        print(f"   Object type: {webhook.object_type}")
    except Exception as e:
        print(f"❌ Webhook validation failed: {e}")
        return False

    # Test ready state check
    event_type = webhook_data.get("event")
    is_ready = looks_ready(event_type, webhook_data)
    print(f"✅ Ready check: {is_ready} (event: {event_type})")

    # Test download URL extraction
    download_url, source = find_download_url(webhook)
    print(f"✅ Download URL found: {download_url}")
    print(f"   Source: {source}")

    # Test video name extraction
    video_name = (
        webhook.object_data.get("file_name")
        or webhook.payload.get("name")
        or f"wowza_video_{webhook.object_id or 'unknown'}"
    )
    print(f"✅ Video name: {video_name}")

    return True


if __name__ == "__main__":
    success = test_new_webhook_format()
    if success:
        print(
            "\n🎉 All tests passed! The webhook endpoint should work with the new format."
        )
    else:
        print("\n❌ Tests failed!")
        sys.exit(1)
