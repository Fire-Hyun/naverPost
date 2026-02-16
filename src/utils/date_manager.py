"""
날짜 기반 디렉토리 관리 유틸리티

블로그 포스팅 데이터를 yyyyMMdd 날짜 단위로 체계적으로 관리합니다.
동일 날짜에 여러 포스팅이 있는 경우 _2, _3 형태로 구분합니다.
"""

import json
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any, Optional, List
import logging
import re

from src.config.settings import Settings


class DateBasedDirectoryManager:
    """날짜 기반 디렉토리 관리 클래스"""

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Args:
            base_dir: 베이스 데이터 디렉토리 (기본: Settings.DATA_DIR)
        """
        try:
            self.base_dir = base_dir or Settings.DATA_DIR

            # 베이스 디렉토리 생성 (예외처리 강화)
            self.base_dir.mkdir(parents=True, exist_ok=True)
            logging.info(f"DateManager initialized with base_dir: {self.base_dir}")

        except PermissionError as e:
            logging.error(f"Permission denied creating base directory {self.base_dir}: {e}")
            raise ValueError(f"Cannot create base directory due to permission error: {e}")
        except OSError as e:
            logging.error(f"OS error creating base directory {self.base_dir}: {e}")
            raise ValueError(f"Cannot create base directory due to OS error: {e}")
        except Exception as e:
            logging.error(f"Unexpected error initializing DateManager: {e}")
            raise

    def _validate_date_format(self, date_str: str) -> bool:
        """날짜 형식 유효성 검사 (yyyyMMdd)"""
        if not re.match(r'^\d{8}$', date_str):
            return False

        try:
            datetime.strptime(date_str, '%Y%m%d')
            return True
        except ValueError:
            return False

    def _sanitize_business_name(self, name: str) -> str:
        """디렉토리명에 안전한 상호명으로 정규화"""
        cleaned = re.sub(r'[<>:"/\\|?*]', '', (name or '').strip())
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _extract_business_name_from_input(self, user_input: Dict[str, Any]) -> str:
        """사용자 입력에서 상호명 추출"""
        try:
            # 0. 명시적 상호명 필드 우선
            explicit_fields = [
                "resolved_store_name",
                "store_name",
                "place_name",
                "business_name",
                "store",
                "place",
            ]
            for key in explicit_fields:
                value = user_input.get(key)
                if isinstance(value, str):
                    clean = self._sanitize_business_name(value)
                    if len(clean) >= 2:
                        return clean

            # location이 문자열 주소/상호명으로 들어오는 경우
            location = user_input.get("location")
            if isinstance(location, str):
                clean_location = self._sanitize_business_name(location)
                if clean_location and not re.match(r'^\d+(\.\d+)?$', clean_location):
                    return clean_location

            # 해시태그에서 상호명 추출 시도
            hashtags = user_input.get("hashtags", [])
            if isinstance(hashtags, list):
                for tag in hashtags:
                    if not isinstance(tag, str):
                        continue
                    for m in re.findall(r'#([가-힣A-Za-z0-9][가-힣A-Za-z0-9\s]{1,20})', tag):
                        candidate = self._sanitize_business_name(m)
                        if len(candidate) >= 2:
                            return candidate

            # 1. AI 스크립트에서 상호명 추출 시도
            ai_script = user_input.get("ai_additional_script", "")
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
                        name = self._sanitize_business_name(match.group(1))
                        if len(name) >= 2 and name not in ['서울', '강남', '홍대', '명동']:
                            return name

            # 2. 개인 리뷰에서 상호명 추출 시도
            personal_review = user_input.get("personal_review", "")
            if personal_review:
                # 개인 리뷰에서 상호명 패턴 찾기
                review_patterns = [
                    r'([가-힣]{2,8})\s*(?:에서|에|은|는|이|가)\s',
                    r'([가-힣A-Za-z]{2,8})\s*(?:라는|이라는)\s*(?:곳|가게|식당)',
                ]

                for pattern in review_patterns:
                    match = re.search(pattern, personal_review)
                    if match:
                        name = self._sanitize_business_name(match.group(1))
                        if len(name) >= 2 and name not in ['음식', '분위기', '직원', '가격', '서비스']:
                            return name

            # 3. 상호명을 찾지 못한 경우에도 괄호 구조를 유지
            return "상호미입력"

        except Exception as e:
            logging.warning(f"Error extracting business name: {e}")
            return "상호미입력"

    def _get_available_directory_name(self, date_str: str, business_name: Optional[str] = None) -> str:
        """중복되지 않는 디렉토리명 반환 (상호명 포함)"""
        if not self._validate_date_format(date_str):
            raise ValueError(f"Invalid date format: {date_str}. Expected yyyyMMdd format.")

        # 항상 yyyyMMdd(상호명) 형식 사용
        clean_business_name = self._sanitize_business_name(business_name or "상호미입력") or "상호미입력"
        base_name = f"{date_str}({clean_business_name})"

        # 기본 이름이 사용 가능한지 확인
        if not (self.base_dir / base_name).exists():
            return base_name

        # 중복된 경우 yyyyMMdd(상호명)_2, _3 형태로 생성
        counter = 2
        while True:
            candidate = f"{base_name}_{counter}"

            if not (self.base_dir / candidate).exists():
                return candidate
            counter += 1

    def create_date_directory(self, date_str: str, user_input: Optional[Dict[str, Any]] = None) -> Path:
        """
        날짜 기반 디렉토리 생성 (예외처리 강화, 상호명 포함)

        Args:
            date_str: 날짜 문자열 (yyyyMMdd)
            user_input: 사용자 입력 데이터 (상호명 추출용)

        Returns:
            생성된 디렉토리 경로

        Raises:
            ValueError: 잘못된 날짜 형식인 경우
            OSError: 디렉토리 생성 실패
        """
        try:
            # 사용자 입력에서 상호명 추출
            business_name = None
            if user_input:
                business_name = self._extract_business_name_from_input(user_input)
                logging.info(f"Extracted business name: {business_name}")

            # 디렉토리명 생성 (상호명 포함)
            dir_name = self._get_available_directory_name(date_str, business_name)
            dir_path = self.base_dir / dir_name

            # 메인 디렉토리 생성
            try:
                dir_path.mkdir(exist_ok=True)
                logging.info(f"Created main directory: {dir_path}")
            except PermissionError as e:
                logging.error(f"Permission denied creating directory {dir_path}: {e}")
                raise OSError(f"Cannot create directory {dir_path}: Permission denied")
            except OSError as e:
                logging.error(f"Failed to create directory {dir_path}: {e}")
                raise OSError(f"Cannot create directory {dir_path}: {e}")

            # 이미지 하위 디렉토리 생성
            try:
                images_dir = dir_path / "images"
                images_dir.mkdir(exist_ok=True)
                logging.info(f"Created images subdirectory: {images_dir}")
            except Exception as e:
                logging.error(f"Failed to create images directory: {e}")
                # 메인 디렉토리 정리
                try:
                    if dir_path.exists():
                        dir_path.rmdir()
                except:
                    pass  # 정리 실패해도 진행
                raise OSError(f"Cannot create images subdirectory: {e}")

            # 생성 로그 추가 (예외처리 포함)
            try:
                self.append_log(dir_name, f"Directory created: {dir_path}")
            except Exception as e:
                logging.warning(f"Failed to write creation log: {e}")
                # 로그 실패는 치명적이지 않으므로 계속 진행

            logging.info(f"Successfully created date directory: {dir_name}")
            return dir_path

        except (ValueError, OSError):
            # 이미 처리된 예외는 재발생
            raise
        except Exception as e:
            logging.error(f"Unexpected error creating date directory {date_str}: {e}")
            raise OSError(f"Unexpected error creating directory: {e}")

    def get_directory_path(self, date_str: str) -> Optional[Path]:
        """
        기존 날짜 디렉토리 경로 반환 (존재하지 않으면 None) - 예외처리 강화

        Args:
            date_str: 날짜 문자열 또는 디렉토리명 (yyyyMMdd 또는 yyyyMMdd_n)

        Returns:
            디렉토리 경로 또는 None

        Raises:
            OSError: 파일시스템 접근 오류
        """
        try:
            if not date_str:
                return None
            filesystem_errors = []

            # 직접 디렉토리명인 경우
            try:
                direct_path = self.base_dir / date_str
                if direct_path.exists():
                    return direct_path
            except (OSError, PermissionError) as e:
                logging.warning(f"Cannot check direct path {date_str}: {e}")
                filesystem_errors.append(e)

            # 날짜 문자열인 경우 가장 최근 디렉토리 찾기
            try:
                if self._validate_date_format(date_str):
                    # 기본 날짜 디렉토리가 있는지 확인 (기존 형식)
                    base_path = self.base_dir / date_str
                    try:
                        if base_path.exists():
                            return base_path
                    except (OSError, PermissionError) as e:
                        logging.warning(f"Cannot check base path {base_path}: {e}")
                        filesystem_errors.append(e)

                    # 상호명 포함 형식과 기존 형식 모두 확인
                    patterns = [
                        f"{date_str}",            # 기존 형식: yyyyMMdd
                        f"{date_str}_*",          # 기존 형식: yyyyMMdd_N
                        f"{date_str}(*)",         # 새 형식: yyyyMMdd(상호명)
                        f"{date_str}(*)_*",       # 새 형식: yyyyMMdd(상호명)_N
                        f"{date_str}_*(*)",       # 과거 형식: yyyyMMdd_N(상호명)
                    ]

                    all_matching_dirs = []
                    for pattern in patterns:
                        try:
                            matching_dirs = list(self.base_dir.glob(pattern))
                            all_matching_dirs.extend(matching_dirs)
                        except (OSError, PermissionError) as e:
                            logging.warning(f"Cannot glob pattern {pattern}: {e}")
                            filesystem_errors.append(e)
                            continue

                    if all_matching_dirs:
                        # 가장 최근 생성된 디렉토리 반환
                        return max(all_matching_dirs, key=lambda p: p.stat().st_ctime)

            except Exception as e:
                logging.warning(f"Error validating date format for {date_str}: {e}")

            if filesystem_errors:
                first_error = filesystem_errors[0]
                raise OSError(f"Cannot get directory path: {first_error}")

            return None

        except Exception as e:
            logging.error(f"Unexpected error getting directory path for {date_str}: {e}")
            raise OSError(f"Cannot get directory path: {e}")

    def get_images_dir(self, date_str: str) -> Path:
        """이미지 디렉토리 경로 반환"""
        dir_path = self.get_directory_path(date_str)
        if not dir_path:
            dir_path = self.create_date_directory(date_str)

        images_dir = dir_path / "images"
        images_dir.mkdir(exist_ok=True)
        return images_dir

    def save_metadata(self, date_str: str, data: Dict[str, Any]) -> Path:
        """
        사용자 입력 메타데이터 저장 (예외처리 강화)

        Args:
            date_str: 날짜 문자열
            data: 저장할 메타데이터

        Returns:
            저장된 파일 경로

        Raises:
            ValueError: 잘못된 입력 데이터
            OSError: 파일 저장 실패
        """
        try:
            # 입력 데이터 검증
            if not isinstance(data, dict):
                raise ValueError("Metadata must be a dictionary")

            # 디렉토리 경로 확인/생성
            try:
                dir_path = self.get_directory_path(date_str)
                if not dir_path:
                    # user_input을 사용하여 상호명이 포함된 디렉토리 생성
                    user_input = data.get("user_input", {}) if isinstance(data, dict) else {}
                    dir_path = self.create_date_directory(date_str, user_input)
                    logging.info(f"Created directory for metadata: {dir_path}")
            except Exception as e:
                logging.error(f"Failed to get/create directory for {date_str}: {e}")
                raise OSError(f"Cannot access directory for {date_str}: {e}")

            metadata_file = dir_path / "metadata.json"

            # 메타데이터 구성
            try:
                enhanced_data = {
                    "created_at": datetime.now().isoformat(),
                    "date_directory": dir_path.name,
                    **data
                }
            except Exception as e:
                logging.error(f"Failed to prepare metadata: {e}")
                raise ValueError(f"Invalid metadata format: {e}")

            # 파일 저장
            try:
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(enhanced_data, f, ensure_ascii=False, indent=2)
                logging.info(f"Metadata saved successfully: {metadata_file}")
            except PermissionError as e:
                logging.error(f"Permission denied saving metadata {metadata_file}: {e}")
                raise OSError(f"Cannot save metadata: Permission denied")
            except (OSError, IOError) as e:
                logging.error(f"File I/O error saving metadata {metadata_file}: {e}")
                raise OSError(f"Cannot save metadata file: {e}")
            except (TypeError, ValueError) as e:
                logging.error(f"JSON serialization error: {e}")
                raise ValueError(f"Cannot serialize metadata to JSON: {e}")

            # 로그 작성 (실패해도 치명적이지 않음)
            try:
                self.append_log(dir_path.name, f"Metadata saved: {metadata_file.name}")
            except Exception as e:
                logging.warning(f"Failed to write metadata save log: {e}")

            return metadata_file

        except (ValueError, OSError):
            # 이미 처리된 예외는 재발생
            raise
        except Exception as e:
            logging.error(f"Unexpected error saving metadata for {date_str}: {e}")
            raise OSError(f"Unexpected error saving metadata: {e}")

    def save_ai_request(self, date_str: str, data: Dict[str, Any]) -> Path:
        """
        AI 요청 데이터 저장

        Args:
            date_str: 날짜 문자열
            data: AI 요청 데이터

        Returns:
            저장된 파일 경로
        """
        dir_path = self.get_directory_path(date_str)
        if not dir_path:
            raise FileNotFoundError(f"Directory not found for date: {date_str}")

        ai_request_file = dir_path / "ai_request.json"

        # AI 요청 데이터에 타임스탬프 추가
        enhanced_data = {
            "request_timestamp": datetime.now().isoformat(),
            "date_directory": dir_path.name,
            **data
        }

        with open(ai_request_file, 'w', encoding='utf-8') as f:
            json.dump(enhanced_data, f, ensure_ascii=False, indent=2, default=str)

        self.append_log(dir_path.name, f"AI request data saved: {ai_request_file.name}")
        return ai_request_file

    def save_blog_result(self, date_str: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Path:
        """
        AI 생성 블로그 결과 저장 (마크다운 형식)

        Args:
            date_str: 날짜 문자열
            content: 블로그 글 내용
            metadata: 추가 메타데이터

        Returns:
            저장된 파일 경로
        """
        dir_path = self.get_directory_path(date_str)
        if not dir_path:
            raise FileNotFoundError(f"Directory not found for date: {date_str}")

        blog_file = dir_path / "blog_result.md"

        # 마크다운 헤더 추가
        header = f"""---
generated_at: {datetime.now().isoformat()}
date_directory: {dir_path.name}
"""

        if metadata:
            for key, value in metadata.items():
                header += f"{key}: {value}\n"

        header += "---\n\n"

        # 콘텐츠와 함께 저장
        full_content = header + content

        with open(blog_file, 'w', encoding='utf-8') as f:
            f.write(full_content)

        self.append_log(dir_path.name, f"Blog result saved: {blog_file.name} ({len(content)} chars)")
        return blog_file

    def append_log(self, date_str: str, message: str, level: str = "INFO"):
        """
        로그 파일에 메시지 추가 (예외처리 강화)

        Args:
            date_str: 날짜 문자열 또는 디렉토리명
            message: 로그 메시지
            level: 로그 레벨 (INFO, ERROR, WARNING 등)
        """
        try:
            # 입력 검증
            if not message:
                return  # 빈 메시지는 무시

            # 로그 파일 경로 결정
            try:
                dir_path = self.get_directory_path(date_str)
                if not dir_path:
                    # 디렉토리가 없으면 베이스 디렉토리에 임시 로그 생성
                    log_file = self.base_dir / f"temp_{date_str}.log"
                else:
                    log_file = dir_path / "log.txt"
            except Exception as e:
                logging.warning(f"Failed to determine log file path: {e}")
                # 최후의 수단으로 베이스 디렉토리에 생성
                log_file = self.base_dir / f"fallback_{date_str}.log"

            # 로그 엔트리 구성
            try:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                # 메시지에서 개행문자 제거하여 로그 형식 보존
                clean_message = message.replace('\n', ' ').replace('\r', '')
                log_entry = f"[{timestamp}] {level}: {clean_message}\n"
            except Exception as e:
                logging.warning(f"Failed to format log entry: {e}")
                log_entry = f"[ERROR] Failed to format log: {e}\n"

            # 파일에 로그 작성
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(log_entry)
            except PermissionError as e:
                logging.warning(f"Permission denied writing log {log_file}: {e}")
                # 권한 문제는 로깅 실패로 처리하지 않고 무시
            except (OSError, IOError) as e:
                logging.warning(f"File I/O error writing log {log_file}: {e}")
                # I/O 오류도 치명적이지 않으므로 무시
            except UnicodeEncodeError as e:
                logging.warning(f"Encoding error writing log: {e}")
                # 인코딩 문제로 재시도
                try:
                    with open(log_file, 'a', encoding='utf-8', errors='replace') as f:
                        f.write(f"[{timestamp}] {level}: [ENCODING ERROR] {repr(message)}\n")
                except:
                    pass  # 최종 실패해도 무시

        except Exception as e:
            # 로그 작성 실패는 치명적이지 않으므로 로깅만 하고 넘어감
            logging.warning(f"Failed to append log for {date_str}: {e}")

    def load_metadata(self, date_str: str) -> Optional[Dict[str, Any]]:
        """
        메타데이터 로드 (예외처리 강화)

        Args:
            date_str: 날짜 문자열

        Returns:
            메타데이터 딕셔너리 또는 None (파일 없음)

        Raises:
            OSError: 파일 읽기 실패
            ValueError: JSON 파싱 실패
        """
        try:
            # 디렉토리 경로 확인
            dir_path = self.get_directory_path(date_str)
            if not dir_path:
                logging.debug(f"Directory not found for {date_str}")
                return None

            metadata_file = dir_path / "metadata.json"
            if not metadata_file.exists():
                logging.debug(f"Metadata file not found: {metadata_file}")
                return None

            # 파일 읽기 및 JSON 파싱
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 데이터 타입 검증
                if not isinstance(data, dict):
                    logging.error(f"Invalid metadata format in {metadata_file}: not a dictionary")
                    raise ValueError(f"Metadata file contains invalid format: {metadata_file}")

                logging.debug(f"Metadata loaded successfully: {metadata_file}")
                return data

            except PermissionError as e:
                logging.error(f"Permission denied reading metadata {metadata_file}: {e}")
                raise OSError(f"Cannot read metadata: Permission denied")
            except (OSError, IOError) as e:
                logging.error(f"File I/O error reading metadata {metadata_file}: {e}")
                raise OSError(f"Cannot read metadata file: {e}")
            except json.JSONDecodeError as e:
                logging.error(f"JSON parsing error in {metadata_file}: {e}")
                raise ValueError(f"Invalid JSON in metadata file: {e}")
            except UnicodeDecodeError as e:
                logging.error(f"Encoding error reading {metadata_file}: {e}")
                raise ValueError(f"Cannot decode metadata file: {e}")

        except (OSError, ValueError):
            # 이미 처리된 예외는 재발생
            raise
        except Exception as e:
            logging.error(f"Unexpected error loading metadata for {date_str}: {e}")
            raise OSError(f"Unexpected error loading metadata: {e}")

    def load_ai_request(self, date_str: str) -> Optional[Dict[str, Any]]:
        """AI 요청 데이터 로드"""
        dir_path = self.get_directory_path(date_str)
        if not dir_path:
            return None

        ai_request_file = dir_path / "ai_request.json"
        if not ai_request_file.exists():
            return None

        with open(ai_request_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_blog_result(self, date_str: str) -> Optional[str]:
        """블로그 결과 로드"""
        dir_path = self.get_directory_path(date_str)
        if not dir_path:
            return None

        blog_file = dir_path / "blog_result.md"
        if not blog_file.exists():
            return None

        with open(blog_file, 'r', encoding='utf-8') as f:
            return f.read()

    def get_directory_info(self, date_str: str) -> Optional[Dict[str, Any]]:
        """디렉토리 정보 반환"""
        dir_path = self.get_directory_path(date_str)
        if not dir_path:
            return None

        # 이미지 저장 위치는 두 군데가 존재할 수 있습니다.
        # 1) 날짜 기반 세션 디렉토리: data/<date_dir>/images  (과거/테스트 또는 레거시)
        # 2) 업로드 전용 디렉토리: uploads/<date_dir>/images (웹/API 업로드 기본)
        #
        # "내가 업로드한 이미지만 사용" 정책 이후에는 (2)가 기본이며,
        # UI/세션 정보에서 이미지 개수도 (2)를 우선 반영해야 합니다.
        images_dir = dir_path / "images"
        session_name = dir_path.name
        uploads_images_dir = Settings.UPLOADS_DIR / session_name / "images"

        data_images = list(images_dir.glob("*")) if images_dir.exists() else []
        uploads_images = list(uploads_images_dir.glob("*")) if uploads_images_dir.exists() else []

        # 중복 제거(파일명 기준) 후 개수
        images_count = len({p.name for p in (data_images + uploads_images)})

        return {
            "directory_name": dir_path.name,
            "directory_path": str(dir_path),
            "images_count": images_count,
            "uploads_images_count": len({p.name for p in uploads_images}),
            "data_images_count": len({p.name for p in data_images}),
            "has_metadata": (dir_path / "metadata.json").exists(),
            "has_ai_request": (dir_path / "ai_request.json").exists(),
            "has_blog_result": (dir_path / "blog_result.md").exists(),
            "has_log": (dir_path / "log.txt").exists(),
            "created_date": datetime.fromtimestamp(dir_path.stat().st_ctime).isoformat()
        }

    def list_date_directories(self) -> List[str]:
        """모든 날짜 디렉토리 목록 반환 (상호명 포함 형식 지원)"""
        # 기존 형식: yyyyMMdd, yyyyMMdd_N
        # 새 형식: yyyyMMdd(상호명), yyyyMMdd(상호명)_N
        # 과거 형식: yyyyMMdd_N(상호명)
        patterns = [
            r'^\d{8}(_\d+)?$',                    # 기존 형식
            r'^\d{8}\([^)]+\)(?:_\d+)?$',         # 새 형식
            r'^\d{8}_\d+\([^)]+\)$'               # 과거 형식
        ]
        directories = []

        for path in self.base_dir.iterdir():
            if path.is_dir():
                for pattern in patterns:
                    if re.match(pattern, path.name):
                        directories.append(path.name)
                        break

        return sorted(directories)

    def cleanup_empty_directories(self) -> List[str]:
        """빈 디렉토리 정리 및 제거된 디렉토리 목록 반환"""
        removed = []

        for dir_name in self.list_date_directories():
            dir_path = self.base_dir / dir_name

            # 이미지 디렉토리가 비어있고, 다른 중요 파일들이 없으면 제거
            images_dir = dir_path / "images"
            important_files = ["metadata.json", "ai_request.json", "blog_result.md"]

            has_images = images_dir.exists() and any(images_dir.iterdir())
            has_important_files = any((dir_path / f).exists() for f in important_files)

            if not has_images and not has_important_files:
                # 로그 파일만 있는 경우에도 제거
                try:
                    if (dir_path / "log.txt").exists():
                        (dir_path / "log.txt").unlink()
                    if images_dir.exists():
                        images_dir.rmdir()
                    dir_path.rmdir()
                    removed.append(dir_name)
                except OSError:
                    pass  # 제거할 수 없으면 그대로 두기

        return removed


# 전역 인스턴스
date_manager = DateBasedDirectoryManager()
