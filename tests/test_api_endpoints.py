#!/usr/bin/env python3
"""
네이버 지도 API 엔드포인트 테스트
"""

import asyncio
import aiohttp
import json

async def test_api_endpoints():
    base_url = "http://localhost:8001"

    async with aiohttp.ClientSession() as session:
        # 1. API 상태 확인
        print("=== API 상태 확인 ===")
        try:
            async with session.get(f"{base_url}/api/map/health") as resp:
                data = await resp.json()
                print(f"Status: {resp.status}")
                print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
        except Exception as e:
            print(f"Error: {e}")

        print("\n=== 장소 검색 테스트 ===")
        # 2. 장소 검색
        try:
            async with session.get(f"{base_url}/api/map/search-places",
                                   params={"query": "강남역 맛집"}) as resp:
                data = await resp.json()
                print(f"Status: {resp.status}")
                print(f"Found {len(data)} places:")
                for place in data[:3]:  # 처음 3개만 출력
                    print(f"  - {place['name']}: {place['address']}")
        except Exception as e:
            print(f"Error: {e}")

        print("\n=== Geocoding 테스트 ===")
        # 3. 주소 -> 좌표 변환
        try:
            async with session.get(f"{base_url}/api/map/geocode",
                                   params={"address": "서울시청"}) as resp:
                data = await resp.json()
                print(f"Status: {resp.status}")
                if resp.status == 200:
                    print(f"Address: {data['address']}")
                    print(f"Coordinates: ({data['lat']:.6f}, {data['lng']:.6f})")
                else:
                    print(f"Error: {data}")
        except Exception as e:
            print(f"Error: {e}")

        print("\n=== 전체 기능 테스트 ===")
        # 4. 전체 기능 테스트
        try:
            async with session.get(f"{base_url}/api/map/test/all") as resp:
                data = await resp.json()
                print(f"Status: {resp.status}")
                print(f"Test Results: {json.dumps(data, indent=2, ensure_ascii=False)}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_api_endpoints())