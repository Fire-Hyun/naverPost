#!/usr/bin/env python3
"""
기본 프로젝트 구조 및 모듈 임포트 테스트
"""

import sys
from pathlib import Path

# 프로젝트 루트를 파이썬 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

def test_project_structure():
    """프로젝트 구조 테스트"""
    print("🧪 프로젝트 구조 테스트")
    print("=" * 50)

    # 필수 디렉토리 확인
    required_dirs = [
        "src/web",
        "src/content",
        "src/quality",
        "src/naver",
        "src/external",
        "src/storage",
        "src/config",
        "src/utils",
        "data",
        "uploads",
        "templates",
        "tests"
    ]

    for dir_path in required_dirs:
        path = Path(dir_path)
        status = "✅" if path.exists() else "❌"
        print(f"{status} {dir_path}")

    print()

def test_file_structure():
    """핵심 파일 존재 확인"""
    print("📁 핵심 파일 구조 테스트")
    print("=" * 50)

    required_files = [
        "src/config/settings.py",
        "src/utils/logger.py",
        "src/utils/exceptions.py",
        "src/content/models.py",
        "src/web/app.py",
        "src/web/routes/upload.py",
        "src/storage/data_manager.py",
        "src/web/static/index.html",
        "requirements.txt",
        ".env.example",
        "README.md"
    ]

    for file_path in required_files:
        path = Path(file_path)
        status = "✅" if path.exists() else "❌"
        size = f"({path.stat().st_size} bytes)" if path.exists() else ""
        print(f"{status} {file_path} {size}")

    print()

def test_basic_imports():
    """기본 모듈 임포트 테스트"""
    print("📦 기본 모듈 임포트 테스트")
    print("=" * 50)

    import_tests = [
        ("src.config.settings", "Settings"),
        ("src.utils.exceptions", "BlogSystemError"),
        ("src.content.models", "UserExperience"),
        ("src.storage.data_manager", "DataManager"),
    ]

    for module_name, class_name in import_tests:
        try:
            module = __import__(module_name, fromlist=[class_name])
            cls = getattr(module, class_name)
            print(f"✅ {module_name}.{class_name}")
        except ImportError as e:
            print(f"❌ {module_name}.{class_name} - ImportError: {e}")
        except AttributeError as e:
            print(f"❌ {module_name}.{class_name} - AttributeError: {e}")
        except Exception as e:
            print(f"❌ {module_name}.{class_name} - Error: {e}")

    print()

def test_environment_setup():
    """환경 설정 테스트"""
    print("⚙️ 환경 설정 테스트")
    print("=" * 50)

    # .env 파일 존재 확인
    env_file = Path(".env")
    env_example = Path(".env.example")

    if env_example.exists():
        print("✅ .env.example 파일 존재")
    else:
        print("❌ .env.example 파일 없음")

    if env_file.exists():
        print("✅ .env 파일 존재")
    else:
        print("⚠️ .env 파일 없음 (.env.example을 복사하여 생성 필요)")

    print()

def main():
    """메인 테스트 실행"""
    print("🚀 네이버 블로그 포스팅 자동화 시스템 구조 테스트")
    print("=" * 60)
    print()

    test_project_structure()
    test_file_structure()
    test_basic_imports()
    test_environment_setup()

    print("✅ 기본 구조 테스트 완료!")
    print()
    print("다음 단계:")
    print("1. pip install -r requirements.txt (의존성 설치)")
    print("2. cp .env.example .env (환경 설정)")
    print("3. .env 파일 편집 (API 키 및 계정 정보 입력)")
    print("4. python -m src.web.app (웹 서버 실행)")

if __name__ == "__main__":
    main()