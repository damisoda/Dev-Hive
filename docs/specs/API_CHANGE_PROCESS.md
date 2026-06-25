# 🚨 Dev-Hive 프런트-백 API 변경 관리 절차

본 프로젝트는 Next.js(프런트엔드)와 FastAPI(백엔드) 간의 안정적인 데이터 바인딩을 위해 API 계약을 동결하여 관리합니다. 계약 동결 이후 API 엔드포인트 수정, 메서드 변경, 필드 추가/삭제가 필요할 경우 다음 절차를 엄격히 준수해야 합니다.

## 1. API 변경 프로세스 4단계
1. **사전 협의 및 공유**: 수정이 필요한 라우터와 필드 스펙을 팀 디스코드/카카오톡에 공유하고 프런트엔드 담당자 및 조장의 사전 승인을 획득합니다.
2. **백엔드 선형 구현**: FastAPI 스키마(Pydantic 모델) 및 라우터 코드를 수정하고, 로컬 서버를 가동하여 정상 동작을 확인합니다.
3. **API 스냅샷 및 TS 타입 동기화**: 로컬 서버가 켜진 상태에서 최상위 루트 경로에서 아래 명령어를 순차적으로 실행하여 계약 문서를 최신화합니다.
   ```bash
   # 스냅샷 최신화
   curl http://127.0.0.1:8000/openapi.json -o docs/specs/openapi-snapshot.json
   
   # TS 타입 재생성
   npx openapi-typescript docs/specs/openapi-snapshot.json --output frontend/src/types/schema.ts
   