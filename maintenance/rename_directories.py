#!/usr/bin/env python3
"""
디렉토리명 변경 스크립트

data/yyyyMMdd -> data/yyyyMMdd(상호명) 형식으로 변경
메타데이터에서 상호명 추출하여 적용
"""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import re

class DirectoryRenamer:
    """디렉토리명 변경 클래스"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.rename_log = []

    def extract_business_name(self, metadata: Dict) -> str:
        """메타데이터에서 상호명 추출"""
        try:
            # 1. AI 스크립트에서 상호명 추출 시도
            ai_script = metadata.get("user_input", {}).get("ai_additional_script", "")
            if ai_script:
                # "○○○ 레스토랑", "○○○ 카페" 등의 패턴 찾기
                business_patterns = [
                    r'([가-힣]+)\s*(?:레스토랑|카페|식당|상회|음식점|매장|가게)',
                    r'([가-힣A-Za-z]+)\s*(?:Restaurant|Cafe|Store)',
                    r'이름은\s*([가-힣A-Za-z]+)',
                    r'([가-힣A-Za-z]{2,8})에서',  # "○○○에서" 패턴
                ]

                for pattern in business_patterns:
                    match = re.search(pattern, ai_script)
                    if match:
                        name = match.group(1).strip()
                        if len(name) >= 2 and name not in ['서울', '강남', '홍대', '명동']:
                            return name

            # 2. 개인 리뷰에서 상호명 추출 시도
            personal_review = metadata.get("user_input", {}).get("personal_review", "")
            if personal_review:
                # 개인 리뷰에서 상호명 패턴 찾기
                review_patterns = [
                    r'([가-힣]{2,8})\s*(?:에서|에|은|는|이|가)\s',
                    r'([가-힣A-Za-z]{2,8})\s*(?:라는|이라는)\s*(?:곳|가게|식당)',
                ]

                for pattern in review_patterns:
                    match = re.search(pattern, personal_review)
                    if match:
                        name = match.group(1).strip()
                        if len(name) >= 2 and name not in ['음식', '분위기', '직원', '가격', '서비스']:
                            return name

            # 3. 카테고리 기반 기본명
            category = metadata.get("user_input", {}).get("category", "기타")
            if category == "맛집":
                return "맛집"
            elif category == "카페":
                return "카페"
            elif category == "호텔":
                return "호텔"
            else:
                return category

        except Exception as e:
            print(f"   Warning: Error extracting business name: {e}")
            return "기타"

    def analyze_directories(self) -> Dict[str, Dict]:
        """현재 디렉토리들 분석"""
        print("📋 현재 데이터 디렉토리 분석...")

        if not self.data_dir.exists():
            print(f"❌ 데이터 디렉토리가 없습니다: {self.data_dir}")
            return {}

        # 날짜 패턴 디렉토리 찾기
        date_pattern = re.compile(r'^\d{8}(_\d+)?$')
        directories = {}

        for item in self.data_dir.iterdir():
            if item.is_dir() and date_pattern.match(item.name):
                print(f"\n📁 분석 중: {item.name}")

                # 메타데이터 로드
                metadata_file = item / "metadata.json"
                if not metadata_file.exists():
                    print(f"   ⚠️  메타데이터 없음")
                    directories[item.name] = {
                        "path": item,
                        "business_name": "정보없음",
                        "has_metadata": False,
                        "metadata": {}
                    }
                    continue

                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)

                    business_name = self.extract_business_name(metadata)
                    category = metadata.get("user_input", {}).get("category", "기타")

                    directories[item.name] = {
                        "path": item,
                        "business_name": business_name,
                        "category": category,
                        "has_metadata": True,
                        "metadata": metadata
                    }

                    print(f"   ✅ 상호명: {business_name}")
                    print(f"   📂 카테고리: {category}")

                except Exception as e:
                    print(f"   ❌ 메타데이터 읽기 실패: {e}")
                    directories[item.name] = {
                        "path": item,
                        "business_name": "오류",
                        "has_metadata": False,
                        "metadata": {}
                    }

        return directories

    def clean_legacy_directories(self):
        """레거시 디렉토리 정리"""
        print("\n🧹 레거시 디렉토리 정리...")

        legacy_dirs = ["metadata", "posts"]
        for legacy in legacy_dirs:
            legacy_path = self.data_dir / legacy
            if legacy_path.exists():
                try:
                    shutil.rmtree(legacy_path)
                    print(f"   ✅ 정리 완료: {legacy}")
                except Exception as e:
                    print(f"   ❌ 정리 실패: {legacy} - {e}")

    def generate_new_names(self, directories: Dict[str, Dict]) -> Dict[str, str]:
        """새로운 디렉토리명 생성"""
        print("\n🏷️  새 디렉토리명 생성...")

        new_names = {}
        name_counters = {}

        for old_name, info in directories.items():
            business_name = info["business_name"]

            # 기본 날짜 부분 추출
            date_part = old_name.split('_')[0]  # 20260212_14 -> 20260212

            # 새 이름 생성
            base_new_name = f"{date_part}({business_name})"

            # 중복 확인 및 번호 추가
            if base_new_name in name_counters:
                name_counters[base_new_name] += 1
                final_new_name = f"{date_part}_{name_counters[base_new_name]}({business_name})"
            else:
                name_counters[base_new_name] = 1
                final_new_name = base_new_name

            new_names[old_name] = final_new_name
            print(f"   {old_name} → {final_new_name}")

        return new_names

    def rename_directories(self, directories: Dict[str, Dict], new_names: Dict[str, str], dry_run: bool = True) -> List[str]:
        """디렉토리 이름 변경 실행"""
        print(f"\n🔄 디렉토리 이름 변경 {'(시뮬레이션)' if dry_run else '(실제 실행)'}...")

        renamed = []
        errors = []

        for old_name, new_name in new_names.items():
            old_path = directories[old_name]["path"]
            new_path = self.data_dir / new_name

            print(f"   {old_name} → {new_name}")

            if not dry_run:
                try:
                    # 이름 변경
                    old_path.rename(new_path)
                    renamed.append(f"{old_name} → {new_name}")

                    # 로그 업데이트 (디렉토리 내부 로그에도 기록)
                    log_file = new_path / "log.txt"
                    if log_file.exists():
                        with open(log_file, 'a', encoding='utf-8') as f:
                            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Directory renamed from {old_name} to {new_name}\n")

                    print(f"      ✅ 변경 완료")

                except Exception as e:
                    print(f"      ❌ 변경 실패: {e}")
                    errors.append(f"{old_name}: {e}")
            else:
                print(f"      🔍 [시뮬레이션] 변경 예정")

        if errors:
            print(f"\n❌ 오류 발생: {len(errors)}개")
            for error in errors:
                print(f"   - {error}")

        return renamed

    def run(self, dry_run: bool = True) -> Dict:
        """전체 작업 실행"""
        print("🏷️  디렉토리명에 상호명 추가 작업 시작")
        print("=" * 50)

        # 1. 레거시 정리
        self.clean_legacy_directories()

        # 2. 현재 디렉토리 분석
        directories = self.analyze_directories()

        if not directories:
            print("❌ 변경할 디렉토리가 없습니다.")
            return {"success": False, "message": "No directories to rename"}

        # 3. 새 이름 생성
        new_names = self.generate_new_names(directories)

        # 4. 이름 변경 실행
        renamed = self.rename_directories(directories, new_names, dry_run)

        # 결과 요약
        result = {
            "success": True,
            "dry_run": dry_run,
            "analyzed": len(directories),
            "renamed": len(renamed),
            "directories": directories,
            "new_names": new_names,
            "renamed_list": renamed
        }

        print(f"\n📊 작업 완료:")
        print(f"   분석된 디렉토리: {len(directories)}개")
        print(f"   {'시뮬레이션' if dry_run else '실제 변경'}: {len(renamed)}개")

        if dry_run:
            print(f"\n실제 변경을 원하면 --execute 옵션으로 실행하세요.")

        return result

def main():
    """메인 실행 함수"""
    import sys
    from datetime import datetime

    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == "--execute":
        dry_run = False
        print("⚠️  실제 변경 모드로 실행됩니다!")

    renamer = DirectoryRenamer()
    result = renamer.run(dry_run)

    return result["success"]

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)