#!/usr/bin/env python3
"""
간단한 워크플로우 테스트
"""
import asyncio
import aiohttp
import json

async def test_workflow():
    base_url = "http://localhost:8001"

    async with aiohttp.ClientSession() as session:
        print("=== 기존 데이터로 워크플로우 시작 ===")
        payload = {
            "date_directory": "20260214(자라)",
            "auto_upload_to_naver": False  # 일단 네이버 업로드 없이 테스트
        }

        try:
            async with session.post(
                f"{base_url}/api/workflow/process-existing",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    workflow_id = data["workflow_id"]
                    print(f"워크플로우 시작됨: {workflow_id}")

                    # 상태 확인 (5초 대기)
                    await asyncio.sleep(5)

                    async with session.get(f"{base_url}/api/workflow/status/{workflow_id}") as status_resp:
                        if status_resp.status == 200:
                            status_data = await status_resp.json()
                            print(f"상태: {status_data['status']}")
                            print(f"진행률: {status_data['progress_percentage']:.1f}%")
                            print(f"메시지: {status_data['message']}")

                            if status_data.get('results'):
                                results = status_data['results']
                                print("\n=== 결과 요약 ===")
                                if 'blog_content_length' in results:
                                    print(f"블로그 콘텐츠 길이: {results['blog_content_length']}자")
                                if 'quality_score' in results:
                                    print(f"품질 점수: {results['quality_score']}")
                                if 'naver_upload' in results:
                                    upload_result = results['naver_upload']
                                    print(f"네이버 업로드: {upload_result.get('message', 'N/A')}")
                        else:
                            print(f"상태 확인 실패: {status_resp.status}")
                else:
                    print(f"워크플로우 시작 실패: {resp.status}")
                    error_data = await resp.json()
                    print(f"오류: {error_data}")
        except Exception as e:
            print(f"오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(test_workflow())