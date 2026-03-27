"""
simulate_load.py — Generate concurrent requests to trigger 429 rate-limiting
and demonstrate APIM AI Gateway failover between regions.

Usage:
    cd apim-ai-gateway-demo
    .\.venv\Scripts\Activate.ps1
    python scripts/simulate_load.py [--requests 50] [--concurrency 10]
"""

import argparse
import asyncio
import sys
import os
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from app.config import settings


async def send_request(client: httpx.AsyncClient, url: str, headers: dict, payload: dict, req_id: int) -> dict:
    """Send a single chat completion request and return result metadata."""
    start = time.perf_counter()
    try:
        resp = await client.post(
            f"{url}/deployments/gpt-4.1/chat/completions",
            headers=headers,
            json=payload,
            params={"api-version": "2024-10-21"},
            timeout=60,
        )
        elapsed = time.perf_counter() - start
        region = resp.headers.get("x-backend-region", "unknown")
        return {
            "id": req_id,
            "status": resp.status_code,
            "region": region,
            "elapsed": elapsed,
            "failover": resp.status_code == 200 and "retry" in resp.headers.get("x-apim-debug", "").lower(),
        }
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {
            "id": req_id,
            "status": 0,
            "region": "error",
            "elapsed": elapsed,
            "error": str(e),
        }


async def run_load_test(url: str, api_key: str, total: int, concurrency: int):
    """Run the load test with bounded concurrency."""
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. Reply in one sentence."},
            {"role": "user", "content": "What is Azure API Management?"},
        ],
        "max_tokens": 50,
    }

    semaphore = asyncio.Semaphore(concurrency)
    results = []

    async def bounded_request(client, i):
        async with semaphore:
            result = await send_request(client, url, headers, payload, i)
            status_icon = "✅" if result["status"] == 200 else "⚠️" if result["status"] == 429 else "❌"
            print(f"  {status_icon} #{i:3d}  status={result['status']}  region={result['region']}  {result['elapsed']:.2f}s")
            results.append(result)

    print(f"\n🚀 Starting load test: {total} requests, concurrency={concurrency}")
    print(f"   Target: {url}\n")

    async with httpx.AsyncClient() as client:
        tasks = [bounded_request(client, i) for i in range(1, total + 1)]
        await asyncio.gather(*tasks)

    # Summary
    status_counts = Counter(r["status"] for r in results)
    region_counts = Counter(r["region"] for r in results)
    avg_time = sum(r["elapsed"] for r in results) / len(results) if results else 0

    print("\n" + "=" * 50)
    print("  📊 Load Test Summary")
    print("=" * 50)
    print(f"  Total requests:    {total}")
    print(f"  Avg response time: {avg_time:.2f}s")
    print(f"\n  Status codes:")
    for code, count in sorted(status_counts.items()):
        icon = "✅" if code == 200 else "⚠️" if code == 429 else "❌"
        print(f"    {icon} {code}: {count}")
    print(f"\n  Backend regions:")
    for region, count in sorted(region_counts.items()):
        print(f"    🌐 {region}: {count}")

    failover_count = sum(1 for r in results if r.get("failover"))
    throttle_count = status_counts.get(429, 0)
    print(f"\n  🔄 429 throttled: {throttle_count}")
    print(f"  🔀 Failovers:     {failover_count}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="Simulate load to trigger APIM 429 failover")
    parser.add_argument("--requests", type=int, default=50, help="Total number of requests")
    parser.add_argument("--concurrency", type=int, default=10, help="Max concurrent requests")
    args = parser.parse_args()

    url = settings.APIM_GATEWAY_URL
    key = settings.APIM_SUBSCRIPTION_KEY

    if not url or not key:
        print("❌ APIM_GATEWAY_URL and APIM_SUBSCRIPTION_KEY must be set in .env")
        sys.exit(1)

    asyncio.run(run_load_test(url, key, args.requests, args.concurrency))


if __name__ == "__main__":
    main()
