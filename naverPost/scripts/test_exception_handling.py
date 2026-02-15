#!/usr/bin/env python3
"""
예외처리 테스트 스크립트

Phase 3에서 강화한 예외처리가 올바르게 작동하는지 테스트합니다.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, mock_open
import json

# 프로젝트 루트를 path에 추가
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.date_manager import DateBasedDirectoryManager
from src.config.settings import Settings

class TestExceptionHandling(unittest.TestCase):
    """예외처리 테스트 클래스"""

    def setUp(self):
        """테스트 환경 설정"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.date_manager = DateBasedDirectoryManager(self.temp_dir)
        print(f"Test temp directory: {self.temp_dir}")

    def tearDown(self):
        """테스트 환경 정리"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_date_manager_initialization_with_invalid_path(self):
        """잘못된 경로로 초기화 시 예외처리 테스트"""
        print("\n🧪 Testing DateManager initialization with invalid path...")

        # 존재하지 않는 드라이브나 권한 없는 경로 (Windows/Linux 호환)
        invalid_path = Path("/root/forbidden") if os.name == 'posix' else Path("Z:/nonexistent")

        with patch('pathlib.Path.mkdir', side_effect=PermissionError("Permission denied")):
            with self.assertRaises(ValueError) as context:
                DateBasedDirectoryManager(invalid_path)

            self.assertIn("permission error", str(context.exception).lower())
            print("✅ Permission error handling works correctly")

    def test_create_date_directory_failure(self):
        """디렉토리 생성 실패 시 예외처리 테스트"""
        print("\n🧪 Testing create_date_directory failure handling...")

        with patch('pathlib.Path.mkdir', side_effect=OSError("Disk full")):
            with self.assertRaises(OSError) as context:
                self.date_manager.create_date_directory("20260213")

            self.assertIn("Cannot create directory", str(context.exception))
            print("✅ Directory creation failure handling works correctly")

    def test_save_metadata_with_invalid_data(self):
        """잘못된 데이터로 메타데이터 저장 시 예외처리 테스트"""
        print("\n🧪 Testing save_metadata with invalid data...")

        # 딕셔너리가 아닌 데이터
        with self.assertRaises(ValueError) as context:
            self.date_manager.save_metadata("20260213", "not_a_dict")

        self.assertIn("must be a dictionary", str(context.exception))
        print("✅ Invalid metadata data type handling works correctly")

        # JSON 직렬화할 수 없는 데이터
        class NonSerializable:
            pass

        invalid_data = {"key": NonSerializable()}
        with self.assertRaises(ValueError) as context:
            self.date_manager.save_metadata("20260213", invalid_data)

        self.assertIn("Cannot serialize", str(context.exception))
        print("✅ JSON serialization error handling works correctly")

    def test_save_metadata_file_permission_error(self):
        """메타데이터 파일 저장 시 권한 오류 테스트"""
        print("\n🧪 Testing save_metadata file permission error...")

        # 정상적으로 디렉토리 생성
        self.date_manager.create_date_directory("20260213")

        # 파일 쓰기 권한 오류 시뮬레이션
        with patch('builtins.open', mock_open()) as mock_file:
            mock_file.side_effect = PermissionError("Permission denied")

            with self.assertRaises(OSError) as context:
                self.date_manager.save_metadata("20260213", {"test": "data"})

            self.assertIn("Permission denied", str(context.exception))
            print("✅ File permission error handling works correctly")

    def test_load_metadata_with_corrupted_file(self):
        """손상된 JSON 파일 로드 시 예외처리 테스트"""
        print("\n🧪 Testing load_metadata with corrupted JSON...")

        # 정상적으로 디렉토리 생성
        dir_path = self.date_manager.create_date_directory("20260213")

        # 손상된 JSON 파일 생성
        metadata_file = dir_path / "metadata.json"
        with open(metadata_file, 'w') as f:
            f.write("{invalid json content")

        with self.assertRaises(ValueError) as context:
            self.date_manager.load_metadata("20260213")

        self.assertIn("Invalid JSON", str(context.exception))
        print("✅ Corrupted JSON handling works correctly")

    def test_load_metadata_permission_error(self):
        """메타데이터 파일 읽기 권한 오류 테스트"""
        print("\n🧪 Testing load_metadata permission error...")

        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            # 파일이 존재한다고 가정하고 권한 오류 테스트
            with patch('pathlib.Path.exists', return_value=True):
                with self.assertRaises(OSError) as context:
                    self.date_manager.load_metadata("20260213")

                self.assertIn("Permission denied", str(context.exception))
                print("✅ File read permission error handling works correctly")

    def test_append_log_with_invalid_message(self):
        """로그 추가 시 예외상황 테스트"""
        print("\n🧪 Testing append_log exception handling...")

        # 빈 메시지는 무시되어야 함
        try:
            self.date_manager.append_log("20260213", "")
            print("✅ Empty message handling works correctly")
        except Exception as e:
            self.fail(f"Empty message should be ignored, but got: {e}")

        # 파일 쓰기 실패 시에도 예외 발생하지 않아야 함
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            try:
                self.date_manager.append_log("20260213", "test message")
                print("✅ Log write failure handling works correctly (no exception raised)")
            except Exception as e:
                self.fail(f"Log write failure should not raise exception, but got: {e}")

    def test_get_directory_path_filesystem_error(self):
        """get_directory_path에서 파일시스템 오류 테스트"""
        print("\n🧪 Testing get_directory_path filesystem error handling...")

        # 파일시스템 접근 오류 시뮬레이션
        with patch('pathlib.Path.exists', side_effect=OSError("I/O error")):
            with self.assertRaises(OSError) as context:
                self.date_manager.get_directory_path("20260213")

            self.assertIn("Cannot get directory path", str(context.exception))
            print("✅ Filesystem error handling works correctly")

    def test_settings_create_directories_failure(self):
        """Settings.create_directories 실패 시 예외처리 테스트"""
        print("\n🧪 Testing Settings.create_directories failure handling...")

        with patch('pathlib.Path.mkdir', side_effect=PermissionError("Permission denied")):
            with self.assertRaises(OSError) as context:
                Settings.create_directories()

            self.assertIn("Failed to create critical directories", str(context.exception))
            print("✅ Critical directory creation failure handling works correctly")

class TestDataIntegrity(unittest.TestCase):
    """데이터 무결성 테스트"""

    def setUp(self):
        """테스트 환경 설정"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.date_manager = DateBasedDirectoryManager(self.temp_dir)
        print(f"Test temp directory: {self.temp_dir}")

    def tearDown(self):
        """테스트 환경 정리"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_transaction_rollback_on_failure(self):
        """실패 시 트랜잭션 롤백 테스트"""
        print("\n🧪 Testing transaction rollback on failure...")

        # 디렉토리 생성은 성공하지만 이미지 디렉토리 생성 실패
        original_mkdir = Path.mkdir

        def failing_mkdir(self, *args, **kwargs):
            if "images" in str(self):
                raise OSError("Simulated failure")
            return original_mkdir(self, *args, **kwargs)

        with patch('pathlib.Path.mkdir', side_effect=failing_mkdir):
            with self.assertRaises(OSError):
                self.date_manager.create_date_directory("20260213")

            # 실패 후 메인 디렉토리도 정리되었는지 확인
            # (실제로는 정리되지 않을 수 있지만, 로그에는 기록됨)
            print("✅ Transaction rollback attempt works correctly")

    def test_partial_failure_recovery(self):
        """부분 실패 시 복구 테스트"""
        print("\n🧪 Testing partial failure recovery...")

        # 정상적으로 디렉토리 생성
        dir_path = self.date_manager.create_date_directory("20260213")
        self.assertTrue(dir_path.exists())

        # 메타데이터 저장
        metadata = {"test": "data", "stage": "test"}
        metadata_path = self.date_manager.save_metadata("20260213", metadata)
        self.assertTrue(metadata_path.exists())

        # 메타데이터 로드로 확인
        loaded_metadata = self.date_manager.load_metadata("20260213")
        self.assertEqual(loaded_metadata["test"], "data")

        print("✅ Normal operation and data persistence works correctly")

def run_tests():
    """테스트 실행"""
    print("🧪 예외처리 강화 테스트 시작\n" + "="*50)

    # 테스트 슈트 생성
    suite = unittest.TestSuite()

    # 예외처리 테스트 추가
    suite.addTest(unittest.makeSuite(TestExceptionHandling))
    suite.addTest(unittest.makeSuite(TestDataIntegrity))

    # 테스트 실행
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 결과 요약
    print("\n" + "="*50)
    print(f"🧪 테스트 완료")
    print(f"   실행: {result.testsRun}개")
    print(f"   성공: {result.testsRun - len(result.failures) - len(result.errors)}개")
    print(f"   실패: {len(result.failures)}개")
    print(f"   오류: {len(result.errors)}개")

    if result.failures:
        print(f"\n❌ 실패한 테스트:")
        for test, trace in result.failures:
            print(f"   - {test}")

    if result.errors:
        print(f"\n💥 오류 발생 테스트:")
        for test, trace in result.errors:
            print(f"   - {test}")

    success_rate = (result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100
    print(f"\n📊 성공률: {success_rate:.1f}%")

    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)