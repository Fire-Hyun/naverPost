#!/usr/bin/env python3
"""
통합 테스트 스크립트

실제 API를 사용하여 전체 시스템의 동작을 검증합니다:
1. 웹 서버 상태 확인
2. 이미지 업로드
3. 블로그 포스트 생성
4. 파일 시스템 확인
5. 메타데이터 확인
"""

import requests
import json
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import tempfile
import os
from typing import Dict, Any, List

class IntegrationTester:
    """통합 테스트 클래스"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.test_session = None
        self.uploaded_files = []

    def create_test_image(self, text: str = "Test Image", size: tuple = (800, 600)) -> bytes:
        """테스트용 이미지 생성"""
        print(f"📷 Creating test image: {text}")

        # 이미지 생성
        image = Image.new('RGB', size, color='lightblue')
        draw = ImageDraw.Draw(image)

        # 텍스트 추가 (기본 폰트 사용)
        try:
            font = ImageFont.load_default()
        except:
            font = None

        text_bbox = draw.textbbox((0, 0), text, font=font) if font else (0, 0, 100, 20)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        x = (size[0] - text_width) // 2
        y = (size[1] - text_height) // 2

        draw.text((x, y), text, fill='black', font=font)

        # 바이트로 변환
        import io
        buf = io.BytesIO()
        image.save(buf, format='JPEG', quality=90)
        return buf.getvalue()

    def test_server_health(self) -> bool:
        """서버 상태 확인"""
        print("🔍 Testing server health...")

        try:
            response = self.session.get(f"{self.base_url}/health", timeout=10)

            if response.status_code == 200:
                health_data = response.json()
                print(f"✅ Server is healthy")
                print(f"   OpenAI configured: {health_data.get('config', {}).get('openai_configured', False)}")
                print(f"   Naver configured: {health_data.get('config', {}).get('naver_configured', False)}")
                return True
            else:
                print(f"❌ Server health check failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Cannot connect to server: {e}")
            return False

    def test_create_session(self) -> bool:
        """포스팅 세션 생성 테스트"""
        print("\n📝 Testing session creation...")

        session_data = {
            "category": "맛집",
            "personal_review": "통합 테스트를 위한 맛집 리뷰입니다. 음식이 정말 맛있었고 분위기도 좋았습니다. 직원들도 친절했고 가격도 합리적이었습니다. 다음에 또 방문하고 싶은 곳입니다.",
            "rating": 5,
            "visit_date": "2026-02-13",
            "companion": "친구",
            "ai_additional_script": "서울 강남 지역의 이탈리안 레스토랑에 대한 리뷰입니다.",
            "hashtags": "맛집,이탈리안,강남,추천"
        }

        try:
            response = self.session.post(
                f"{self.base_url}/api/sessions/create",
                json=session_data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                self.test_session = result.get("date_directory")
                print(f"✅ Session created: {self.test_session}")
                print(f"   Message: {result.get('message', 'No message')}")
                return True
            else:
                print(f"❌ Session creation failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Session creation error: {e}")
            return False

    def test_image_upload(self) -> bool:
        """이미지 업로드 테스트"""
        print("\n📤 Testing image upload...")

        if not self.test_session:
            print("❌ No test session available")
            return False

        # 테스트 이미지들 생성
        test_images = [
            ("음식사진1.jpg", self.create_test_image("Delicious Pasta", (800, 600))),
            ("음식사진2.jpg", self.create_test_image("Beautiful Interior", (1024, 768))),
            ("음식사진3.jpg", self.create_test_image("Dessert Time", (640, 480))),
        ]

        try:
            files = []
            for filename, image_data in test_images:
                files.append(('files', (filename, image_data, 'image/jpeg')))

            response = self.session.post(
                f"{self.base_url}/api/sessions/{self.test_session}/images",
                files=files,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                self.uploaded_files = result.get("uploaded_files", [])
                print(f"✅ Images uploaded successfully: {len(self.uploaded_files)} files")

                for file_info in self.uploaded_files:
                    print(f"   - {file_info['original_filename']} → {file_info['saved_filename']}")
                    print(f"     Size: {file_info['file_size']} bytes")
                    print(f"     URL: {file_info['url']}")

                return True
            else:
                print(f"❌ Image upload failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Image upload error: {e}")
            return False

    def test_blog_generation(self) -> bool:
        """블로그 생성 테스트"""
        print("\n🤖 Testing blog generation...")

        if not self.test_session:
            print("❌ No test session available")
            return False

        try:
            response = self.session.post(
                f"{self.base_url}/api/sessions/{self.test_session}/generate-blog",
                timeout=60  # AI 생성은 시간이 걸릴 수 있음
            )

            if response.status_code == 200:
                result = response.json()
                print("✅ Blog generated successfully")
                print(f"   Content length: {len(result.get('generated_content', ''))} characters")

                # 생성된 내용 일부 출력
                content = result.get('generated_content', '')
                if content:
                    preview = content[:200] + "..." if len(content) > 200 else content
                    print(f"   Preview: {preview}")

                print(f"   Blog file: {result.get('blog_file_path', 'N/A')}")

                # 메타데이터 확인
                metadata = result.get('metadata', {})
                print(f"   Tokens used: {metadata.get('total_tokens', 'N/A')}")
                print(f"   Model: {metadata.get('model_used', 'N/A')}")

                return True
            else:
                print(f"❌ Blog generation failed: {response.status_code}")
                error_response = response.text
                print(f"   Error: {error_response}")

                # OpenAI API 할당량 문제인지 확인
                if "quota" in error_response.lower():
                    print("💡 OpenAI API 할당량 초과 - 이는 예상된 문제일 수 있습니다.")
                    return "quota_exceeded"

                return False

        except requests.exceptions.Timeout:
            print("⏰ Blog generation timed out (60s)")
            return False
        except Exception as e:
            print(f"❌ Blog generation error: {e}")
            return False

    def verify_file_system(self) -> bool:
        """파일 시스템 확인"""
        print("\n📁 Verifying file system...")

        if not self.test_session:
            print("❌ No test session available")
            return False

        # 데이터 디렉토리 확인
        data_dir = Path("data") / self.test_session

        if not data_dir.exists():
            print(f"❌ Data directory not found: {data_dir}")
            return False

        print(f"✅ Data directory exists: {data_dir}")

        # 이미지 디렉토리 확인
        images_dir = data_dir / "images"

        if not images_dir.exists():
            print(f"❌ Images directory not found: {images_dir}")
            return False

        print(f"✅ Images directory exists: {images_dir}")

        # 이미지 파일들 확인
        image_files = list(images_dir.glob("*"))
        print(f"✅ Found {len(image_files)} image files:")

        for img_file in image_files:
            stat = img_file.stat()
            print(f"   - {img_file.name}")
            print(f"     Size: {stat.st_size} bytes")
            print(f"     Created: {time.ctime(stat.st_ctime)}")
            print(f"     Modified: {time.ctime(stat.st_mtime)}")

        # 메타데이터 파일 확인
        metadata_file = data_dir / "metadata.json"

        if metadata_file.exists():
            print(f"✅ Metadata file exists: {metadata_file}")

            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                print("   Metadata contents:")
                print(f"   - Category: {metadata.get('user_input', {}).get('category')}")
                print(f"   - Rating: {metadata.get('user_input', {}).get('rating')}")
                print(f"   - Images: {len(metadata.get('images', []))}")
                print(f"   - Workflow stage: {metadata.get('workflow_stage')}")

            except Exception as e:
                print(f"⚠️  Could not read metadata: {e}")
        else:
            print(f"❌ Metadata file not found: {metadata_file}")
            return False

        # 블로그 결과 파일 확인
        blog_file = data_dir / "blog_result.md"

        if blog_file.exists():
            print(f"✅ Blog result file exists: {blog_file}")

            try:
                with open(blog_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                print(f"   Blog content length: {len(content)} characters")

                # 해시태그나 특정 키워드 확인
                if "#맛집" in content:
                    print("   ✅ Contains hashtags")
                if "이탈리안" in content or "레스토랑" in content:
                    print("   ✅ Contains relevant keywords")

            except Exception as e:
                print(f"⚠️  Could not read blog file: {e}")
        else:
            print(f"⚠️  Blog result file not found: {blog_file}")
            # 블로그 생성이 실패했을 수도 있으므로 완전히 실패로 보지는 않음

        return True

    def run_full_test(self) -> Dict[str, Any]:
        """전체 테스트 실행"""
        print("🧪 시작: 통합 테스트 - 전체 기능 검증")
        print("=" * 60)

        results = {
            "server_health": False,
            "session_creation": False,
            "image_upload": False,
            "blog_generation": False,
            "file_system": False,
            "overall_success": False
        }

        # 1. 서버 상태 확인
        results["server_health"] = self.test_server_health()

        if not results["server_health"]:
            print("\n❌ 서버가 실행되지 않았습니다. 먼저 웹서버를 시작하세요:")
            print("   python3 -m src.web.app")
            return results

        # 2. 세션 생성
        results["session_creation"] = self.test_create_session()

        if not results["session_creation"]:
            return results

        # 3. 이미지 업로드
        results["image_upload"] = self.test_image_upload()

        # 4. 블로그 생성 (API 할당량 문제 가능)
        blog_result = self.test_blog_generation()
        if blog_result == "quota_exceeded":
            results["blog_generation"] = "quota_exceeded"
            print("⚠️  OpenAI API 할당량 초과로 인한 실패 - 시스템 자체는 정상")
        else:
            results["blog_generation"] = blog_result

        # 5. 파일 시스템 검증
        results["file_system"] = self.verify_file_system()

        # 전체 성공 판정
        core_functions_success = all([
            results["server_health"],
            results["session_creation"],
            results["image_upload"],
            results["file_system"]
        ])

        # 블로그 생성은 API 할당량 문제로 실패할 수 있으므로 별도 처리
        if results["blog_generation"] == "quota_exceeded":
            results["overall_success"] = core_functions_success
            print("\n📊 테스트 결과: 핵심 기능 모두 정상 (AI 생성은 API 할당량 문제)")
        else:
            results["overall_success"] = core_functions_success and results["blog_generation"]
            if results["overall_success"]:
                print("\n🎉 모든 테스트 통과! 시스템이 완벽하게 작동합니다.")
            else:
                print("\n⚠️  일부 테스트 실패")

        # 결과 요약
        print("\n📋 테스트 결과 요약:")
        for test_name, result in results.items():
            if test_name == "overall_success":
                continue
            status = "✅" if result is True else "❌" if result is False else "⚠️ "
            print(f"   {status} {test_name}: {result}")

        return results

def main():
    """메인 실행 함수"""
    tester = IntegrationTester()
    results = tester.run_full_test()

    # 테스트 세션 정보 출력
    if tester.test_session:
        print(f"\n📍 테스트 세션: {tester.test_session}")
        print("   다음 경로에서 결과를 확인할 수 있습니다:")
        print(f"   - data/{tester.test_session}/")
        print(f"   - http://localhost:8000/data/{tester.test_session}/images/")

    return results["overall_success"]

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)