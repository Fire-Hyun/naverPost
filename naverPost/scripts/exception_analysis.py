#!/usr/bin/env python3
"""
예외처리 분석 스크립트

핵심 모듈들의 예외처리 상태를 분석하고 개선이 필요한 부분을 식별합니다.
"""

import ast
import re
from pathlib import Path
from typing import Dict, List, Tuple
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ExceptionAnalyzer:
    """예외처리 분석 클래스"""

    def __init__(self):
        self.risky_operations = {
            # 파일 I/O 작업
            "file_io": [
                "open(", ".read(", ".write(", ".unlink(", ".mkdir(",
                ".rmdir(", "shutil.rmtree(", "shutil.move(", "shutil.copy("
            ],
            # 네트워크/API 작업
            "network": [
                ".create(", "requests.", "openai.", "client.", ".api"
            ],
            # JSON/데이터 처리
            "data": [
                "json.load(", "json.loads(", "json.dump(", "json.dumps(",
                ".save(", ".load("
            ],
            # 디렉토리 작업
            "directory": [
                ".iterdir(", ".glob(", ".exists(", ".stat(", "Path("
            ]
        }

        self.critical_functions = [
            "save_uploaded_images", "generate_blog_post", "create_date_directory",
            "save_metadata", "load_metadata", "save_blog_result"
        ]

    def analyze_file(self, file_path: Path) -> Dict:
        """단일 파일의 예외처리 분석"""
        analysis = {
            "file": str(file_path),
            "total_lines": 0,
            "try_blocks": 0,
            "risky_operations": [],
            "unprotected_operations": [],
            "critical_functions": [],
            "recommendations": []
        }

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()

            analysis["total_lines"] = len(lines)

            # Try 블록 개수 계산
            analysis["try_blocks"] = content.count("try:")

            # AST 파싱으로 상세 분석
            try:
                tree = ast.parse(content)
                analysis.update(self._analyze_ast(tree, content))
            except SyntaxError as e:
                logger.warning(f"AST 파싱 실패 {file_path}: {e}")

            # 위험한 작업 식별
            for category, operations in self.risky_operations.items():
                for op in operations:
                    if op in content:
                        analysis["risky_operations"].append((category, op))

            # 보호되지 않은 작업 찾기
            analysis["unprotected_operations"] = self._find_unprotected_operations(content)

            # 중요 함수 식별
            for func in self.critical_functions:
                if f"def {func}" in content:
                    analysis["critical_functions"].append(func)

            # 추천사항 생성
            analysis["recommendations"] = self._generate_recommendations(analysis)

        except Exception as e:
            logger.error(f"파일 분석 실패 {file_path}: {e}")

        return analysis

    def _analyze_ast(self, tree: ast.AST, content: str) -> Dict:
        """AST를 이용한 상세 분석"""
        details = {
            "functions_count": 0,
            "classes_count": 0,
            "try_except_coverage": []
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                details["functions_count"] += 1
            elif isinstance(node, ast.ClassDef):
                details["classes_count"] += 1
            elif isinstance(node, ast.Try):
                # Try 블록의 예외 타입 분석
                exception_types = []
                for handler in node.handlers:
                    if handler.type:
                        if isinstance(handler.type, ast.Name):
                            exception_types.append(handler.type.id)
                        elif isinstance(handler.type, ast.Tuple):
                            for exc in handler.type.elts:
                                if isinstance(exc, ast.Name):
                                    exception_types.append(exc.id)
                details["try_except_coverage"].append(exception_types)

        return details

    def _find_unprotected_operations(self, content: str) -> List[str]:
        """보호되지 않은 위험 작업 찾기"""
        unprotected = []
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()

            # 위험한 작업이 있는지 확인
            for category, operations in self.risky_operations.items():
                for op in operations:
                    if op in line_stripped:
                        # try 블록 안에 있는지 확인 (간단한 휴리스틱)
                        if not self._is_in_try_block(lines, i-1):
                            unprotected.append(f"Line {i}: {line_stripped[:50]}...")
                            break

        return unprotected[:10]  # 최대 10개만

    def _is_in_try_block(self, lines: List[str], line_idx: int) -> bool:
        """해당 라인이 try 블록 안에 있는지 간단히 확인"""
        # 역순으로 탐색하여 try: 찾기
        indent_level = len(lines[line_idx]) - len(lines[line_idx].lstrip())

        for i in range(line_idx, -1, -1):
            line = lines[i].strip()
            current_indent = len(lines[i]) - len(lines[i].lstrip())

            if line.startswith("try:") and current_indent < indent_level:
                return True
            elif line.startswith(("def ", "class ", "if ", "for ", "while ")) and current_indent < indent_level:
                return False

        return False

    def _generate_recommendations(self, analysis: Dict) -> List[str]:
        """분석 결과를 기반으로 추천사항 생성"""
        recommendations = []

        # Try 블록 비율 확인
        if analysis["try_blocks"] < analysis["functions_count"] * 0.5:
            recommendations.append("함수별 예외처리 비율이 낮습니다. 핵심 함수에 try-except 추가를 권장합니다.")

        # 보호되지 않은 작업
        if analysis["unprotected_operations"]:
            recommendations.append(f"{len(analysis['unprotected_operations'])}개의 보호되지 않은 위험 작업이 발견되었습니다.")

        # 중요 함수 예외처리 확인
        if analysis["critical_functions"]:
            recommendations.append("중요 함수들의 예외처리를 강화하세요.")

        # 파일 I/O 작업 많은 경우
        file_io_count = len([op for cat, op in analysis["risky_operations"] if cat == "file_io"])
        if file_io_count > 5:
            recommendations.append("파일 I/O 작업이 많습니다. 모든 파일 작업에 예외처리를 적용하세요.")

        return recommendations

    def analyze_project(self, src_dir: str = "src") -> Dict:
        """전체 프로젝트 분석"""
        logger.info(f"🔍 프로젝트 예외처리 분석 시작: {src_dir}")

        src_path = Path(src_dir)
        if not src_path.exists():
            logger.error(f"소스 디렉토리 없음: {src_path}")
            return {}

        # 핵심 모듈들 분석
        critical_files = [
            "storage/data_manager.py",
            "content/blog_generator.py",
            "web/routes/upload.py",
            "utils/date_manager.py",
            "utils/logger.py",
            "config/settings.py"
        ]

        results = {
            "summary": {
                "total_files": 0,
                "total_try_blocks": 0,
                "high_risk_files": [],
                "needs_improvement": []
            },
            "files": {}
        }

        for file_rel in critical_files:
            file_path = src_path / file_rel
            if file_path.exists():
                logger.info(f"분석 중: {file_rel}")
                analysis = self.analyze_file(file_path)
                results["files"][file_rel] = analysis

                results["summary"]["total_files"] += 1
                results["summary"]["total_try_blocks"] += analysis["try_blocks"]

                # 고위험 파일 식별
                risk_score = len(analysis["unprotected_operations"]) + len(analysis["risky_operations"]) - analysis["try_blocks"]
                if risk_score > 5:
                    results["summary"]["high_risk_files"].append(file_rel)

                # 개선 필요 파일
                if analysis["recommendations"]:
                    results["summary"]["needs_improvement"].append(file_rel)

        # 결과 요약 출력
        self._print_summary(results)

        return results

    def _print_summary(self, results: Dict):
        """분석 결과 요약 출력"""
        summary = results["summary"]

        logger.info(f"\n📊 예외처리 분석 완료")
        logger.info(f"   분석 파일: {summary['total_files']}개")
        logger.info(f"   총 try 블록: {summary['total_try_blocks']}개")

        if summary["high_risk_files"]:
            logger.warning(f"🚨 고위험 파일: {len(summary['high_risk_files'])}개")
            for file in summary["high_risk_files"]:
                logger.warning(f"   - {file}")

        if summary["needs_improvement"]:
            logger.info(f"🔧 개선 필요: {len(summary['needs_improvement'])}개")
            for file in summary["needs_improvement"]:
                logger.info(f"   - {file}")

        # 각 파일별 상세 정보
        logger.info(f"\n📋 파일별 상세 분석:")
        for file_rel, analysis in results["files"].items():
            logger.info(f"\n{file_rel}:")
            logger.info(f"   라인수: {analysis['total_lines']}, try블록: {analysis['try_blocks']}")
            logger.info(f"   위험작업: {len(analysis['risky_operations'])}, 미보호작업: {len(analysis['unprotected_operations'])}")

            if analysis["recommendations"]:
                logger.info(f"   추천사항:")
                for rec in analysis["recommendations"]:
                    logger.info(f"     - {rec}")

def main():
    """메인 실행 함수"""
    analyzer = ExceptionAnalyzer()
    results = analyzer.analyze_project()

    print("\n" + "="*60)
    print("🔍 예외처리 분석 완료")
    print(f"Phase 3에서 개선할 파일들: {len(results['summary']['needs_improvement'])}개")
    print("="*60)

if __name__ == "__main__":
    main()