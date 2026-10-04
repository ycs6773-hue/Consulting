# CLAUDE.md — Consulting (CAE 해석 의뢰 수행 저장소)

## WHY / WHAT
- 고객 해석 의뢰(HFSS/SIwave)를 PyAEDT 자동화로 수행하고 보고서를 납품하는 저장소.
- 현재 의뢰: 2.4 GHz inset-fed 패치 안테나 HFSS 설계/해석/보고서 (`hfss_patch/`).
- 실제 솔버 실행은 라이선스가 있는 사용자 Windows PC에서만 가능 (클라우드 컨테이너에는 AEDT 없음).

## MUST / NEVER
- MUST: AEDT 세션은 try/finally에서 `release_desktop(close_projects=True, close_desktop=True)`로 해제.
- MUST: PyAEDT 호출의 False/None 반환은 `_require`로 예외 변환 (조용한 실패 금지).
- MUST: 기하/물리 검증(`config.validate`, `geometry.check_model`)은 AEDT 실행 전에 통과해야 함.
- MUST: 실행마다 로그 파일 + `run_summary.json`(config sha256 포함) 남김 — 재현성.
- MUST: PyAEDT API 시그니처는 추측하지 말고 소스(ansys/pyaedt)로 확인.
- MUST: 코드 변경 시 `python -m pytest -q` 통과 후 커밋.
- NEVER: 고객 메일 발송/회신은 사용자 승인 없이 하지 않음.
- NEVER: 고객 데이터·결과를 저장소 외부 서비스로 전송하지 않음.
- NEVER: `results/`(해석 산출물, .aedt)를 커밋하지 않음.

## 파일 참조
- 해석 계획/질문 리스트: docs/plan.md
- 현재 Phase/실행 방법: docs/current_context.md
- 교훈/주의사항: docs/claude_lessons.md
- 설정: hfss_patch/configs/*.yaml / 실행: `python -m hfss_patch.run --config ...`

## Core Principles
- 설정(YAML) → 순수 Python 기하 정의 → PyAEDT 실행부 분리 (AEDT 없이 테스트 가능).
- 모든 치수는 AEDT 설계 변수 표현식 → Optimetrics 스윕 시 형상 자동 재생성.
