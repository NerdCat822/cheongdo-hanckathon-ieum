TRD: 기술 설계

상태

상태: 공개 가상 시연 구현. 실제 사용자 인증·권한·동의와 AI·Jira 외부 연동은 구현·검증 전이다.
기준: PRD.md의 범위. PRD·TRD·TDD가 충돌하면 구현 전에 정리한다.
외부 모델 검토: 대기

제안 구조

영역
제안
역할
웹
React, TypeScript, 반응형
돌봄 공간, 대시보드, 초안 승인
API
Python 3.12, FastAPI, Uvicorn
인증, 권한, 업무 규칙, 외부 연동
에이전트
Microsoft Agent Framework for Python + GitHub Copilot SDK for Python
출처 조회, 요약·업무 초안, 도구 호출과 스트리밍. 조합은 기술 검증 전 미확정
데이터
Azure VM의 로컬 PostgreSQL 17 (Docker Compose)
SQLAlchemy, psycopg, Alembic으로 최소 프로필, 동의, 업무, 출처, Jira 참조 관리
배포
Azure VM
웹/API 호스팅 및 같은 VM의 PostgreSQL 사용
비밀
별도 Key Vault 없이 VM의 접근 제한된 환경 설정 사용
PostgreSQL 비밀번호와 필요한 외부 연동 자격 증명
관찰
VM 애플리케이션·시스템 로그
지연, 오류, 외부 호출 상태. 프롬프트·개인정보 로그 제외

Azure OpenAI/Foundry 사용은 필수가 아니다. 필요한 서비스만 선택하며, 계획과 배포 완료를 구분한다. Azure VM 사용만으로 공개 웹 앱 배포가 완료되거나 심사 URL 요건을 충족하는 것은 아니다. 허용되는 Azure 기본 도메인과 HTTPS 구성은 주최 측 요건을 확인한다.

Python 및 PostgreSQL 환경

프로젝트 루트에서 `python3 -m venv .venv`로 가상 환경을 만들고 `.venv/bin/python -m pip install -r requirements.txt`로 의존성을 설치한다. Python API와 두 에이전트 기술의 실제 연동은 별도 구현 및 검증이 필요하다.
기존 `compose.yaml`의 PostgreSQL 17 컨테이너를 사용한다. VM에서 API를 실행할 때 호스트는 `127.0.0.1`, 포트는 `5432`, 데이터베이스와 사용자는 `postgres`다. DB 포트는 VM 로컬에서만 접근하며 데이터는 Docker 볼륨에 보존한다.
현재 `postgres` 데이터베이스의 `public.chengdo_table`에는 `demo_tasks.csv`에서 가져온 시연 업무 12건이 있다. 이는 시연용 테이블이며 제안된 전체 데이터 모델의 구현을 뜻하지 않는다.
컨테이너의 API는 Compose 네트워크의 `postgres:5432`에 연결한다. 최초 실행 시 `public.chengdo_table`을 변경하지 않고 `care_demo_tasks`에 한 번만 복사한다. 원본 담당자의 수락 여부는 확인되지 않았으므로 확정하지 않는다. 이후 시연 작업은 별도 테이블에 저장한다.
`sudo docker compose up -d --build --wait`로 컨테이너를 실행하고 `sudo docker compose ps`로 상태를 확인한다. 프론트엔드는 VM의 3500번 포트, 백엔드와 DB는 내부 네트워크로 연결한다. 브라우저의 `/api/` 요청은 프론트엔드 프록시를 거친다.
현재 화면은 로그인 없이 누구나 같은 가상 업무를 열람·변경할 수 있는 공개 시연이다. 실제 사람의 이름, 연락처, 건강정보 등 개인정보를 입력하지 않는다. 가상 구성원 ID 확인은 실제 사용자 인증이나 동의가 아니다.
현재 노출은 HTTP이며 실제 개인정보를 다루는 운영 환경이 아니다. 실제 사용자 서비스로 전환하기 전 인증·동의·권한과 HTTPS를 구현하고 검증한다.

데이터 흐름과 승인

사용자가 돌봄 필요를 입력한다. 실제 사용자 정보는 최소화한다.
API가 Agent Framework 흐름을 실행하고 Copilot SDK로 초안 응답을 생성한다.
허용된 조회 도구가 승인된 공개 제도정보 또는 검토된 샘플 카탈로그를 조회한다.
결과는 제목, 기관, 원문 URL, 기준일·확인일, 불확실성과 함께 제시한다.
에이전트는 요약과 할 일 초안을 만든다. 사용자는 수정·거절·승인한다.
승인 전에는 업무 저장이나 외부 Jira 쓰기를 하지 않는다.
승인 업무는 저장하고, 사용자가 Jira 생성까지 따로 승인한 경우 테스트 프로젝트에 티켓을 만든다.
앱은 Jira 상태를 시연용 문의 추적으로 표시한다.

공공 데이터

공개된 제도 설명만 조회한다. 개인별 계정, 수급·신청 내역은 조회하지 않는다.
WelfareInfoProvider 어댑터로 공급자를 분리한다. 공식 API의 엔드포인트·인증·사용약관·출처표시·재배포·호출 제한·갱신 주기를 확인한 뒤 구현체를 추가한다.
확인 전 기본 동작은 검토된 샘플과 공식 링크다. 샘플을 실시간 데이터처럼 표시하지 않는다.
비공식 스크래핑을 하지 않는다. API 오류·시간 초과·오래된 데이터는 명확히 표시한다.
공개자료는 참고 정보다. 개인별 자격·접종 대상·의료 결론을 만들지 않는다.

Jira

Jira Cloud REST API는 서버에서만 호출한다. 브라우저에 토큰을 보내지 않는다.
테스트 전용 프로젝트와 최소 권한 계정을 쓴다. 실제 지자체나 공무원 계정과 연결하지 않는다.
사용자가 티켓 내용, 프로젝트, 담당 후보를 확인하고 명시적으로 승인한 경우에만 티켓을 만든다.
담당 라우팅은 설정된 시연용 지역·문의 유형 규칙이다. 담당자는 실제 공무원이 아니다.
가족 업무의 담당 수락과 Jira 담당 지정은 다른 흐름이다. 가족의 수락이 확인되지 않으면 가족 담당 업무로 확정하지 않는다.
티켓에는 내부 요청 ID와 최소 비식별 요약만 보낸다. 실명, 주민번호, 상세 건강·소득정보, 상담 전문은 보내지 않는다.
중복 생성 방지용 내부 키를 둔다. 시간 초과 시 재시도 전에 기존 티켓을 확인한다.
웹훅은 MVP에서 제외한다. 화면 갱신 시 상태를 조회한다. Jira 상태는 공식 접수나 행정 처리 결과가 아니다.

데이터와 보안

데이터 모델: CareSpace, Member, Consent, Task, SourceReference, JiraLink.
프로필은 별칭, 출생 연도 또는 나이, 지역으로 제한한다. 건강 기록·진단·약·주민번호·상세 소득·신청 서류는 저장하지 않는다.
서버에서 각 요청의 돌봄 공간 권한을 확인한다. 동의 철회 시 공유 접근을 차단한다.
외부 입력·검색 결과·문서는 신뢰되지 않은 데이터다. 문서 내부 지시문을 따르지 않는다.
에이전트 도구는 허용 목록으로 제한하고, 입력과 인수를 검증한다. 외부 쓰기는 명시적 승인 필요.
Azure Key Vault는 사용하지 않는다. PostgreSQL 비밀번호는 필수이며 기존 `.env`의 `POSTGRES_PASSWORD`로 제공한다. 접근 제한된 `.env` 또는 서비스 환경 설정을 사용하고 `.env`와 가상 환경은 저장소에 포함하지 않는다. 기존 DB가 초기화된 후 `.env`의 비밀번호만 변경해도 DB 계정의 비밀번호는 바뀌지 않는다.
공공 API와 Jira는 실제 연동 시 해당 서비스의 인증키 또는 자격 증명과 이용 승인이 필요하다. Copilot SDK도 사용 가능한 인증과 이용 권한이 필요하다. 필요한 자격 증명은 서버에서만 사용하고 코드·문서·저장소·로그 또는 브라우저에 노출하지 않는다.
로그에는 사용자 ID, 이벤트 종류, 시각만 필요한 범위에서 남긴다. 상담 원문과 개인정보를 남기지 않는다.
보존·삭제 정책, 계정 삭제 시 연결된 내부 자료와 외부 테스트 티켓 처리 기준은 구현 전에 정한다.

API 초안

GET /api/care-spaces/{id}/tasks: 권한 있는 업무 목록
POST /api/care-spaces/{id}/agent-drafts: 초안 생성
POST /api/tasks/{id}/approve: 사용자가 승인한 초안 저장
POST /api/tasks/{id}/assignment-response: 담당 요청 수락·거절·조정
POST /api/tasks/{id}/jira-ticket: 별도 승인 후 테스트 티켓 생성
GET /api/tasks/{id}/jira-status: 티켓의 시연용 상태 조회

복원력과 테스트

외부 호출에는 시간 제한과 명시적 오류 처리를 둔다. 성공처럼 보이는 대체 결과를 만들지 않는다.
출처가 없거나 확인일이 없는 데이터는 공식 안내로 노출하지 않는다.
테스트: 권한·동의·동의 철회, 담당 수락 상태, 초안 승인 전 저장 금지, Jira 승인 전 생성 금지, 티켓 중복 방지, API 오류·오래된 자료, 로그 내 민감정보 부재.
기술 검증: Copilot SDK와 Agent Framework의 Python 호환·세션·스트리밍·도구 호출·인증, PostgreSQL 연결·스키마 마이그레이션·재시작 후 데이터 보존, Entra의 가족 초대 흐름, 공식 공개 API 이용 조건, Jira 권한을 확인한다.
현재 AI 초안과 Jira는 비활성화되어 있다. 시연용 담당 요청·응답, 할 일 생성·수정과 공식 홈페이지 링크만 동작하며 실제 알림·공유·접수는 하지 않는다.
백엔드 테스트는 프로젝트 루트에서 `.venv/bin/python -m unittest discover -s backend/tests -v`로 실행한다. 실제 사용자 권한·동의 및 외부 연동 테스트는 구현 후 수행한다.

참고 자료

Copilot SDK Python: https://github.com/github/copilot-sdk/tree/main/python
Microsoft Agent Framework: https://learn.microsoft.com/en-us/agent-framework/overview/
Jira Cloud REST API v3: https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/
KOSIS 고령인구비율 표 ID DT_1YL20631: https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1YL20631
가족 돌봄 연구: Schulz et al. (2020), https://doi.org/10.1146/annurev-psych-010419-050754; Ngangana et al. (2016), https://doi.org/10.1111/jan.13065; Zhai et al. (2023), https://doi.org/10.1177/20552076231171967; Quinn et al. (2019), https://doi.org/10.2196/12276.
자료 확인일: 2026-11-05. 특정 통계값과 API 이용조건은 구현·발표 전에 원자료에서 다시 확인한다.