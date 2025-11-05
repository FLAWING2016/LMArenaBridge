#!/usr/bin/env python3
"""
Script to find the maximum character limit for LMArena API.
Iterates from a starting length downward to find where requests succeed.
"""

import asyncio
import json
import sys
import httpx
from typing import Optional

# Configuration
BASE_URL = "http://localhost:8000/api/v1/chat/completions"
API_KEY = "sk-lmab-4d4c13f6-7846-4f94-a261-f59911838196"  # Set your API key here
MODEL = "claude-sonnet-4-5-20250929-thinking-32k"  # Default model, will be updated from available models

# Test parameters
STARTING_LENGTH = 500000  # Start with 500k characters
STEP_SIZE = 10000  # Decrease by 10k each time
MIN_LENGTH = 1000  # Minimum length to test

def load_config():
    """Load config to get API key if not set"""
    global API_KEY
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
            if not API_KEY and config.get("api_keys"):
                API_KEY = config["api_keys"][0]["key"]
                print(f"✅ Using API key from config: {API_KEY[:20]}...")
    except (FileNotFoundError, json.JSONDecodeError, IndexError):
        pass
    
    # Verify the model exists in available models
    try:
        with open("models.json", "r") as f:
            models = json.load(f)
            text_models = [m for m in models if m.get('capabilities', {}).get('outputCapabilities', {}).get('text')]
            model_names = [m.get("publicName") for m in text_models if m.get("publicName")]
            if MODEL not in model_names and text_models:
                print(f"⚠️  Model '{MODEL}' not found in available models")
                print(f"    Available models: {', '.join(model_names[:5])}...")
            else:
                print(f"✅ Using model: {MODEL}")
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"⚠️  Could not load models.json, using model: {MODEL}")

def generate_test_prompt(length: int) -> str:
    """
    Generate a test prompt of specified length.
    Uses only alphanumeric characters and spaces to avoid any escaping issues.
    """
    # Use simple, safe characters that won't need escaping in JSON
    base_text = "abcdefghijklmnopqrstuvwxyz0123456789 "
    repeat_count = length // len(base_text)
    remainder = length % len(base_text)
    return (base_text * repeat_count) + base_text[:remainder]

async def test_request(length: int, timeout: int = 60) -> tuple[bool, Optional[str]]:
    """
    Test a request with the given prompt length.
    Returns (success, error_message)
    """
    prompt = generate_test_prompt(length)
    
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False
    }
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    print(f"\n{'='*60}")
    print(f"🧪 Testing with {length:,} characters")
    print(f"{'='*60}")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                BASE_URL,
                json=payload,
                headers=headers,
                timeout=timeout
            )
            
            print(f"📊 Status Code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(f"✅ SUCCESS - Got response ({len(response_text)} chars)")
                return True, None
            else:
                error_msg = f"Status {response.status_code}: {response.text[:200]}"
                print(f"❌ FAILED - {error_msg}")
                return False, error_msg
                
        except httpx.TimeoutException:
            error_msg = f"Request timed out after {timeout}s"
            print(f"⏱️ TIMEOUT - {error_msg}")
            return False, error_msg
            
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code}: {e.response.text[:200]}"
            print(f"❌ HTTP ERROR - {error_msg}")
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
            print(f"❌ ERROR - {error_msg}")
            return False, error_msg

async def binary_search(min_len: int, max_len: int, step: int = 1000) -> int:
    """
    Use binary search to find the exact character limit more efficiently.
    """
    print(f"\n{'='*60}")
    print(f"🔍 Binary search between {min_len:,} and {max_len:,} characters")
    print(f"{'='*60}")
    
    last_success = min_len
    
    while max_len - min_len > step:
        mid = (min_len + max_len) // 2
        success, error = await test_request(mid)
        
        if success:
            last_success = mid
            min_len = mid + 1
            print(f"↗️ Increasing search range to {min_len:,} - {max_len:,}")
        else:
            max_len = mid - 1
            print(f"↘️ Decreasing search range to {min_len:,} - {max_len:,}")
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(2)
    
    return last_success

async def find_char_limit():
    """Main function to find the character limit"""
    
    print("\n" + "="*60)
    print("🔎 LMArena Character Limit Finder")
    print("="*60)
    
    load_config()
    
    if not API_KEY:
        print("❌ No API key found!")
        print("Please set API_KEY in the script or add it to config.json")
        sys.exit(1)
    
    print(f"\n📋 Configuration:")
    print(f"   Base URL: {BASE_URL}")
    print(f"   Model: {MODEL}")
    print(f"   Starting Length: {STARTING_LENGTH:,} chars")
    print(f"   Step Size: {STEP_SIZE:,} chars")
    print(f"   Min Length: {MIN_LENGTH:,} chars")
    
    # Phase 1: Coarse search - find approximate range
    print(f"\n{'='*60}")
    print("PHASE 1: Coarse Search")
    print(f"{'='*60}")
    
    current_length = STARTING_LENGTH
    last_success_length = None
    first_failure_length = None
    
    while current_length >= MIN_LENGTH:
        success, error = await test_request(current_length)
        
        if success:
            last_success_length = current_length
            print(f"✅ Found working length: {current_length:,} chars")
            break
        else:
            first_failure_length = current_length
            print(f"❌ {current_length:,} chars is too large")
            current_length -= STEP_SIZE
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(2)
    
    if last_success_length is None:
        print(f"\n❌ All tested lengths failed. The limit might be below {MIN_LENGTH:,} chars")
        return
    
    # Phase 2: Binary search for exact limit
    if first_failure_length and last_success_length:
        print(f"\n{'='*60}")
        print("PHASE 2: Binary Search for Exact Limit")
        print(f"{'='*60}")
        
        exact_limit = await binary_search(
            last_success_length,
            first_failure_length,
            step=500  # Find limit within 500 char accuracy
        )
        last_success_length = exact_limit
    
    # Final results
    print(f"\n{'='*60}")
    print("🎯 RESULTS")
    print(f"{'='*60}")
    print(f"✅ Maximum working character limit: {last_success_length:,} characters")
    print(f"📝 This means prompts up to {last_success_length:,} chars should work")
    
    if first_failure_length:
        print(f"❌ First failure at: {first_failure_length:,} characters")
        print(f"📊 Safe range: up to {last_success_length:,} characters")
    
    print(f"\n{'='*60}")
    print("✨ Testing complete!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    try:
        asyncio.run(find_char_limit())
    except KeyboardInterrupt:
        print("\n\n⚠️ Testing interrupted by user")
        sys.exit(0)
