#!/usr/bin/env python3
"""
네이버 지도 API 연동 테스트 스크립트

이 스크립트는 네이버 지도 API의 다양한 기능을 테스트합니다.
- API 키 검증
- 주소 -> 좌표 변환 (Geocoding)
- 좌표 -> 주소 변환 (Reverse Geocoding)
- 정적 지도 이미지 생성
- 장소 검색
"""

import asyncio
import os
from pathlib import Path
import pytest

# 프로젝트 루트를 파이썬 경로에 추가
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.naver_map_service import (
    naver_map_service,
    get_location_from_address,
    get_address_from_coordinates,
    generate_map_image,
    search_nearby_places,
    Location,
    MapOptions
)


@pytest.fixture
def locations():
    """pytest 수집 시 fixture 누락 오류 방지용 기본 데이터."""
    return []


async def test_api_validation():
    """API 키 유효성 검증 테스트"""
    print("=== API 키 검증 테스트 ===")
    try:
        is_valid = await naver_map_service.validate_api_keys()
        if is_valid:
            print("✅ API 키가 유효합니다!")
        else:
            print("❌ API 키가 유효하지 않거나 문제가 있습니다.")
        return is_valid
    except Exception as e:
        print(f"❌ API 키 검증 중 오류 발생: {e}")
        return False


async def test_geocoding():
    """주소 -> 좌표 변환 테스트"""
    print("\n=== Geocoding 테스트 ===")

    test_addresses = [
        "서울특별시 중구 세종대로 110",  # 서울시청
        "서울특별시 강남구 테헤란로 152",  # 강남역 근처
        "부산광역시 해운대구 해운대해변로 264",  # 해운대 해수욕장
        "제주특별자치도 서귀포시 중문관광로 72"  # 제주도
    ]

    results = []
    for address in test_addresses:
        try:
            location = await get_location_from_address(address)
            if location:
                print(f"✅ {address}")
                print(f"   좌표: ({location.lat:.6f}, {location.lng:.6f})")
                print(f"   주소: {location.address}")
                results.append(location)
            else:
                print(f"❌ {address} - 변환 실패")
        except Exception as e:
            print(f"❌ {address} - 오류: {e}")

    return results


async def test_reverse_geocoding(locations):
    """좌표 -> 주소 변환 테스트"""
    print("\n=== Reverse Geocoding 테스트 ===")

    for location in locations[:2]:  # 처음 2개만 테스트
        try:
            address = await get_address_from_coordinates(location.lat, location.lng)
            if address:
                print(f"✅ 좌표 ({location.lat:.6f}, {location.lng:.6f})")
                print(f"   변환된 주소: {address}")
            else:
                print(f"❌ 좌표 ({location.lat:.6f}, {location.lng:.6f}) - 변환 실패")
        except Exception as e:
            print(f"❌ 좌표 ({location.lat:.6f}, {location.lng:.6f}) - 오류: {e}")


async def test_static_map_generation(locations):
    """정적 지도 이미지 생성 테스트"""
    print("\n=== 정적 지도 이미지 생성 테스트 ===")

    if not locations:
        print("❌ 테스트할 위치 정보가 없습니다.")
        return

    # 테스트용 디렉토리 생성
    output_dir = Path("test_maps")
    output_dir.mkdir(exist_ok=True)

    for i, location in enumerate(locations[:2]):  # 처음 2개만 테스트
        try:
            # 기본 옵션으로 지도 생성
            options = MapOptions(width=500, height=400, zoom=15)
            image_data = await naver_map_service.get_static_map(location, options)

            if image_data:
                filename = output_dir / f"map_{i+1}_{location.name.replace(' ', '_')}.png"
                with open(filename, 'wb') as f:
                    f.write(image_data)
                print(f"✅ 지도 이미지 생성 완료: {filename}")
                print(f"   위치: {location.name or location.address}")
                print(f"   크기: {len(image_data)} bytes")
            else:
                print(f"❌ {location.name or location.address} - 이미지 생성 실패")
        except Exception as e:
            print(f"❌ {location.name or location.address} - 오류: {e}")


async def test_place_search():
    """장소 검색 테스트"""
    print("\n=== 장소 검색 테스트 ===")

    search_queries = [
        "강남역 맛집",
        "홍대 카페",
        "명동 쇼핑몰"
    ]

    for query in search_queries:
        try:
            places = await naver_map_service.search_places(query)
            if places:
                print(f"✅ '{query}' 검색 결과: {len(places)}개")
                for i, place in enumerate(places[:3]):  # 상위 3개만 표시
                    print(f"   {i+1}. {place.name}")
                    print(f"      주소: {place.address}")
                    print(f"      좌표: ({place.lat:.6f}, {place.lng:.6f})")
            else:
                print(f"❌ '{query}' - 검색 결과 없음")
        except Exception as e:
            print(f"❌ '{query}' - 오류: {e}")


async def test_nearby_search():
    """주변 장소 검색 테스트"""
    print("\n=== 주변 장소 검색 테스트 ===")

    try:
        # 강남역 주변 카페 검색
        places = await search_nearby_places("카페", "서울특별시 강남구 강남대로 396", 1000)
        if places:
            print(f"✅ 강남역 주변 카페 검색 결과: {len(places)}개")
            for i, place in enumerate(places[:3]):  # 상위 3개만 표시
                print(f"   {i+1}. {place.name}")
                print(f"      주소: {place.address}")
        else:
            print("❌ 강남역 주변 카페 검색 결과 없음")
    except Exception as e:
        print(f"❌ 주변 장소 검색 오류: {e}")


async def test_map_url_generation(locations):
    """지도 URL 생성 테스트"""
    print("\n=== 지도 URL 생성 테스트 ===")

    for location in locations[:2]:  # 처음 2개만 테스트
        try:
            map_url = naver_map_service.generate_map_url(location)
            print(f"✅ {location.name or location.address}")
            print(f"   네이버 지도 URL: {map_url}")
        except Exception as e:
            print(f"❌ {location.name or location.address} - 오류: {e}")


async def main():
    """메인 테스트 함수"""
    print("네이버 지도 API 연동 테스트를 시작합니다...\n")

    # 1. API 키 검증
    api_valid = await test_api_validation()
    if not api_valid:
        print("\n❌ API 키가 유효하지 않아 테스트를 중단합니다.")
        print("설정 파일(.env)에서 NAVER_MAP_CLIENT_ID와 NAVER_MAP_CLIENT_SECRET을 확인하세요.")
        return

    # 2. Geocoding 테스트
    locations = await test_geocoding()

    # 3. Reverse Geocoding 테스트
    if locations:
        await test_reverse_geocoding(locations)

    # 4. 정적 지도 이미지 생성 테스트
    if locations:
        await test_static_map_generation(locations)

    # 5. 장소 검색 테스트
    await test_place_search()

    # 6. 주변 장소 검색 테스트
    await test_nearby_search()

    # 7. 지도 URL 생성 테스트
    if locations:
        await test_map_url_generation(locations)

    print("\n=== 테스트 완료 ===")
    print("생성된 지도 이미지는 'test_maps' 폴더에서 확인하실 수 있습니다.")


if __name__ == "__main__":
    # 환경 변수 확인
    from src.config.settings import Settings

    print("환경 변수 확인:")
    print(f"NAVER_MAP_CLIENT_ID: {'설정됨' if Settings.NAVER_MAP_CLIENT_ID else '설정되지 않음'}")
    print(f"NAVER_MAP_CLIENT_SECRET: {'설정됨' if Settings.NAVER_MAP_CLIENT_SECRET else '설정되지 않음'}")
    print(f"NAVER_CLIENT_ID: {'설정됨' if Settings.NAVER_CLIENT_ID else '설정되지 않음'}")
    print(f"NAVER_CLIENT_SECRET: {'설정됨' if Settings.NAVER_CLIENT_SECRET else '설정되지 않음'}")
    print()

    # 실제 테스트 실행
    asyncio.run(main())
