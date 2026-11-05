TRD: 기술 설계

상태

상태: 공개 가상 시연. Microsoft Agent Framework와 GitHub Copilot SDK를 사용해 실제 초안을 생성하고 사용자가 검토 후 저장한다. 실제 사용자 인증·권한·동의는 구현 전이며 Jira 대신 자체 업무 보드를 사용한다.
배포: Azure Container Apps HTTPS 게이트웨이가 Azure VM의 Docker Compose 웹/API와 로컬 PostgreSQL로 연결된다. VM이 중지되면 서비스도 중지된다.
공공 API: 병원 검색·진료과목과 예방접종 목록·상세는 서버에서 공공데이터포털 인증키로 조회한다. 노인복지시설은 호출 조건을 확인하지 못해 미연결이다.
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
가상 업무 규칙, 외부 연동. 실제 사용자 인증·권한은 미구현
에이전트
Microsoft Agent Framework for Python + GitHub Copilot SDK for Python
승인된 홈페이지 조회 도구와 업무 초안. 스트리밍은 미구현
데이터
Azure VM의 로컬 PostgreSQL 17 (Docker Compose)
SQLAlchemy와 psycopg로 가상 업무, 변경 이력과 AI 사용량 관리
배포
Azure Container Apps HTTPS 게이트웨이와 Azure VM
게이트웨이가 VM의 웹/API에 전달하고, PostgreSQL은 같은 VM에서 실행
비밀
별도 Key Vault 없이 VM의 접근 제한된 환경 설정 사용
PostgreSQL 비밀번호와 필요한 외부 연동 자격 증명
관찰
VM 애플리케이션·시스템 로그
지연, 오류, 외부 호출 상태. 프롬프트·개인정보 로그 제외

Azure OpenAI/Foundry 사용은 필수가 아니다. 필요한 서비스만 선택하며, 계획과 배포 완료를 구분한다. Azure VM 사용만으로 공개 웹 앱 배포가 완료되거나 심사 URL 요건을 충족하는 것은 아니다. 허용되는 Azure 기본 도메인과 HTTPS 구성은 주최 측 요건을 확인한다.

Python 및 PostgreSQL 환경

프로젝트 루트에서 `python3 -m venv .venv`로 가상 환경을 만들고 `.venv/bin/python -m pip install -r requirements.txt`로 의존성을 설치한다. AI는 `CARE_AI_ENABLED=true`와 Copilot 사용 권한이 있는 `COPILOT_GITHUB_TOKEN`을 서버 환경에 설정해야 한다. 모델 API 키는 사용하지 않는다.
기존 `compose.yaml`의 PostgreSQL 17 컨테이너를 사용한다. VM에서 API를 실행할 때 호스트는 `127.0.0.1`, 포트는 `5432`, 데이터베이스와 사용자는 `postgres`다. DB 포트는 VM 로컬에서만 접근하며 데이터는 Docker 볼륨에 보존한다.
현재 `postgres` 데이터베이스의 `public.chengdo_table`에는 `demo_tasks.csv`에서 가져온 시연 업무 12건이 있다. 이는 시연용 테이블이며 제안된 전체 데이터 모델의 구현을 뜻하지 않는다.
컨테이너의 API는 Compose 네트워크의 `postgres:5432`에 연결한다. 최초 실행 시 `public.chengdo_table`을 변경하지 않고 `care_demo_tasks`에 한 번만 복사한다. 원본 담당자의 수락 여부는 확인되지 않았으므로 확정하지 않는다. 이후 시연 작업은 별도 테이블에 저장한다.
`sudo docker compose up -d --build --wait`로 컨테이너를 실행하고 `sudo docker compose ps`로 상태를 확인한다. 프론트엔드는 VM의 3500번 포트, 백엔드와 DB는 내부 네트워크로 연결한다. 브라우저의 `/api/` 요청은 프론트엔드 프록시를 거친다.
현재 화면은 로그인 없이 누구나 같은 가상 업무를 열람·변경할 수 있는 공개 시연이다. 실제 사람의 이름, 연락처, 건강정보 등 개인정보를 입력하지 않는다. 가상 구성원 ID 확인은 실제 사용자 인증이나 동의가 아니다.
공개 URL은 HTTPS이며 게이트웨이에서 VM까지는 HTTP다. 실제 개인정보를 다루는 운영 환경이 아니다. 실제 서비스 전환 전 인증·동의·권한과 전체 구간 암호화를 구현하고 검증한다.

데이터 흐름과 승인

사용자가 정해진 가상 분야를 선택하고 Copilot 전송에 동의한다. 자유 입력이나 실제 개인정보는 전송하지 않는다.
API가 Agent Framework 흐름을 실행하고 Copilot SDK로 초안 응답을 생성한다.
허용된 읽기 전용 도구가 공식 홈페이지 참고 링크를 조회한다. 예방접종 분야는 질병관리청 감염병 명칭 목록을 추가로 조회하고 출처·조회 시각을 표시한다. 홈페이지 링크 자체는 제도의 세부 내용을 검증하지 않는다.
결과는 제목, 기관, 원문 URL, 기준일·확인일, 불확실성과 함께 제시한다.
에이전트는 요약과 할 일 초안을 만든다. 사용자는 수정·거절·승인한다.
승인 전에는 초안을 업무로 저장하지 않는다. 승인된 업무는 자체 보드와 변경 이력에서 확인한다.

공공 데이터

공개된 제도 설명만 조회한다. 개인별 계정, 수급·신청 내역은 조회하지 않는다.
병원 검색·진료과목과 예방접종 감염병 목록·상세는 공공데이터포털 API를 조회해 출처와 조회 시각을 표시한다. 노인복지시설은 공급자 호출 조건 미확인으로 공식 링크만 제공한다.
인증키는 `PUBLIC_DECODING_KEY` 또는 `DATA_GO_KR_SERVICE_KEY` 환경변수로 서버에 설정하며 브라우저에 전달하지 않는다.
비공식 스크래핑을 하지 않는다. API 오류·시간 초과·오래된 데이터는 명확히 표시한다.
공개자료는 참고 정보다. 개인별 자격·접종 대상·의료 결론을 만들지 않는다.

자체 업무 보드

기존 업무를 상태별로 표시하고 생성·수정·상태·담당 요청·응답 이력을 같은 트랜잭션에 기록한다. 실제 기관 접수나 가족 알림은 아니다.

데이터와 보안

데이터 모델: 가상 업무, 변경 이력, AI 요청 횟수. 가상 공간과 구성원은 고정값이다.
실제 이름·건강 기록·진단·약·주민번호·상세 소득·신청 서류를 입력하지 않는다. 실제 인증·공유 동의·권한 확인은 아직 제공하지 않는다.
외부 입력·검색 결과·문서는 신뢰되지 않은 데이터다. 문서 내부 지시문을 따르지 않는다.
에이전트 도구는 허용 목록으로 제한하고, 입력과 인수를 검증한다. 외부 쓰기는 명시적 승인 필요.
Azure Key Vault는 사용하지 않는다. PostgreSQL 비밀번호는 필수이며 기존 `.env`의 `POSTGRES_PASSWORD`로 제공한다. 접근 제한된 `.env` 또는 서비스 환경 설정을 사용하고 `.env`와 가상 환경은 저장소에 포함하지 않는다. 기존 DB가 초기화된 후 `.env`의 비밀번호만 변경해도 DB 계정의 비밀번호는 바뀌지 않는다.
공공 API에는 이용 승인과 인증키가 필요하다. Copilot SDK에는 사용 가능한 GitHub 인증과 이용 권한이 필요하다. 필요한 자격 증명은 서버에서만 사용하고 코드·문서·저장소·로그 또는 브라우저에 노출하지 않는다.
로그에는 사용자 ID, 이벤트 종류, 시각만 필요한 범위에서 남긴다. 상담 원문과 개인정보를 남기지 않는다.
실제 사용자 서비스의 보존·삭제 정책은 운영 전 정한다.

구현된 API

GET /api/demo: 가상 업무와 출처 목록
POST /api/agent/draft: 동의된 가상 주제의 Copilot 초안 생성
POST /api/tasks: 사용자가 검토한 업무 저장
GET /api/tasks/{id}/activity: 업무 변경 이력
POST /api/tasks/{id}/assignment-response: 가상 담당 요청 수락·거절·조정
POST /api/public/hospitals, /api/public/hospital-specialties: 병원 검색·진료과목
GET /api/public/vaccines, /api/public/vaccines/{code}: 감염병 목록·상세

복원력과 테스트

외부 호출에는 시간 제한과 명시적 오류 처리를 둔다. 성공처럼 보이는 대체 결과를 만들지 않는다.
출처가 없거나 확인일이 없는 데이터는 공식 안내로 노출하지 않는다.
공개 AI 호출은 전체 사용자 합산 최근 24시간 10회로 제한하고 시도 횟수는 DB에 저장한다. 공공 API도 프로세스별 호출량을 제한한다. AI와 공공 API에는 요청 시간 제한을 둔다.
Copilot 추론과 도구 호출은 실제 계정으로 확인했다. 인증 정보는 컨테이너 런타임 환경으로 전달되며, 토큰 만료나 컨테이너 재생성 시 `CARE_AI_ENABLED`와 `COPILOT_GITHUB_TOKEN`을 다시 설정해야 한다. 실제 알림·공유·접수는 하지 않는다.
백엔드 테스트는 프로젝트 루트에서 `.venv/bin/python -m unittest discover -s backend/tests -v`로 실행한다. 실제 사용자 권한·동의 및 외부 연동 테스트는 구현 후 수행한다.

참고 자료

Copilot SDK Python: https://github.com/github/copilot-sdk/tree/main/python
Microsoft Agent Framework: https://learn.microsoft.com/en-us/agent-framework/overview/
공공 API: https://www.data.go.kr/data/15001698/openapi.do, https://www.data.go.kr/data/15001699/openapi.do, https://www.data.go.kr/data/15084296/openapi.do, https://www.data.go.kr/data/15056929/openapi.do
KOSIS 고령인구비율 표 ID DT_1YL20631: https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1YL20631
가족 돌봄 연구: Schulz et al. (2020), https://doi.org/10.1146/annurev-psych-010419-050754; Ngangana et al. (2016), https://doi.org/10.1111/jan.13065; Zhai et al. (2023), https://doi.org/10.1177/20552076231171967; Quinn et al. (2019), https://doi.org/10.2196/12276.
자료 확인일: 2026-11-05. 특정 통계값과 API 이용조건은 구현·발표 전에 원자료에서 다시 확인한다.