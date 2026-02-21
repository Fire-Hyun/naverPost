# 중복 삽입 Troubleshooting

## 증상
- 임시저장 글에서 텍스트/이미지가 2회 이상 삽입됨
- 같은 입력인데 `blog_result.md` 내용이 런마다 달라짐

## RCA (Root Cause Analysis)
- 동일 `job_key` 작업이 중복 실행되면 같은 draft에 2회 삽입될 수 있음
- 재시도 과정에서 생성 단계가 다시 실행되면 `blog_result.md`가 덮어써져 같은 job의 본문 해시가 달라질 수 있음
- 에디터가 비어있지 않은 상태에서 재진입하면 기존 내용 위에 추가 삽입될 수 있음

## 적용된 방어 장치
- `run_id`: 각 런 시작 시 생성, `blog_result.md` 상단 `<!-- RUN_ID: ... -->` 주석 삽입
- `job_key lock`: `.secrets/idempotency/locks/*.lock` 원자 생성, 중복 실행 시 `DUP_RUN_DETECTED`
- `draft_guard`: 삽입 전 에디터 비어있음 검사, 기본 `abort` (`DRAFT_NOT_EMPTY_ABORT`)
- `retry consistency`: 재시도(`NAVER_RETRY_ATTEMPT>0`)에서 `run_id/content_hash` 불일치 시 `RUN_ID_MISMATCH_RETRY_BLOCKED`

## 운영 추적 방법
- 로그에서 아래 필드를 확인:
  - `run_id`
  - `job_key`
  - `blog_result_path`
  - `content_hash`
  - `content_length`
  - `image_count`
- 삽입 전/후 로그 키:
  - `[trace] stage=before_insert ...`
  - `[trace] stage=after_insert ...`
- draft guard 로그 키:
  - `[draft-guard] stage=before_insert ...`
  - `[draft-guard] stage=after_reopen ...`

## 장애 대응
1. `reason_code`가 `DUP_RUN_DETECTED`면 동일 `job_key` 중복 실행 여부 확인
2. `reason_code`가 `DRAFT_NOT_EMPTY_ABORT`면 기존 draft 내용 정리 후 재실행 또는 `NAVER_DRAFT_GUARD_MODE=reset` 사용
3. `reason_code`가 `RUN_ID_MISMATCH_RETRY_BLOCKED`면 재시도 전에 생성 단계가 다시 호출되었는지 확인
