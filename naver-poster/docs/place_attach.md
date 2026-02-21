# 장소첨부 성공 판정 기준

장소첨부 단계는 아래 신호 중 최소 1개를 만족해야 성공으로 처리한다.

- 장소 카드 DOM이 baseline 대비 증가한다.
- 또는 장소 카드/블록 텍스트에 선택한 장소명의 핵심 토큰이 포함된다.

실패 시 `reason_code`를 남긴다.

- `PLACE_UI_NOT_FOUND`: 장소 버튼/패널/검색 입력 UI를 찾지 못함
- `PLACE_SEARCH_NO_RESULT`: 검색 결과가 0건
- `PLACE_SEARCH_SELECT_FAILED`: 검색 결과 선택 실패
- `PLACE_CONFIRM_NEVER_ENABLED`: 선택 후 추가/확인 버튼이 활성화되지 않음
- `PLACE_ATTACH_NOT_APPLIED`: 결과 클릭 후에도 카드 반영 검증 실패
- `PLACE_AUTH_OR_RATE_LIMIT`: API 응답 401/403/429 감지
- `PLACE_NETWORK_TIMEOUT`: 검색 응답/결과 DOM이 제한시간 내 미도착

디버그 아티팩트는 `/tmp/naver_editor_debug/<ts>_place_attach_fail/` 에 저장된다.

`place_debug.json` 추적 필드:

- `addButtonFound`
- `addButtonEnabledBeforeClick`
- `addButtonClicked`
- `addButtonClickError`
- `attachSignalsObserved.panelClosed`
- `attachSignalsObserved.toast`
- `attachSignalsObserved.response2xx`
- `attachSignalsObserved.domInserted`
