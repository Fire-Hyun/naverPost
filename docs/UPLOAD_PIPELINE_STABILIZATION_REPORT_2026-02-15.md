# 임시저장 판정 오류 + 이미지 누락 안정화 보고서 (2026-02-15)

## 1) 변경 파일 목록
- `src/services/blog_workflow.py`
- `src/telegram/service_layer.py`
- `src/utils/image_processor.py`
- `naver-poster/src/naver/editor.ts`
- `naver-poster/src/cli/post_to_naver.ts`
- `naver-poster/tests/integration/test_naver_draft_save.ts`
- `naver-poster/tests/integration/smoke_test_post_draft_with_images.ts`
- `naver-poster/scripts/test_draft_save.sh`
- `naver-poster/scripts/smoke_test_post_draft_with_images.sh`
- `naver-poster/package.json`
- `scripts/test_naver_upload_pipeline_state.py`

## 2) 핵심 수정 요약
- 업로드 파이프라인을 Step A~G 상태머신으로 분해하고 JSON 결과(`NAVER_POST_RESULT_JSON`)를 출력.
- 임시저장 성공(`draft_summary.success`)과 이미지 포함 성공(`image_summary.status`)을 분리 판정.
- 이미지 업로드를 bool에서 상세 결과 구조로 확장:
  - 파일 단위 메타(파일명/확장자/MIME/bytes)
  - 시도별 네트워크 trace(status/elapsed)
  - 지수 백오프 + 지터 재시도
  - 사후 이미지 참조 검증(Step G)
- Python 업로드 판정을 문자열 기반에서 JSON 리포트 기반으로 전환.
- 인증 오류는 1회 `--autoLogin` 후 재시도, transient 오류는 자동 재시도.
- 텔레그램 사용자 알림을 성공/경고/실패 3단계로 분리.

## 3) 원인 결론 (로그 증거 기반)
### 결론 A: "임시저장 성공인데 실패로 알림"은 판정 모델 결함
- 기존: 문자열/종료코드 중심 판정.
- 수정 후: `draft_summary.success`(임시저장) + `image_summary.status`(이미지 포함)를 독립 판정.

### 결론 B: "텍스트만 저장되고 이미지 누락"은 다중 선택 업로드 경로에서 재현됨
- 실측 5장 시나리오에서:
  - Step F: `success` (임시저장 검증 통과)
  - Step C/D/E/G: 실패
  - 최종: `overall_status=SUCCESS_TEXT_ONLY`, `image_status=none`
- 즉, 임시저장 자체는 성공하지만 이미지 리소스가 본문에 남지 않는 부분성공 케이스가 실제 존재.

### 결론 C: 단일 이미지는 정상 성공 가능
- 실측 1장 시나리오:
  - Step C/D/E/G 모두 성공
  - 최종: `overall_status=SUCCESS_FULL`, `image_status=full`

### 결론 D: 다중 실패는 "중복 파일" 문제가 아님
- 서로 다른 5장(`unique_1..5.jpg`)으로 재실행해도 동일하게:
  - Step C: `uploaded_count=0`
  - 최종: `overall_status=SUCCESS_TEXT_ONLY`
- 즉, 멀티 선택 업로드 경로(UI 이벤트 체인) 자체 문제로 판단.

### 결론 E: 다중 선택 대신 "단건 순차 업로드"로 안정화 가능
- 전략 전환:
  - 다중 이미지 요청 시 각 이미지를 1장씩 순차 업로드
  - 각 장마다 업로드 성공/네트워크 trace/에디터 참조를 검증
- 실측 결과:
  - 5장(중복): `overall_status=SUCCESS_FULL`, `uploaded_count=5`, `image_status=full`
  - 5장(서로 다른 이미지): `overall_status=SUCCESS_FULL`, `uploaded_count=5`, `image_status=full`

## 4) 재현 절차
1. 1장/5장 테스트 디렉토리 준비.
2. 스모크 실행:
   - `bash naver-poster/scripts/smoke_test_post_draft_with_images.sh <dir1> <dir5>`
3. 로그에서 `NAVER_POST_RESULT_JSON:` 라인 확인.
4. `overall_status`, `steps.C`, `steps.F`, `steps.G` 비교.

## 5) 수정 후 검증 결과
### 타입/단위 검증
- `cd naver-poster && npx tsc --noEmit` 통과
- `LOG_FILE=/tmp/naverpost.log PYTHONPATH=. pytest -q scripts/test_naver_upload_pipeline_state.py -o cache_dir=/tmp/pytest_cache`
  - 결과: `3 passed`

### 실측 스모크(권한상승 환경)
- `single-image-draft`: `SUCCESS_FULL` / `image=full`
- `five-images-draft` (초기 다중 선택): `SUCCESS_TEXT_ONLY` / `image=none`
- `simulated-upload-timeout`: `SUCCESS_TEXT_ONLY` / `image=none`
- `parallel-multi-image-order` (초기 다중 선택): `SUCCESS_TEXT_ONLY` / `image=none`
- `five-images-unique` (초기 다중 선택): `SUCCESS_TEXT_ONLY` / `image=none` (중복 아님 검증)
- `five-images-draft` (단건 순차 업로드 적용 후): `SUCCESS_FULL` / `image=full`
- `five-images-unique` (단건 순차 업로드 적용 후): `SUCCESS_FULL` / `image=full`
- `simulated-upload-timeout` (수정 후): `SUCCESS_TEXT_ONLY` / `image=none` (의도된 경고 경로 유지)

### 증거 포인트
- 1장 성공 케이스 Step C에 업로드 API 200 trace 존재.
- 5장 실패 케이스 Step C에 실제 이미지 업로드 trace 부재 + `editor_image_count=0`.

## 6) 운영 가이드
### 실패/재시도 정책
- transient(네트워크/timeout/429/5xx): 재시도(지수 백오프 + 지터)
- auth 오류: `--autoLogin` 1회 후 재시도
- 포맷/권한 4xx 성격: 즉시 실패 분류

### 알림 정책
- `SUCCESS_FULL`: 임시저장+이미지 포함 성공
- `SUCCESS_PARTIAL_IMAGES`: 임시저장 성공, 이미지 일부 누락
- `SUCCESS_TEXT_ONLY`: 임시저장 성공, 이미지 전체 누락
- `FAILED`: 임시저장 실패

### 모니터링 포인트
- `steps.C.status`, `steps.C.data.attempts[].network_traces`
- `steps.G.status`, `steps.G.data.image_count`
- `image_summary.requested/uploaded/missing`
- `overall_status` 분포 변화

## 7) 텔레그램 사용자 메시지 포맷
- 성공:
  - `✅ 네이버 임시저장: 성공 (이미지 포함)`
- 경고:
  - `⚠️ 네이버 임시저장: 성공 (텍스트 저장, 이미지 누락 N장)`
  - `• 이미지 상태: X/Y장 포함`
- 실패:
  - `❌ 네이버 임시저장: 실패`
  - `• 원인: ...`
