# 학사 지식베이스 출처와 한계 (2026-11-07 확인)

`src/kw_mcp/knowledge/`의 데이터(`faq.json`, `curricula/`, `rules_tables.json`)를 무엇으로, 어떻게 만들었는지 적은 문서입니다. 학교가 공개한 페이지·규정·첨부에서 왔고, 다전공 학점은 학교 공식 다전공 플래너 Daple 값에 맞췄습니다(아래 'Daple에 맞춘 것'). 실제 처리는 소속 학과 사무실과 담당 부서가 정합니다. 데이터의 모든 항목에는 출처 URL과 확인일이 붙어 있습니다.

## 한눈에 보기

- Q&A 항목 333개, 22개 범주: 장학 38, 다전공 25, 수강신청 23, 학적변동 22, 재수강·성적 19, 졸업 18, 수업·출석 18, 증명서·학생증 17, 전과·전공배정 16, 등록·등록금 16, 기숙사 14, 학점교류·교환학생 13, 학식·편의시설 12, 기타 12, 도서관 11, 진로·취업 11, IT·계정 10, 계절학기 10, 동아리·학생자치 9, 셔틀·교통 7, 상담·학생지원 7, 병무·예비군 5. (1·2차 248개, 3차 뒤 287개)
- 신뢰도: high 157, medium 139, low 37.
- 교육과정: 학과·전공 45곳, 입학연도별 파일 247개(2026 현행 전체 표 + 2019~2025 필수과목).
- 규정 별표 HWP 3개를 표로 옮김(`rules_tables.json`): 학칙 [별표 6] 16개 구간, 연계전공 26개 학점·학위명, 교양교과목 분류.
- 요청 311건(1·2차 228 + 3차 34 + 4차 49), Claude 비용 59.40달러(1·2차 41.03 + 3차 10.47 + 4차 7.90, 장부 기준).

## 수집 방법

- User-Agent `kw-campus-research (contact kyowon1108@gmail.com)`, GET만 썼습니다. 로그인, 폼 입력, 검색 요청은 하지 않았습니다.
- 같은 서버 요청 사이 3.5초 이상. 서버는 IP로 묶어 셌습니다(학과 서브도메인 여러 개가 서버 하나를 쓰는 경우 대비).
- 요청 수는 모두 228건입니다(상한 250, robots.txt 포함). www.kw.ac.kr 185, rule.kw.ac.kr 39, oia.kw.ac.kr 2, kupis.kw.ac.kr 2. 실패는 3건으로 oia robots.txt 404, kupis 2건(인증서 검증 실패)입니다. 인증서 검증을 끄고 다시 받지는 않았습니다.
- robots.txt: www와 rule은 robots.txt 자리에 HTML 페이지가 나와 기계가 읽을 규칙이 없습니다(규칙 작업자가 같은 날 받은 사본을 다시 씀). oia는 404, kupis는 받지 못했습니다. 막는 규칙을 만난 적은 없습니다.
- daple.kwuniv.com과 KLAS(klas.kw.ac.kr)는 열지 않았습니다. `scripts/knowledge/fetch.py`가 두 호스트를 거부합니다. Daple 값은 소유자가 자기 세션에서 뜬 스냅숏에서만 가져왔습니다(아래 'Daple에 맞춘 것').
- 규칙 작업자가 이미 받은 원본 10개(학사안내 01·07·11·12, 학칙, 시행세칙, 다전공 내규 2개, 조기졸업 규정, 교양교육 운영 규정)는 다시 받지 않고 그대로 썼습니다.
- 규정 별표 HWP 3개는 규정 페이지의 '다운받기' 버튼이 보내는 주소(`/lmxsrv/fileDown.do?FILE_SEQ=…&FILE_TYPE=attach`)를 GET으로 받았습니다. 버튼은 원래 같은 값을 POST 폼으로 보내지만, 로그인 없이 GET으로도 같은 파일이 나왔습니다. 이 점은 '폼을 쓰지 않는다'는 원칙의 경계에 있어 따로 적어 둡니다.
- 본문 추출은 이 저장소의 파서(`kw_mcp.text.html_to_text`, `kw_mcp.attachments.extract_text`)로 했습니다. 표는 rowspan·colspan을 펼쳐 `a | b | c` 줄로 바꿨습니다. 필수과목표는 옛 엑셀(.xls, BIFF) 형식이라 `kw_mcp.attachments`가 읽지 못해 파이프라인에서만 `xlrd`로 읽었습니다(.xlsx 2개는 `kw_mcp.attachments`).
- 직원 담당업무 표는 Claude에 보내기 전에 성명·직위·이메일 열을 지웠습니다(`build_faq.scrub_people`). 데이터에는 부서명과 대표번호만 남습니다.

## Claude로 한 일

모델은 `claude-opus-5-5`, 구조화 출력(`output_config.format`)을 썼습니다. 호출마다 지출 장부(`claude-spend/ledger.py`)에 기록했고, 호출 전에 남은 예산이 0.5달러 넘는지 확인했습니다.

| 작업 | 호출 수 | 비용(USD) |
|---|---|---|
| Q&A 작성·검토 | 34 | 23.92 |
| Q&A 독립 감사(15개 범주) | 15 | 5.08 |
| 교육과정 구조화 | 48 | 5.04 |
| Q&A 2차(빈 곳 보충) 작성·검토 | 8 | 3.09 |
| Q&A 범주 간 모순 점검 | 1 | 1.44 |
| 별표 표 구조화 | 1 | 0.98 |
| 교육과정 번역 | 3 | 0.53 |
| Daple 값 맞춤 | 1 | 0.48 |
| 검색 점검 질문 | 1 | 0.47 |
| 연결 확인(시험 호출) | 1 | 0.00 |
| 합계 | 113 | 41.03 |

- Q&A는 범주마다 두 번 불렀습니다. 첫 호출이 문서를 읽고 항목을 쓰고, 두 번째 호출이 같은 문서로 숫자·기한·조건·경로·전화번호·조문을 하나씩 대조해 고치거나 신뢰도를 낮췄습니다.
- 첫 실행에서 '문서에 없음'으로 남은 질문 중 채울 수 있는 것은 자료를 더 받아(수업 운영 규정 별표 3·4, 장학 규정 별표 1, 교과과정 편성 규정, 자율전공학부 규정) 2차로 썼고, '기타' 범주(창업·현장실습·상담·경력개발 등)도 이때 만들었습니다.
- 셔틀·도서관·학식을 뺀 15개 범주는 쓴 적 없는 감사자 역할로 한 번 더 대조했습니다(고칠 항목만 돌려받음). 졸업·다전공·수강신청·재수강·장학·학적변동·등록금 7개는 범주 간 점검 전에, 나머지 8개는 그 뒤에 했습니다.
- 마지막으로 전체 항목을 한 번에 넣어 범주 사이 모순, 전화번호, 중복 항목을 정리했습니다.
- 학칙·시행세칙과 부서 연락처 문서는 모든 Q&A 호출에 들어갔습니다(프롬프트 캐시 사용). 첫 실행은 범주마다 출처 id 목록을 스키마에 넣어 캐시가 거의 맞지 않았고, 스크립트는 그 뒤 스키마를 하나로 고쳤습니다.
- 교육과정은 학과마다 한 번(effort low) 불러 www 표와 필수과목표를 합쳤습니다. 결과의 학정번호는 모두 필수과목표 원문에 있는지, 과목명은 두 문서 중 하나에 있는지 로컬에서 확인했고 통과하지 못한 것은 버리게 했습니다(이번에는 버린 것 0).
- 검색 점검: Claude가 항목마다 기존 질문과 다른 말투의 새 질문을 하나씩 썼고(248개), `search()`가 맞는 항목을 1위로 낸 비율이 0.65, 3위 안이 0.84였습니다. 그 결과를 보고 줄임말 사전과 가중치(사용자 단어 1, 사전으로 늘린 단어 0.5)를 고친 뒤 같은 질문으로 0.71 / 0.90입니다(같은 질문으로 맞춘 값이라 낙관적). 그래도 놓친 질문 25개는 해당 항목의 질문 목록에 더했습니다.
- 출처 URL·제목·규정명·시행일은 Claude가 쓰지 않고 `sources.json`과 규정 머리말에서 로컬로 채웠습니다. Claude가 준 출처 id가 목록에 없으면 그 출처는 버리고, 출처가 하나도 남지 않으면 항목을 버립니다.

## Daple(다전공 플래너)에 맞춘 것

소유자는 학교의 공식 다전공 플래너 Daple(https://daple.kwuniv.com, 기획처 대학혁신사업단 운영)을 다전공·졸업 학점의 기준으로 봅니다. 그래서 공개 자료로 만든 항목을 마지막에 Daple 값에 맞췄습니다.

- **어떻게 읽었나**: 이 파이프라인은 Daple을 열지 않았습니다(`fetch.py`가 호스트를 거부). 소유자가 자기 세션에서 뜬 스냅숏(2026-11-07, 개인 값 없음)에서 트랙 유형·이름·필요 학점·운영/대상 학과·학점 기준표·과목 수만 꺼내 썼습니다(`scripts/knowledge/apply_daple.py`). Daple의 설명 문장이나 과목 목록은 옮기지 않았습니다.
- **출처 표기**: 값이 Daple에 기대는 항목에는 공식 출처 옆에 `다전공 플래너(Daple) 2026-11-07 확인`(https://daple.kwuniv.com)을 붙였습니다. 다전공 계획·시뮬레이션을 묻는 항목은 "공식 다전공 계획·시뮬레이션은 Daple에서" 하라고 안내합니다(URL만, 내부 동작 설명 없음).
- **스냅숏 규모**: 트랙 146개(복수 28, 부 28, 연계 26, 마이크로 64).

**바꾼 항목**: `grad-major-credits`, `multi-minor-credits`, `multi-double-credits`, `multi-linked-major`, `multi-micro-credits`, `multi-major-credit-reduction`, `multi-architecture`, `multi-social-welfare-linked` (새 항목 `multi-planner-daple`).
- grad-major-credits: 복수 45·부전공 21·마이크로 15 고정값 -> 목표 학과 기준(복수 45/54/36/99, 부전공 21·건축 45·행정 30), 연계 30(사회복지학 51), 마이크로 대부분 15(일부 9·12); 행정학과 부전공 불일치 disagreement를 Daple 기준으로 재작성; how_to에 Daple 문장, daple-snapshot 출처 추가
- multi-minor-credits: 21학점 기본+행정 확인 요망 -> 목표 학과 기준 21(행정학과 30, 건축학과 45); disagreement에 학칙·별표6·학사정보 표 값 기재; confidence low -> medium; how_to에 Daple 문장, 출처 추가
- multi-double-credits: 기본 45(2025·2026 표 기준) -> 목표 학과 기준 45(인문사회 등)/54(공학계열·화학·전자바이오물리·스포츠융합과학)/36(법학부)/99(건축학과); 39학점 학과는 Daple에 없음을 disagreement에 기재; confidence low -> medium; Daple 문장·출처 추가
- multi-linked-major: 수치 Daple과 일치 확인, how_to에 Daple 문장, daple-snapshot 출처 추가
- multi-micro-credits: 과정별 15학점 -> 대부분 15, 지능형로봇학과 12, 글로벌지속가능융합학과 9; 15학점 미만 과정 졸업요건 인정 확인 조건 추가; disagreement 추가; confidence high -> medium; Daple 문장·출처 추가
- multi-major-credit-reduction: how_to에 Daple 문장, daple-snapshot 출처 추가(수치는 Daple과 일치)
- multi-architecture: how_to에 Daple 문장, daple-snapshot 출처 추가(99·45 Daple과 일치)
- multi-social-welfare-linked: how_to에 Daple 문장, daple-snapshot 출처 추가(51학점 Daple과 일치)
- multi-planner-daple: 신규 항목 추가(다전공 계획·시뮬레이션은 Daple)

**공개 자료와 Daple이 다른 곳 (항목은 Daple을 따르고 차이를 `disagreement`에 적음)**
- 복수·부전공 학점은 Daple에서 **대상 학과**의 표를 따릅니다. 복수전공 법학부 36, 건축학과 99, 공학계열(전정대·인융대·공대·자연대 대부분) 54, 인문사회·경영 45. 부전공 21, 건축학과 45, 행정학과 30. 행정학과 부전공(아래)을 빼면 이 값은 학칙 [별표 6]의 2017~2024학번 표 '복수전공'·'부전공' 칸과 같습니다. 반면 2025·2026학번 표(별표 6 15·16항, bachelor_info12)는 복수전공을 학과 구분 없이 45(건축학과 99)로 적습니다. 2025학번 이후 학생이 54·36 같은 대상 학과 값을 따르는지, 45를 따르는지는 공개 자료만으로 정리되지 않아 교육지원팀 확인이 필요합니다.
- 행정학과 부전공: Daple 30, 학칙 [별표 6](2017~2024) 21, 웹 bachelor_info12 30.
- 사회복지학 연계전공: Daple 51. 별표1·웹은 2020학번 이전(또는 2019학번까지) 입학자 45를 경과조치로 둡니다.
- 마이크로전공 이름 4개: Daple '기초전공'(지능형로봇학과) = 공개 자료 '로봇기초전공', '바이오헬스케어전공' = '바이오헬스케어', '에너지·환경지속가능성전공' = '에너지‧환경지속가능성전공'(가운뎃점 글자 차이), '문학기반K-콘텐츠전공' = '문학기반K-콘텐츠개발전공'. Q&A 항목에는 이 네 이름이 나오지 않아 고칠 것이 없었습니다. `rules/multi_major.json`은 다른 작업자가 Daple 이름으로 고치는 중입니다.
- 나머지 연계·마이크로 트랙 86개의 학점은 공개 자료와 같습니다.

**교육과정과 Daple 과목 수 비교 (교육과정 파일은 바꾸지 않음)**

Daple의 과목 수는 그 트랙이 인정하는 과목 전체(기준표 연도 기준), 이 지식베이스의 2026 파일은 www '교육과정' 탭의 현행 표라 같은 것을 세지 않습니다. 차이가 큰 곳만 적습니다.

| 대상 학과 | Daple 복수전공 과목 수(기준표) | 2026 현행 표 과목 수(전공) | 비고 |
|---|---|---|---|
| 미디어커뮤니케이션학부 | 81 (admission 2007) | 69 (69) | Daple이 많음 |
| 동북아문화산업학부 | 54 (admission 2017) | 15 (15) | Daple이 많음 |
| 스포츠융합과학과 | 48 (admission 2017) | 37 (37) | Daple이 많음 |
| 지능형로봇학과 | 30 (admission 2022) | 없음 | 이 지식베이스에 2026 표 없음 |
| 국제통상학부 | 57 (admission 2017) | 47 (47) | Daple이 많음 |
| 영어산업학과 | 42 (admission 2007) | 31 (31) | Daple이 많음 |
| 정보융합학부 | 47 (admission 2017) | 40 (33) | Daple이 많음 |
| 전기공학과 | 46 (admission 2017) | 40 (35) | Daple이 많음 |
| 건축학과 | 44 (admission 2003) | 20 (20) | Daple이 많음 |
| 경영학부 | 77 (admission 2003) | 65 (63) | Daple이 많음 |
| 국제학부 | 42 (admission 2016) | 41 (0) | 전공 구분 없는 표 |
| 로봇학부 | 55 (admission 2017) | 55 (45) | Daple이 많음 |
| 수학과 | 48 (admission 2017) | 47 (39) | Daple이 많음 |

연계·마이크로전공은 이 지식베이스에 트랙별 교육과정이 없어 비교하지 않았습니다. 트랙 과목 수는 Daple 기준(연계 26개, 마이크로 64개)이 유일한 출처입니다.

## 3차 보강 (2026-11-07, 첫 평가 라운드 뒤)

평가 1차에서 지어낸 답이 나온 주제는 대부분 자료가 없던 곳이었습니다. 평가 문항과 결과는 열지 않고, 조정자가 준 주제 목록만 보고 채웠습니다.

- **더 받은 자료(34건)**: 공지사항 학사·등록/장학 목록 5쪽, 그 목록에서 제목으로 고른 공지 12건(국가장학금 지급 안내, 유고결석·공결 안내, 수강과목 포기, 재수강 불가 과목 취득학점 포기, 졸업연기·조기졸업 신청, 수강신청 공고, 조기취업자, 성적 확인, 화도·동해장학금 2차, 중간고사 지침, 재입학 전형, 동계계절 학점교류), 단과대학 소개 9쪽(교학팀 번호), 행복기숙사 5쪽(홈·메인·입사/퇴사안내·입사신청·연락처, robots.txt 없음), 열람실 좌석 현황 1쪽(robots.txt 없음). 같은 서버 3.5초 간격, GET만, 로그인 없음.
- **링크만 단 곳**: 중앙도서관 kupis.kw.ac.kr(robots 차단, 받지 않음), 열람실 좌석 현황 http://mobileid.kw.ac.kr/seatweb/domian5.asp(학교가 http로만 제공, 실시간이라 숫자는 옮기지 않음), 행복기숙사 공지사항(목록이 스크립트로 열림). ontl.kw.ac.kr(robots 차단)은 이번 주제에 쓸 곳이 없어 인용하지 않았습니다.
- **Claude**: 10개 범주를 다시 쓰고 검토했고(기존 항목은 같은 id로 보강 가능), 범주 간 점검 1회, 학적변동·장학·수업·출석·등록금 감사 1회씩, 새 질문으로 검색 점검 1회. 26회 호출, 10.47달러.
- **학과 사무실 연락처**: Claude 없이 `build_contacts.py`가 학과 소개 페이지의 '학과문의'와 단과대학 페이지의 교학팀 번호로 단과대학별 항목 9개와 안내 항목 1개를 만들었습니다. 같은 페이지의 담당자 표(이름·이메일)는 쓰지 않았습니다.
- **링크 넣기**: Claude는 페이지 본문만 봐서 주소를 모르고 "주소는 자료에 없음"이라고 쓴 항목이 있었습니다. `apply_links.py`가 열람실·도서관·기숙사·셔틀 항목 12개의 how_to에 공식 주소를 넣고 그 페이지를 출처로 붙였습니다.

| 주제 | 새 항목 | 보강한 기존 항목 |
|---|---|---|
| 휴학·복학 | 5 (복학 종류, 군 제대 복학, 처리 확인, 복학 후 할 일, 휴학 중 등록금·도서) | 휴학 기간·횟수, 재입학, 예비군 신고 |
| 등록금 반환 | 5 (자퇴 환불 절차, 입학금·수업료 반환 차이, 휴학·납부 시점, 유급 등록금, 장애학생 학점등록) | 시기별 반환 비율, 군휴학 등록금 |
| 국가장학금 환수·지급 | 6 (휴학·자퇴 시 처리, 결격사유 반환과 제재부가금, 결과 확인 KLAS 경로, 지급 방식, 화도·동해 2차, 중복) | 장학금 반환, Ⅱ유형, 가계곤란, 등록금 초과 |
| 출석·공결 | 6 (신청 절차·기한, 인정 안 되는 사유, 조기취업, 예비군, 출석 정정, 시험 지침) | 유고결석 허용기간, 공결, 면접 결석 |
| 성적·학점 | 4 (수강포기, 성적증명서, 2년 수료증명, 군입대 중간고사 성적) | 취득학점포기(폐지 과목만), 학사경고 제적 |
| 졸업·계절 | 1 (동계 학점교류 2026) | 조기졸업 기준·신청, 졸업연기, 계절 6학점, 재수강, 휴학생 계절수업 |
| 기숙사 | 5 (입사 서류, 입사 절차, 반입 금지, 고장 신고, 거주증명서) | 신청 방법, 기숙사비, 연락처, 생활 규칙 |
| 도서관·셔틀 | 5 (실시간 좌석 링크, 열람실 좌석 수, 오픈열람실, 셔틀 타는 곳, 하교 셔틀) | 운영시간·연락처에 홈페이지 링크, 셔틀 정보 날짜 |
| 학과 사무실 연락처 | 10 | |

- 범주 간 점검이 새 항목과 겹친 17개를 지웠습니다(예: `enroll-withdraw` → `grade-course-drop`, `military-return-after-discharge` → `status-return-after-military`). 3차 전과 비교하면 47개가 늘고 8개가 빠졌습니다.
- `graduation.json`에 있는 조기졸업, 취득학점포기(폐지·3개 학기 연속 미개설 과목만), 계절 6학점, 군 e-러닝 12학점, 재수강 제한은 이미 항목이 있었고, 3차에서 2026-2학기 공지로 보강했습니다.
- 교시별 수업 시간은 `class-period-times`(학사안내 수업안내 페이지·수업 운영 규정)가 맡습니다. 공식 표에는 0교시가 연강(08:00~10:45 등)으로만 있고, `service.PERIOD_TIMES`의 0교시 08:00~08:50은 공식 페이지에서 확인하지 못했습니다.
- 검색 점검(새로 쓴 287개 질문, 조정 전): 1위 0.763, 3위 안 0.930. 놓친 16개를 항목 질문에 더한 뒤 같은 질문으로 0.815 / 0.983(같은 질문이라 낙관적).

**3차에서도 자료로 채우지 못한 것**
- 출석 정정의 별도 절차: 공지에는 "출석 입력 권한은 수업 담당 교원에게만 있음"까지만 있어, 항목은 담당 교원에게 요청하라고만 안내합니다(medium).
- 휴·복학 처리 결과를 확인하는 KLAS 메뉴: 학적변동 안내는 "처리결과를 반드시 본인이 확인"이라고만 적어, 항목은 교육지원팀 문의로 안내합니다.
- 국가장학금 환수: 한국장학재단 페이지는 받지 않았고, 학교 공지(학적변동 등 결격사유 시 반환, 공공재정환수법 제재부가금)와 장학안내 페이지 범위에서만 답합니다.
- 근로장학: 학교 자료는 신청서를 학생복지팀에 낸다는 것과 국가근로 기본요건까지만 있고, 시급·근무시간·모집 일정은 공지마다 다릅니다.
- 하교 셔틀, 기숙사비·선발 기준: 공식 페이지에 없거나 공지(스크립트 목록)에만 있어 low/medium으로 두고 문의처를 안내합니다.

## 4차 보강 (2026-11-07, 일상 질문)

에브리타임에서 자주 나오지만 비어 있던 생활 질문을 채웠습니다. 평가 문항과 결과는 열지 않았습니다.

- **새 범주 4개**: `IT·계정`(it), `상담·학생지원`(support), `진로·취업`(career), `동아리·학생자치`(club). `build_faq.py`, `validate.py`, `tests/test_knowledge.py`의 범주 목록을 같이 고쳤습니다.
- **더 받은 자료(49건)**: www 공지 목록(일반 3쪽·학생 2쪽·시설 1쪽·취업게시판 2쪽)과 그중 손으로 고른 공지 14건(교내 허가 소프트웨어, 내PC지키미·알약, KLAS 보안 강화(해외 2차 인증·졸업생 로그인 제한), 학생상담실 프로그램, 인권센터 특강, 폭력예방교육, 장소사용 신청(풋살·농구장), 함지마루 운영, 주차장 출입 통제 2건, 학석사연계 수강, 수강신청자료집, 경력개발팀 인스타그램 공지), 부서 소개 6쪽(정보통신처·통신운영팀·체육지원팀·총무처·관리처·현장실습지원팀), 인권센터·장애학생지원실, 장소 사용 안내, 학생자치(총학생회·총동아리연합회·중앙동아리), 경력개발팀 사이트 5쪽(홈·공지 목록·상담안내·취업프로그램·외부상담 공지), 현장실습 첫 화면, 전기공학과 선수과목 상담 공지, 종합 FAQ 1건(비밀번호 분실, 2003년).
- **robots**: job.kw.ac.kr는 `Crawl-delay: 10`이라 그 호스트만 10초 간격으로 받았고, `/recommend/`·`/job/`·`/internship/`는 받지 않았습니다(채용공고는 링크만). internship.kw.ac.kr는 `/index.do`만 허용이라 첫 화면만 받았습니다. 이때 `urllib.robotparser`가 'Disallow: / 다음 Allow: /index.do'를 첫 규칙 기준으로 막아서, `fetch.py`를 RFC 9309(가장 긴 규칙이 이김, 같으면 Allow)로 바꿨습니다. 학생상담실·인권센터 사이트는 열지 않고 www 소개 페이지와 링크만 썼습니다(학생상담실은 공지 밖 접근 금지 원칙).
- **Claude**: 7개 범주 작성·검토(기존 항목 보강 가능, 다른 범주의 비슷한 항목을 같이 보여 줌), 범주 간 점검 1회, 6개 범주 감사, 새 질문 검색 점검 1회. 7.90달러.
- **결과**: 새 항목 57개를 썼고 범주 간 점검이 그중 7개와 예전 항목 4개를 중복으로 지웠습니다(예: `class-course-cancellation` → `enroll-course-closure-criteria`, `class-photo-change` → `cert-photo-change`). 남은 새 항목 50개, 전체 287 → 333개.

| 주제 | 새 항목 |
|---|---|
| IT·계정 | 10 (웹메일 가입, Office 365 자격, 교내 허가 소프트웨어, 어도비 라이선스, 폰트·이미지 저작권, KLAS 비밀번호 분실, 해외 2차 인증, 졸업생 로그인 제한, 수강신청 접속, KLAS 장애 문의) |
| 학생증 | 2 (사진 변경, 학생증 종류) + 기존 학생증·모바일 학생증 보강 |
| 상담·학생지원 | 7 (인권·성평등상담, 장애학생 지원, 폭력예방교육, 심리검사·해석상담, 인권센터 특강, 유학생, 진로상담 안내) |
| 시설 | 3 (풋살·농구장 11월 일정, 시설 고장 신고, 한울관·아이스링크 주차장 공지) + 장소 사용 보강 |
| 진로·취업 | 11 (상담 예약, 졸업생 상담, 프로그램 일정, 취업박람회, 인스타그램 @kwu_career, 진로·취업 교과목, 국민취업지원제도, 제휴 온라인 서비스, 현장실습 신청·문의, 현장실습 학점 인정, 현장실습 보수·시간) |
| 동아리·학생자치 | 9 (가입 방법, 중앙동아리 목록·동아리방, 총학생회, 총동아리연합회, 학생회비, 장소 대여, 게시물 승인, 사회봉사단, 건의) |
| 수강신청 빈 곳 | 8 (시간표 확인, 장바구니, 선수과목, 학석사연계 대학원 과목, 폐강 기준, 폐강 뒤 변경, 복학생 수강신청, 교양 난이도 안내) |

- 검색 점검(새로 쓴 332개 질문, 조정 전): 1위 0.840, 3위 안 0.961. 놓친 9개를 질문에 더한 뒤 같은 질문으로 0.858 / 0.988(낙관적).

**4차에서도 자료로 채우지 못한 것**
- eduroam: 학교 공식 페이지에서 찾지 못했습니다. Wi-Fi 안내는 Kwangwoon_KT·KW_<건물호실>만 적습니다.
- Office 365 신청 경로: 소프트웨어 공지에는 가입 자격만 있고 신청 방법이 없어 통신운영팀 문의로 안내합니다.
- KLAS 비밀번호 찾기: 공식 자료는 2003년 u-Campus FAQ뿐이라 low로 두었습니다. KLAS 로그인 화면은 열지 않았습니다.
- 분실물, 학생회관 시설, 함지마루 외 식당·카페·편의점 운영시간: 공식 페이지에 없습니다(편의시설 페이지는 서점·문구점·아이스링크 등만).
- 주차 요금·등록: 시설 공지 두 건은 본문이 이미지라 제목만 인용했습니다.
- 학생회비 금액과 납부 방법, 동아리 등록(신규 동아리) 절차: 공식 페이지에는 소관 부서와 연락처만 있습니다.
- 수강신청 장바구니: 2026-2학기 수강신청 공고와 자료집 안내에 장바구니 제도가 없어 low로 두었습니다.
- 학생상담실 온라인 예약: www 소개 페이지에는 위치·전화만 있습니다. 상담실 사이트는 열지 않았습니다.

## 읽은 자료와 쓰인 곳

'쓰인 곳'의 (인용됨)은 `faq.json` 항목이 실제로 출처로 단 자료입니다. 상태 '재사용'은 규칙 작업자가 같은 날 받은 원본을 쓴 것입니다.

| id | 자료 | 확인일 | 상태 | 쓰인 곳 |
|---|---|---|---|---|
| web-info01 | [학사정보 교과안내(이수구분)](https://www.kw.ac.kr/ko/life/bachelor_info01.jsp) | 2026-11-07 | 재사용 | Q&A (인용됨) |
| web-info03 | [학사정보 수업안내](https://www.kw.ac.kr/ko/life/bachelor_info03.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-info04 | [학사정보 전공배정 신청 안내](https://www.kw.ac.kr/ko/life/bachelor_info04.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-info05 | [학사정보 성적평가 안내](https://www.kw.ac.kr/ko/life/bachelor_info05.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-info07 | [학사정보 수료/졸업요건 안내](https://www.kw.ac.kr/ko/life/bachelor_info07.jsp) | 2026-11-07 | 재사용 | Q&A (인용됨) |
| web-info08 | [학사정보 학적변동 구분](https://www.kw.ac.kr/ko/life/bachelor_info08.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-info09 | [학사정보 특별프로그램 안내](https://www.kw.ac.kr/ko/life/bachelor_info09.jsp) | 2026-11-07 | 200 | Q&A |
| web-info11 | [학사정보 다전공 이수제도 안내](https://www.kw.ac.kr/ko/life/bachelor_info11.jsp) | 2026-11-07 | 재사용 | Q&A (인용됨) |
| web-info12 | [학사정보 입학연도별 졸업학점 안내](https://www.kw.ac.kr/ko/life/bachelor_info12.jsp) | 2026-11-07 | 재사용 | Q&A (인용됨) |
| web-info13 | [학사정보 수강신청/강의시간표](https://www.kw.ac.kr/ko/life/bachelor_info13.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-info02 | [학사정보 필수과목 개설안내(연도별/학과별)](https://www.kw.ac.kr/ko/life/bachelor_info02.jsp) | 2026-11-07 | 200 | 교육과정 |
| web-rule | [학칙 및 학사관련규정](https://www.kw.ac.kr/ko/life/bachelor_rule.jsp) | 2026-11-07 | 200 | Q&A |
| web-summary | [장학안내](https://www.kw.ac.kr/ko/life/summary.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-scholar01 | [교내장학금](https://www.kw.ac.kr/ko/life/scholarship01.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-scholar02 | [교외장학금](https://www.kw.ac.kr/ko/life/scholarship02.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-scholar03 | [장학재단 예우](https://www.kw.ac.kr/ko/life/scholarship03.jsp) | 2026-11-07 | 200 | Q&A |
| web-cert01 | [제증명안내](https://www.kw.ac.kr/ko/life/certificate01.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-cert02 | [인터넷 증명발급](https://www.kw.ac.kr/ko/life/certificate02.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-cert06 | [증명서 자동발급기](https://www.kw.ac.kr/ko/life/certificate06.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-cert07 | [증명서 창구 발급](https://www.kw.ac.kr/ko/life/certificate07.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-studentid | [학생증발급 안내](https://www.kw.ac.kr/ko/life/student_id.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-isic | [국제학생증 발급 안내](https://www.kw.ac.kr/ko/life/isic.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-military | [병무안내](https://www.kw.ac.kr/ko/life/military_consulting.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-military01 | [병사업무안내](https://www.kw.ac.kr/ko/life/military_guide01.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-facility01 | [복지 편의시설](https://www.kw.ac.kr/ko/life/facility01.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-facility03 | [문화학습지원](https://www.kw.ac.kr/ko/life/facility03.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-facility07 | [전산멀티미디어지원](https://www.kw.ac.kr/ko/life/facility07.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-facility09 | [편의시설안내](https://www.kw.ac.kr/ko/life/facility09.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-facility11 | [식단안내](https://www.kw.ac.kr/ko/life/facility11.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-facility12 | [Wi-Fi 이용 안내](https://www.kw.ac.kr/ko/life/facility12.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-dorm | [생활관](https://www.kw.ac.kr/ko/department/affiliated_etc02.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-directions | [위치 및 교통안내(셔틀)](https://www.kw.ac.kr/ko/tour/directions.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-tour02 | [위치 및 교통안내](https://www.kw.ac.kr/ko/tour/tour02.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-phone | [조회서비스(전화번호)](https://www.kw.ac.kr/ko/tour/phone.jsp) | 2026-11-07 | 200 | 연락처 |
| web-team-edu | [교육지원팀 소개](https://www.kw.ac.kr/ko/department/view.jsp?hpage=intro_0004) | 2026-11-07 | 200 | 연락처 |
| web-team-student | [학생처(학생복지팀) 소개](https://www.kw.ac.kr/ko/department/view.jsp?hpage=intro_0005) | 2026-11-07 | 200 | 연락처 |
| web-team-intl | [국제교류팀 소개](https://www.kw.ac.kr/ko/department/view.jsp?hpage=intro_0014) | 2026-11-07 | 200 | 연락처 |
| web-team-finance | [재무팀 소개](https://www.kw.ac.kr/ko/department/view.jsp?hpage=intro_0017) | 2026-11-07 | 200 | 연락처 |
| web-team-career | [경력개발팀 소개](https://www.kw.ac.kr/ko/department/view.jsp?hpage=intro_0008) | 2026-11-07 | 200 | 연락처 |
| web-counsel | [학생상담실](https://www.kw.ac.kr/ko/department/admin32.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-faq-all | [종합 FAQ 목록](https://www.kw.ac.kr/ko/life/faq.jsp?MaxRows=100&tpage=1&searchKey=1&searchVal=&srCategoryId=) | 2026-11-07 | 200 | Q&A |
| dept-college_001_01 | [전자공학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_001_01) | 2026-11-07 | 200 | 교육과정 |
| dept-college_001_04 | [전자통신공학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_001_04) | 2026-11-07 | 200 | 교육과정 |
| dept-college_001_05 | [전자융합공학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_001_05) | 2026-11-07 | 200 | 교육과정 |
| dept-college_001_02 | [전기공학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_001_02) | 2026-11-07 | 200 | 교육과정 |
| dept-college_001_03 | [전자재료공학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_001_03) | 2026-11-07 | 200 | 교육과정 |
| dept-college_001_08 | [반도체시스템공학부 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_001_08) | 2026-11-07 | 200 | 교육과정 |
| dept-college_011_01 | [컴퓨터정보공학부 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_011_01) | 2026-11-07 | 200 | 교육과정 |
| dept-college_011_02 | [소프트웨어학부 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_011_02) | 2026-11-07 | 200 | 교육과정 |
| dept-college_011_03 | [정보융합학부 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_011_03) | 2026-11-07 | 200 | 교육과정 |
| dept-college_011_04 | [로봇학부 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_011_04) | 2026-11-07 | 200 | 교육과정 |
| dept-college_011_05 | [정보제어·지능시스템전공 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_011_05) | 2026-11-07 | 200 | 교육과정 |
| dept-ai06_1 | [지능형로봇학과 학과 소개](https://www.kw.ac.kr/ko/univ/ai06_1.jsp) | 2026-11-07 | 200 | 교육과정 |
| dept-college_003_01 | [건축공학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_003_01) | 2026-11-07 | 200 | 교육과정 |
| dept-college_003_02 | [화학공학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_003_02) | 2026-11-07 | 200 | 교육과정 |
| dept-college_003_03 | [환경공학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_003_03) | 2026-11-07 | 200 | 교육과정 |
| dept-college_003_04 | [건축학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_003_04) | 2026-11-07 | 200 | 교육과정 |
| dept-college_004_01 | [수학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_004_01) | 2026-11-07 | 200 | 교육과정 |
| dept-college_004_02 | [전자바이오물리학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_004_02) | 2026-11-07 | 200 | 교육과정 |
| dept-college_004_04 | [화학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_004_04) | 2026-11-07 | 200 | 교육과정 |
| dept-college_004_05 | [스포츠융합과학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_004_05) | 2026-11-07 | 200 | 교육과정 |
| dept-college_005_01 | [국어국문학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_005_01) | 2026-11-07 | 200 | 교육과정 |
| dept-college_005_02 | [영어산업학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_005_02) | 2026-11-07 | 200 | 교육과정 |
| dept-college_005_03 | [미디어커뮤니케이션학부 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_005_03) | 2026-11-07 | 200 | 교육과정 |
| dept-college_005_06 | [산업심리학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_005_06) | 2026-11-07 | 200 | 교육과정 |
| dept-college_005_07 | [동북아문화산업학부 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_005_07) | 2026-11-07 | 200 | 교육과정 |
| dept-college_006_01 | [행정학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_006_01) | 2026-11-07 | 200 | 교육과정 |
| dept-college_006_02 | [법학부 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_006_02) | 2026-11-07 | 200 | 교육과정 |
| dept-college_006_05 | [국제학부 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_006_05) | 2026-11-07 | 200 | 교육과정 |
| dept-college_007_01 | [경영학부 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_007_01) | 2026-11-07 | 200 | 교육과정 |
| dept-college_007_02 | [국제통상학부 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_007_02) | 2026-11-07 | 200 | 교육과정 |
| dept-college_010_01 | [금융부동산법무학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_010_01) | 2026-11-07 | 200 | 교육과정 |
| dept-college_010_02 | [게임콘텐츠학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_010_02) | 2026-11-07 | 200 | 교육과정 |
| dept-college_010_03 | [스마트전기전자학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_010_03) | 2026-11-07 | 200 | 교육과정 |
| dept-college_010_04 | [스포츠상담재활학과 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_010_04) | 2026-11-07 | 200 | 교육과정 |
| must-2026-01 | [필수과목표 must_2026_01](https://www.kw.ac.kr/ko/life/must_2026_01.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-02 | [필수과목표 must_2026_02](https://www.kw.ac.kr/ko/life/must_2026_02.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-03 | [필수과목표 must_2026_03](https://www.kw.ac.kr/ko/life/must_2026_03.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-04 | [필수과목표 must_2026_04](https://www.kw.ac.kr/ko/life/must_2026_04.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-05 | [필수과목표 must_2026_05](https://www.kw.ac.kr/ko/life/must_2026_05.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-06 | [필수과목표 must_2026_06](https://www.kw.ac.kr/ko/life/must_2026_06.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-07 | [필수과목표 must_2026_07](https://www.kw.ac.kr/ko/life/must_2026_07.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-08 | [필수과목표 must_2026_08](https://www.kw.ac.kr/ko/life/must_2026_08.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-09 | [필수과목표 must_2026_09](https://www.kw.ac.kr/ko/life/must_2026_09.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-10 | [필수과목표 must_2026_10](https://www.kw.ac.kr/ko/life/must_2026_10.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-11 | [필수과목표 must_2026_11](https://www.kw.ac.kr/ko/life/must_2026_11.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-12 | [필수과목표 must_2026_12](https://www.kw.ac.kr/ko/life/must_2026_12.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-13 | [필수과목표 must_2026_13](https://www.kw.ac.kr/ko/life/must_2026_13.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-14 | [필수과목표 must_2026_14](https://www.kw.ac.kr/ko/life/must_2026_14.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-15 | [필수과목표 must_2026_15](https://www.kw.ac.kr/ko/life/must_2026_15.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-16 | [필수과목표 must_2026_16](https://www.kw.ac.kr/ko/life/must_2026_16.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-17 | [필수과목표 must_2026_17](https://www.kw.ac.kr/ko/life/must_2026_17.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-18 | [필수과목표 must_2026_18](https://www.kw.ac.kr/ko/life/must_2026_18.xlsx) | 2026-11-07 | 200 | 교육과정 |
| must-2026-19 | [필수과목표 must_2026_19](https://www.kw.ac.kr/ko/life/must_2026_19.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-20 | [필수과목표 must_2026_20](https://www.kw.ac.kr/ko/life/must_2026_20.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-21 | [필수과목표 must_2026_21](https://www.kw.ac.kr/ko/life/must_2026_21.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-22 | [필수과목표 must_2026_22](https://www.kw.ac.kr/ko/life/must_2026_22.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-23 | [필수과목표 must_2026_23](https://www.kw.ac.kr/ko/life/must_2026_23.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-24 | [필수과목표 must_2026_24](https://www.kw.ac.kr/ko/life/must_2026_24.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-25 | [필수과목표 must_2026_25](https://www.kw.ac.kr/ko/life/must_2026_25.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-26 | [필수과목표 must_2026_26](https://www.kw.ac.kr/ko/life/must_2026_26.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-28 | [필수과목표 must_2026_28](https://www.kw.ac.kr/ko/life/must_2026_28.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-29 | [필수과목표 must_2026_29](https://www.kw.ac.kr/ko/life/must_2026_29.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-30 | [필수과목표 must_2026_30](https://www.kw.ac.kr/ko/life/must_2026_30.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-31 | [필수과목표 must_2026_31](https://www.kw.ac.kr/ko/life/must_2026_31.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-32 | [필수과목표 must_2026_32](https://www.kw.ac.kr/ko/life/must_2026_32.xls) | 2026-11-07 | 200 | 교육과정 |
| must-2026-33 | [필수과목표 must_2026_33](https://www.kw.ac.kr/ko/life/must_2026_33.xlsx) | 2026-11-07 | 200 | 교육과정 |
| must-2026-34 | [필수과목표 must_2026_34](https://www.kw.ac.kr/ko/life/must_2026_34.xls) | 2026-11-07 | 200 | 교육과정 |
| regview-188 | [4-3-3 계절수업 운영에 관한 규정 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=188) | 2026-11-07 | 200 | Q&A |
| regview-221 | [4-3-4 수강신청에 관한 규정 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=221) | 2026-11-07 | 200 | Q&A |
| regview-223 | [4-3-6 국내대학 수학 및 이수학점 인정에 관한 시행세칙 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=223) | 2026-11-07 | 200 | Q&A |
| regview-211 | [4-3-11 학사경고자 관리 및 지원에 관한 규정 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=211) | 2026-11-07 | 200 | Q&A |
| regview-79 | [4-3-18 국제기관 교환학생에 대한 내규 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=79) | 2026-11-07 | 200 | Q&A |
| regview-89 | [4-3-31 전과에 관한 규정 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=89) | 2026-11-07 | 200 | Q&A |
| regview-90 | [4-3-32 수업 운영에 관한 규정 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=90) | 2026-11-07 | 200 | Q&A |
| regview-87 | [4-3-27 현장실습학기제 운영 규정 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=87) | 2026-11-07 | 200 | Q&A |
| regview-218 | [4-3-33 학생창업 학사지원에 관한 규정 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=218) | 2026-11-07 | 200 | Q&A |
| ruletree-13 | [제4편 제4장 재무행정 목록](https://rule.kw.ac.kr/lmxsrv/law/lawTreeNodes.do?LAWGROUP=1&PARENT=13&TREEDEPTH=3) | 2026-11-07 | 200 | Q&A |
| ruletree-15 | [제4편 제6장 학생행정 목록](https://rule.kw.ac.kr/lmxsrv/law/lawTreeNodes.do?LAWGROUP=1&PARENT=15&TREEDEPTH=3) | 2026-11-07 | 200 | Q&A |
| reg-hakchik | [2-0-1 광운대학교 학칙 (2026.10.28.)](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=21&SEQ_HISTORY=675) | 2026-11-07 | 재사용 | Q&A, 별표 표 (인용됨) |
| reg-sihaeng | [2-0-2 학칙 시행세칙 (2026.02.11.)](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=22&SEQ_HISTORY=614) | 2026-11-07 | 재사용 | Q&A, 별표 표 (인용됨) |
| reg-damajor-isu | [4-3-8 다전공 이수에 관한 내규](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=95&SEQ_HISTORY=672) | 2026-11-07 | 재사용 | Q&A, 별표 표 (인용됨) |
| reg-damajor-unyeong | [4-3-9 다전공 운영에 관한 내규](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=96&SEQ_HISTORY=525) | 2026-11-07 | 재사용 | Q&A, 별표 표 (인용됨) |
| reg-early-grad | [4-3-2 조기졸업에 관한 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=216&SEQ_HISTORY=422) | 2026-11-07 | 재사용 | Q&A, 별표 표 (인용됨) |
| reg-gyoyang | [4-3-1 교양교육 운영 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=77&SEQ_HISTORY=509) | 2026-11-07 | 재사용 | Q&A, 별표 표 |
| annex-hakchik-6 | [학칙 [별표 6] 입학년도별 단과대학(학과)별 이수학점 안내 (HWP)](https://rule.kw.ac.kr/lmxsrv/fileDown.do?FILE_SEQ=3092&FILE_TYPE=attach) | 2026-11-07 | 200 | 별표 표 |
| annex-damajor-1 | [다전공 이수에 관한 내규 [별표1] 연계전공별 이수학점 및 학위명 (HWP)](https://rule.kw.ac.kr/lmxsrv/fileDown.do?FILE_SEQ=3086&FILE_TYPE=attach) | 2026-11-07 | 200 | 별표 표 |
| annex-gyoyang-2 | [교양교육 운영 규정 [별표2] 교양교과목 분류 (HWP)](https://rule.kw.ac.kr/lmxsrv/fileDown.do?FILE_SEQ=2708&FILE_TYPE=attach) | 2026-11-07 | 200 | 별표 표 |
| oia-outbound | [국제교류팀 교환학생(파견) 안내](https://oia.kw.ac.kr/exchange/outbound.php) | 2026-11-07 | 200 | Q&A (인용됨) |
| kupis-home | [중앙도서관 홈](https://kupis.kw.ac.kr/) | 2026-11-07 | ERR:URLError:<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unabl | Q&A (인용됨) |
| curr-college_001_01 | [전자공학과 교육과정](https://www.kw.ac.kr/ko/univ/electronic01_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_001_04 | [전자통신공학과 교육과정](https://www.kw.ac.kr/ko/univ/electronic02_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_001_05 | [전자융합공학과 교육과정](https://www.kw.ac.kr/ko/univ/electronic03_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_001_02 | [전기공학과 교육과정](https://www.kw.ac.kr/ko/univ/electronic06_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_001_03 | [전자재료공학과 교육과정](https://www.kw.ac.kr/ko/univ/electronic07_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_001_08 | [반도체시스템공학부 교육과정](https://www.kw.ac.kr/ko/univ/electronic11_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_011_01 | [컴퓨터정보공학부 교육과정](https://www.kw.ac.kr/ko/univ/ai01_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_011_02 | [소프트웨어학부 교육과정](https://www.kw.ac.kr/ko/univ/ai02_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_011_03 | [정보융합학부 교육과정](https://www.kw.ac.kr/ko/univ/ai03_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_011_04 | [로봇학부 교육과정](https://www.kw.ac.kr/ko/univ/ai04_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_011_05 | [정보제어·지능시스템전공 교육과정](https://www.kw.ac.kr/ko/univ/ai05_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_003_01 | [건축공학과 교육과정](https://www.kw.ac.kr/ko/univ/engineering01_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_003_02 | [화학공학과 교육과정](https://www.kw.ac.kr/ko/univ/engineering02_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_003_03 | [환경공학과 교육과정](https://www.kw.ac.kr/ko/univ/engineering03_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_003_04 | [건축학과 교육과정](https://www.kw.ac.kr/ko/univ/engineering04_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_004_01 | [수학과 교육과정](https://www.kw.ac.kr/ko/univ/science01_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_004_02 | [전자바이오물리학과 교육과정](https://www.kw.ac.kr/ko/univ/science02_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_004_04 | [화학과 교육과정](https://www.kw.ac.kr/ko/univ/science03_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_004_05 | [스포츠융합과학과 교육과정](https://www.kw.ac.kr/ko/univ/science04_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_005_01 | [국어국문학과 교육과정](https://www.kw.ac.kr/ko/univ/social01_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_005_02 | [영어산업학과 교육과정](https://www.kw.ac.kr/ko/univ/social02_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_005_03 | [미디어커뮤니케이션학부 교육과정](https://www.kw.ac.kr/ko/univ/social03_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_005_06 | [산업심리학과 교육과정](https://www.kw.ac.kr/ko/univ/social06_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_005_07 | [동북아문화산업학부 교육과정](https://www.kw.ac.kr/ko/univ/social07_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_006_01 | [행정학과 교육과정](https://www.kw.ac.kr/ko/univ/law01_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_006_02 | [법학부 교육과정](https://www.kw.ac.kr/ko/univ/law02_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_006_05 | [국제학부 교육과정](https://www.kw.ac.kr/ko/univ/law05_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_007_01 | [경영학부 교육과정](https://www.kw.ac.kr/ko/univ/business01_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_007_02 | [국제통상학부 교육과정](https://www.kw.ac.kr/ko/univ/business02_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_010_01 | [금융부동산법무학과 교육과정](https://www.kw.ac.kr/ko/univ/chambit01_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_010_02 | [게임콘텐츠학과 교육과정](https://www.kw.ac.kr/ko/univ/chambit02_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_010_03 | [스마트전기전자학과 교육과정](https://www.kw.ac.kr/ko/univ/chambit03_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_010_04 | [스포츠상담재활학과 교육과정](https://www.kw.ac.kr/ko/univ/chambit04_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| reg-188 | [4-3-3 계절수업 운영에 관한 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=188&SEQ_HISTORY=599) | 2026-11-07 | 200 | Q&A (인용됨) |
| reg-221 | [4-3-4 수강신청에 관한 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=221&SEQ_HISTORY=619) | 2026-11-07 | 200 | Q&A (인용됨) |
| reg-223 | [4-3-6 국내대학 수학 및 이수학점 인정에 관한 시행세칙](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=223&SEQ_HISTORY=429) | 2026-11-07 | 200 | Q&A (인용됨) |
| reg-211 | [4-3-11 학사경고자 관리 및 지원에 관한 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=211&SEQ_HISTORY=417) | 2026-11-07 | 200 | Q&A (인용됨) |
| reg-79 | [4-3-18 국제기관 교환학생에 대한 내규](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=79&SEQ_HISTORY=654) | 2026-11-07 | 200 | Q&A (인용됨) |
| reg-89 | [4-3-31 전과에 관한 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=89&SEQ_HISTORY=676) | 2026-11-07 | 200 | Q&A (인용됨) |
| reg-90 | [4-3-32 수업 운영에 관한 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=90&SEQ_HISTORY=511) | 2026-11-07 | 200 | Q&A (인용됨) |
| reg-87 | [4-3-27 현장실습학기제 운영 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=87&SEQ_HISTORY=218) | 2026-11-07 | 200 | Q&A (인용됨) |
| reg-218 | [4-3-33 학생창업 학사지원에 관한 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=218&SEQ_HISTORY=606) | 2026-11-07 | 200 | Q&A (인용됨) |
| regview-114 | [4-6-4 장학 규정 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=114) | 2026-11-07 | 200 | Q&A |
| regview-230 | [4-4-9 납입금 반환에 관한 규정 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=230) | 2026-11-07 | 200 | Q&A |
| regview-229 | [4-4-8 제증명 수수료 징수 규정 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=229) | 2026-11-07 | 200 | Q&A |
| reg-114 | [4-6-4 장학 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=114&SEQ_HISTORY=666) | 2026-11-07 | 200 | Q&A (인용됨) |
| reg-230 | [4-4-9 납입금 반환에 관한 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=230&SEQ_HISTORY=436) | 2026-11-07 | 200 | Q&A (인용됨) |
| reg-229 | [4-4-8 제증명 수수료 징수 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=229&SEQ_HISTORY=435) | 2026-11-07 | 200 | Q&A (인용됨) |
| faqlist-2 | [종합 FAQ 목록 2쪽](https://www.kw.ac.kr/ko/life/faq.jsp?MaxRows=10&tpage=2&searchKey=1&searchVal=&srCategoryId=) | 2026-11-07 | 200 | Q&A |
| faqlist-3 | [종합 FAQ 목록 3쪽](https://www.kw.ac.kr/ko/life/faq.jsp?MaxRows=10&tpage=3&searchKey=1&searchVal=&srCategoryId=) | 2026-11-07 | 200 | Q&A |
| faqlist-4 | [종합 FAQ 목록 4쪽](https://www.kw.ac.kr/ko/life/faq.jsp?MaxRows=10&tpage=4&searchKey=1&searchVal=&srCategoryId=) | 2026-11-07 | 200 | Q&A |
| faqlist-5 | [종합 FAQ 목록 5쪽](https://www.kw.ac.kr/ko/life/faq.jsp?MaxRows=10&tpage=5&searchKey=1&searchVal=&srCategoryId=) | 2026-11-07 | 200 | Q&A |
| faqlist-6 | [종합 FAQ 목록 6쪽](https://www.kw.ac.kr/ko/life/faq.jsp?MaxRows=10&tpage=6&searchKey=1&searchVal=&srCategoryId=) | 2026-11-07 | 200 | Q&A |
| faqlist-7 | [종합 FAQ 목록 7쪽](https://www.kw.ac.kr/ko/life/faq.jsp?MaxRows=10&tpage=7&searchKey=1&searchVal=&srCategoryId=) | 2026-11-07 | 200 | Q&A |
| faqlist-8 | [종합 FAQ 목록 8쪽](https://www.kw.ac.kr/ko/life/faq.jsp?MaxRows=10&tpage=8&searchKey=1&searchVal=&srCategoryId=) | 2026-11-07 | 200 | Q&A |
| faq-53053 | [종합 FAQ [교육지원팀] 군 복무 e-러닝 수강신청 및 학점 인정 안내](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=53053) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-52309 | [종합 FAQ [교육지원팀] 학적부 정정 신청 안내](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=52309) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-49939 | [종합 FAQ [교육지원팀] 출석부•학생증 사진 변경 방법 안내](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=49939) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-34897 | [종합 FAQ [교육지원팀] 자퇴 신청 절차 안내 (자퇴원서 첨부)](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=34897) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-34581 | [종합 FAQ [교육지원팀] 수강신청 프로그램 설치방법 및 이용방법 안내(2020학년도 리뉴얼)](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=34581) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-829 | [종합 FAQ [교육지원팀] 졸업연기 및 조기졸업 신청방법](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=829) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-791 | [종합 FAQ [예비군연대] 예비군업무 자주하는 질문](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=791) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-783 | [종합 FAQ [재무팀] 학부생 은행정보 등록 안내](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=783) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-782 | [종합 FAQ [재무팀] 졸업요건 미달자에 대한 등록금 책정 기준(학점당 등록)](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=782) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-781 | [종합 FAQ [재무팀] 등록금 반환 안내](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=781) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-780 | [종합 FAQ [재무팀] 교육비납입증명서 발급 안내](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=780) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-779 | [종합 FAQ [재무팀] 등록금 납부 안내](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=779) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-776 | [종합 FAQ [예비군연대] 학생예비군의 연간 교육훈련시간을 알고 싶은데요](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=776) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-775 | [종합 FAQ [예비군연대] 신입생(복학생)예비군의 신고절차는 어떻게 되나요?](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=775) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-774 | [종합 FAQ [예비군연대] 학생예비군으로 재학하고있다가 휴학을 하면 예비군관계는 어떻게 신고를 하면 됩니까?](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=774) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-750 | [종합 FAQ [정보운영팀] 광운대학교 오는 교통편](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=750) | 2026-11-07 | 200 | Q&A (인용됨) |
| dept-college_001_07 | [지능시스템전공 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_001_07) | 2026-11-07 | 200 | 교육과정 |
| dept-college_005_04 | [인터랙티브미디어커뮤니케이션전공 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_005_04) | 2026-11-07 | 200 | 교육과정 |
| dept-college_005_05 | [전략커뮤니케이션전공 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_005_05) | 2026-11-07 | 200 | 교육과정 |
| dept-college_005_08 | [문화콘텐츠개발전공 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_005_08) | 2026-11-07 | 200 | 교육과정 |
| dept-college_006_08 | [기업법무전공 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_006_08) | 2026-11-07 | 200 | 교육과정 |
| dept-college_006_04 | [과학기술법무전공 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_006_04) | 2026-11-07 | 200 | 교육과정 |
| dept-college_006_03 | [국제법무전공 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_006_03) | 2026-11-07 | 200 | 교육과정 |
| dept-college_006_06 | [글로벌코리아전공 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_006_06) | 2026-11-07 | 200 | 교육과정 |
| dept-college_007_03 | [빅데이터경영전공 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_007_03) | 2026-11-07 | 200 | 교육과정 |
| dept-college_007_04 | [국제금융전공 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_007_04) | 2026-11-07 | 200 | 교육과정 |
| dept-college_007_05 | [글로벌비즈니스전공 학과 소개](https://www.kw.ac.kr/ko/univ/depart_intro.jsp?hpage=college_007_05) | 2026-11-07 | 200 | 교육과정 |
| curr-college_001_07 | [지능시스템전공 교육과정](https://www.kw.ac.kr/ko/univ/electronic09_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_005_04 | [인터랙티브미디어커뮤니케이션전공 교육과정](https://www.kw.ac.kr/ko/univ/social04_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_005_05 | [전략커뮤니케이션전공 교육과정](https://www.kw.ac.kr/ko/univ/social05_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_005_08 | [문화콘텐츠개발전공 교육과정](https://www.kw.ac.kr/ko/univ/social08_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_006_08 | [기업법무전공 교육과정](https://www.kw.ac.kr/ko/univ/law08_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_006_04 | [과학기술법무전공 교육과정](https://www.kw.ac.kr/ko/univ/law04_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_006_03 | [국제법무전공 교육과정](https://www.kw.ac.kr/ko/univ/law03_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_007_03 | [빅데이터경영전공 교육과정](https://www.kw.ac.kr/ko/univ/business03_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_007_04 | [국제금융전공 교육과정](https://www.kw.ac.kr/ko/univ/business04_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| curr-college_007_05 | [글로벌비즈니스전공 교육과정](https://www.kw.ac.kr/ko/univ/business05_4.jsp) | 2026-11-07 | 200 | 교육과정 |
| regview-78 | [4-3-10 교과과정 편성 및 운영에 관한 규정 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=78) | 2026-11-07 | 200 | Q&A |
| regview-189 | [4-3-39 자율전공학부 운영에 관한 규정 (개정 정보)](https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=189) | 2026-11-07 | 200 | Q&A |
| annex-class-3 | [수업 운영에 관한 규정 [별표3] 수강인원 (HWP)](https://rule.kw.ac.kr/lmxsrv/fileDown.do?FILE_SEQ=2715&FILE_TYPE=attach) | 2026-11-07 | 200 | 별표 표 |
| annex-class-4 | [수업 운영에 관한 규정 [별표4] 유고결석 사유에 따른 결석 허용기간 (HWP)](https://rule.kw.ac.kr/lmxsrv/fileDown.do?FILE_SEQ=2716&FILE_TYPE=attach) | 2026-11-07 | 200 | 별표 표 |
| annex-scholar-1 | [장학 규정 [별표 1] 장학금 종류별 지급대상 및 신청자격 (HWP)](https://rule.kw.ac.kr/lmxsrv/fileDown.do?FILE_SEQ=3076&FILE_TYPE=attach) | 2026-11-07 | 200 | 별표 표 |
| reg-78 | [4-3-10 교과과정 편성 및 운영에 관한 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=78&SEQ_HISTORY=620) | 2026-11-07 | 200 | Q&A (인용됨) |
| reg-189 | [4-3-39 자율전공학부 운영에 관한 규정](https://rule.kw.ac.kr/lmxsrv/law/lawFullContent.do?SEQ=189&SEQ_HISTORY=601) | 2026-11-07 | 200 | Q&A (인용됨) |
| daple-snapshot | [다전공 플래너(Daple) 2026-11-07 확인](https://daple.kwuniv.com) | - | - | Q&A (인용됨) |
| notices-haksa-1 | [공지사항 학사 목록 1쪽](https://www.kw.ac.kr/ko/life/notice.jsp?srCategoryId=1&mode=list&tpage=1) | 2026-11-07 | 200 | Q&A |
| notices-haksa-2 | [공지사항 학사 목록 2쪽](https://www.kw.ac.kr/ko/life/notice.jsp?srCategoryId=1&mode=list&tpage=2) | 2026-11-07 | 200 | Q&A |
| notices-haksa-3 | [공지사항 학사 목록 3쪽](https://www.kw.ac.kr/ko/life/notice.jsp?srCategoryId=1&mode=list&tpage=3) | 2026-11-07 | 200 | Q&A |
| notices-jang-1 | [공지사항 등록/장학 목록 1쪽](https://www.kw.ac.kr/ko/life/notice.jsp?srCategoryId=4&mode=list&tpage=1) | 2026-11-07 | 200 | Q&A |
| notices-jang-2 | [공지사항 등록/장학 목록 2쪽](https://www.kw.ac.kr/ko/life/notice.jsp?srCategoryId=4&mode=list&tpage=2) | 2026-11-07 | 200 | Q&A |
| college-001 | [단과대학 소개 college_001](https://www.kw.ac.kr/ko/univ/college_view.jsp?hpage=college_001) | 2026-11-07 | 200 | Q&A, 연락처 (인용됨) |
| college-003 | [단과대학 소개 college_003](https://www.kw.ac.kr/ko/univ/college_view.jsp?hpage=college_003) | 2026-11-07 | 200 | Q&A, 연락처 (인용됨) |
| college-004 | [단과대학 소개 college_004](https://www.kw.ac.kr/ko/univ/college_view.jsp?hpage=college_004) | 2026-11-07 | 200 | Q&A, 연락처 (인용됨) |
| college-005 | [단과대학 소개 college_005](https://www.kw.ac.kr/ko/univ/college_view.jsp?hpage=college_005) | 2026-11-07 | 200 | Q&A, 연락처 (인용됨) |
| college-006 | [단과대학 소개 college_006](https://www.kw.ac.kr/ko/univ/college_view.jsp?hpage=college_006) | 2026-11-07 | 200 | Q&A, 연락처 (인용됨) |
| college-007 | [단과대학 소개 college_007](https://www.kw.ac.kr/ko/univ/college_view.jsp?hpage=college_007) | 2026-11-07 | 200 | Q&A, 연락처 (인용됨) |
| college-008 | [단과대학 소개 college_008](https://www.kw.ac.kr/ko/univ/college_view.jsp?hpage=college_008) | 2026-11-07 | 200 | Q&A, 연락처 (인용됨) |
| college-010 | [단과대학 소개 college_010](https://www.kw.ac.kr/ko/univ/college_view.jsp?hpage=college_010) | 2026-11-07 | 200 | Q&A, 연락처 |
| college-011 | [단과대학 소개 college_011](https://www.kw.ac.kr/ko/univ/college_view.jsp?hpage=college_011) | 2026-11-07 | 200 | Q&A, 연락처 (인용됨) |
| dorm-home | [행복기숙사(빛솔재) 홈페이지](https://kw.happydorm.or.kr/) | 2026-11-07 | 200 | Q&A |
| seat-status | [중앙도서관 열람실 좌석 현황](http://mobileid.kw.ac.kr/seatweb/domian5.asp) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53557 | [공지 [학사] 2026학년도 동계계절수업 타대학 학점교류 안내 (본교→타교)](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53557) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53449 | [공지 [학사] 2026학년도 2학기 중간고사 일정 및 시행 지침 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53449) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53320 | [공지 [학사] 2026학년도 2학기 학부 수강과목 포기 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53320) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53174 | [공지 [학사] 2026학년도 2학기 학부 재수강 불가 과목의 취득학점 포기 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53174) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-52920 | [공지 [학사] 2026학년도 2학기 수강신청 공고](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=52920) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53138 | [공지 [학사] 2026학년도 전기(2027. 2.) 졸업연기 및 조기졸업 신청 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53138) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53083 | [공지 [학사] 2026학년도 2학기 조기취업자에 관한 사항 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53083) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53077 | [공지 [학사] 2026학년도 2학기 유고결석 및 공결에 관한 사항 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53077) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-52850 | [공지 [학사] 2026학년도 1학기 성적 확인 및 성적증명서 발급 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=52850) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-52788 | [공지 [학사] 2026학년도 2학기 재입학 전형 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=52788) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53624 | [공지 [등록/장학] 2026학년도 2학기 국가장학금 지급 (예정)안내(1차)](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53624) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53561 | [공지 [등록/장학] 2026학년도 2학기 화도 및 동해장학금 2차 신청 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53561) | 2026-11-07 | 200 | Q&A (인용됨) |
| dorm-main | [행복기숙사(빛솔재) 메인](https://kw.happydorm.or.kr/00/0000.do) | 2026-11-07 | 200 | Q&A (인용됨) |
| dorm-admission | [행복기숙사 입사/퇴사안내](https://kw.happydorm.or.kr/30/3010.do) | 2026-11-07 | 200 | Q&A (인용됨) |
| dorm-apply | [행복기숙사 입사신청](https://kw.happydorm.or.kr/30/3030.do) | 2026-11-07 | 200 | Q&A (인용됨) |
| dorm-contact | [행복기숙사 연락처](https://kw.happydorm.or.kr/10/1040.do) | 2026-11-07 | 200 | Q&A (인용됨) |
| notices-general-1 | [공지사항 일반 목록 1쪽](https://www.kw.ac.kr/ko/life/notice.jsp?srCategoryId=0&mode=list&tpage=1) | 2026-11-07 | 200 | Q&A |
| notices-general-2 | [공지사항 일반 목록 2쪽](https://www.kw.ac.kr/ko/life/notice.jsp?srCategoryId=0&mode=list&tpage=2) | 2026-11-07 | 200 | Q&A |
| notices-general-3 | [공지사항 일반 목록 3쪽](https://www.kw.ac.kr/ko/life/notice.jsp?srCategoryId=0&mode=list&tpage=3) | 2026-11-07 | 200 | Q&A |
| notices-student-1 | [공지사항 학생 목록 1쪽](https://www.kw.ac.kr/ko/life/notice.jsp?srCategoryId=2&mode=list&tpage=1) | 2026-11-07 | 200 | Q&A |
| notices-student-2 | [공지사항 학생 목록 2쪽](https://www.kw.ac.kr/ko/life/notice.jsp?srCategoryId=2&mode=list&tpage=2) | 2026-11-07 | 200 | Q&A |
| notices-facility-1 | [공지사항 시설 목록 1쪽](https://www.kw.ac.kr/ko/life/notice.jsp?srCategoryId=6&mode=list&tpage=1) | 2026-11-07 | 200 | Q&A |
| notices-job-1 | [취업게시판 목록 1쪽](https://www.kw.ac.kr/ko/life/job.jsp?mode=list&tpage=1) | 2026-11-07 | 200 | Q&A |
| notices-job-2 | [취업게시판 목록 2쪽](https://www.kw.ac.kr/ko/life/job.jsp?mode=list&tpage=2) | 2026-11-07 | 200 | Q&A |
| web-team-it | [정보통신처(정보운영팀) 소개](https://www.kw.ac.kr/ko/department/view.jsp?hpage=intro_0019) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-team-network | [통신운영팀 소개](https://www.kw.ac.kr/ko/department/view.jsp?hpage=intro_0020) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-team-sports | [체육지원팀 소개](https://www.kw.ac.kr/ko/department/view.jsp?hpage=intro_0006) | 2026-11-07 | 200 | Q&A |
| web-team-general | [총무처(총무팀) 소개](https://www.kw.ac.kr/ko/department/view.jsp?hpage=intro_0016) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-team-facility | [관리처(시설안전관리팀) 소개](https://www.kw.ac.kr/ko/department/view.jsp?hpage=intro_0018) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-team-internship | [현장실습지원팀 소개](https://www.kw.ac.kr/ko/department/view.jsp?hpage=intro_0009) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-humanrights | [인권센터](https://www.kw.ac.kr/ko/department/admin31.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-disability | [장애학생지원실](https://www.kw.ac.kr/ko/department/admin33.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-facility10 | [장소 사용(신청) 안내](https://www.kw.ac.kr/ko/life/facility10.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-facility04 | [대강당/소강당](https://www.kw.ac.kr/ko/life/facility04.jsp) | 2026-11-07 | 200 | Q&A |
| web-tour01 | [광운캠퍼스안내](https://www.kw.ac.kr/ko/tour/tour01.jsp) | 2026-11-07 | 200 | Q&A |
| web-activity01 | [학생자치활동(학생자치기구)](https://www.kw.ac.kr/ko/life/activity01.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-activity02 | [총동아리연합회](https://www.kw.ac.kr/ko/life/activity02.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| web-activity03 | [중앙동아리](https://www.kw.ac.kr/ko/life/activity03.jsp) | 2026-11-07 | 200 | Q&A (인용됨) |
| job-home | [경력개발팀(인재개발원) 홈](https://job.kw.ac.kr/) | 2026-11-07 | 200 | Q&A (인용됨) |
| job-notice | [경력개발팀 공지사항 목록](https://job.kw.ac.kr/community/notice.php) | 2026-11-07 | 200 | Q&A |
| internship-home | [현장실습지원팀 첫 화면](https://internship.kw.ac.kr/index.do) | 2026-11-07 | 200 | Q&A (인용됨) |
| dept-electric-852 | [전기공학과 공지 2026-2 이수체계 준수제도 및 선수 교과목 미이수자 상담 안내](https://electric.kw.ac.kr/community/s_notice.php?BoardMode=view&UID=852) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53558 | [공지 [학생] 장소사용 신청 안내(2026년 11월)](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53558) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53200 | [공지 [학생] 2026-2 복지관 3층 학생식당(함지마루) 운영 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53200) | 2026-11-07 | 200 | Q&A |
| notice-53599 | [공지 [시설] 한울관 및 아이스링크 주차장 입구 차량 출입 통제 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53599) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53462 | [공지 [시설] 한울관 및 아이스링크 주차장 출입구 변경 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53462) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53458 | [공지 [정보통신처] 불법 소프트웨어, 이미지, 폰트 사용 및 배포 방지를 위한 협조 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53458) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53457 | [공지 [정보통신처] 내PC지키미를 이용한 PC보안 및 알약 점검 협조 요청](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53457) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53483 | [공지 [학사] KLAS 종합정보서비스 보안 강화 조치 시행 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53483) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53549 | [공지 [학생상담실] 뇌파·맥파 측정 체험 및 해석상담](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53549) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53505 | [공지 [인권센터 특강] AI·SNS 시대 디지털 경계](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53505) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-52442 | [공지 [학생] 2026 폭력예방교육 수강 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=52442) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-53210 | [공지 [취업] 2026-2 비교과프로그램 운영 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53210) | 2026-11-07 | 200 | Q&A |
| notice-53211 | [공지 [취업] 2026-2 온라인 이력서 클리닉](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=53211) | 2026-11-07 | 200 | Q&A |
| notice-52987 | [공지 [학사] 2026-2 학부·대학원 연계과목(학석사연계과정) 수강신청 안내](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=52987) | 2026-11-07 | 200 | Q&A (인용됨) |
| notice-52981 | [공지 [학사] 2026-2 수강신청자료집](https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=52981) | 2026-11-07 | 200 | Q&A (인용됨) |
| job-counsel-info | [경력개발팀 진로·취업 상담안내](https://job.kw.ac.kr/jobprogram/counsel_info.php) | 2026-11-07 | 200 | Q&A (인용됨) |
| job-program-intro | [경력개발팀 취업프로그램](https://job.kw.ac.kr/jobprogram/program_intro.php) | 2026-11-07 | 200 | Q&A (인용됨) |
| job-notice-12476 | [경력개발팀 공지 10월 외부상담사(온라인) 진로 및 취업상담 신청 안내](https://job.kw.ac.kr/community/notice.php?BoardMode=view&UID=12476) | 2026-11-07 | 200 | Q&A (인용됨) |
| faq-755 | [종합 FAQ [정보운영팀] 홈페이지 및 종합정보서비스 비밀번호를 분실한 경우](https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=755) | 2026-11-07 | 200 | Q&A (인용됨) |
| job-51947 | [취업게시판 경력개발팀 취업정보 인스타그램(@kwu_career) 제공 안내](https://www.kw.ac.kr/ko/life/job.jsp?BoardMode=view&DUID=51947) | 2026-11-07 | 200 | Q&A (인용됨) |

## 읽지 못한 것과 빈 곳

**받지 못했거나 읽지 못한 페이지**
- 중앙도서관 사이트(kupis.kw.ac.kr): 인증서 검증에 실패해 받지 않았습니다. 도서관 항목은 www '문화학습지원 > 도서관' 페이지(운영시간·자료실)와 전산 페이지만 근거로 합니다. 대출 권수·기간, 스터디룸 예약, 상호대차는 확인하지 못했습니다.
- 학사안내 '특별프로그램 안내'(bachelor_info09): 404(서비스 준비중).
- '학칙 및 학사관련규정'(bachelor_rule.jsp), '조회서비스 교내전화번호'(phone.jsp): 본문이 스크립트로 채워져 GET으로는 빈 틀만 옵니다.
- 학사일정(bachelor_calendar.jsp): 데이터가 POST로 와서 읽지 않았습니다. 그래서 수강신청·정정·포기·휴복학·다전공 신청의 **날짜는 지식베이스에 없습니다.** 항목은 '매 학기 공지 확인'으로 안내합니다.
- 행복기숙사(kw.happydorm.or.kr): 공지가 POST로 와서 읽지 않았습니다. 기숙사 항목은 www 생활관 소개 페이지만 근거로 해, 기숙사비·선발 기준·입퇴사 일정은 대부분 '생활관 문의'로 남았습니다.
- 교직과정(teacher.kw.ac.kr), ROTC: 이번에 열지 않았습니다(로드맵 조사 때 타임아웃).
- 국제처 교환학생 페이지는 파견 조건과 협정교 목록까지만 읽었고, 학교별 세부 조건 페이지는 열지 않았습니다.
- 종합 FAQ 79건 중 학생 업무와 관련된 16건만 열었습니다(정보운영팀의 옛 u-Campus 오류, 교수학습센터 강의실 장비, 재무팀 구매 절차 등은 제외).

**교육과정에서 빈 곳**
- www 학과 '교육과정' 탭에는 학정번호가 없습니다. 학정번호는 필수과목표에 나오는 과목에만 채웠고, 나머지(대부분의 전공선택)는 `code: null`입니다. KLAS 성적의 학정번호와 맞추려면 과목명으로 맞춰야 합니다.
- 입학연도별 전체 교육과정은 공개돼 있지 않습니다. 2026은 현행 표 전체(`scope: full`), 2019~2025는 필수과목표에서 대각선으로 뽑은 필수과목만(`scope: required_only`)입니다. 필수과목표의 '연도' 행은 입학연도가 아니라 그 해 학년별 필수과목이라, 입학연도 A의 g학년 필수과목을 A+g-1 행에서 가져왔습니다. 2027년 이후 학년은 아직 없습니다.
- 금융부동산법무학과: 필수과목표 링크가 국제학부 파일을 가리켜(학교 페이지 오류로 보임) 2026 현행 표만 있습니다.
- 정보콘텐츠학과(야)·자산관리학과(야): www 교육과정 탭이 없어 2019~2024 필수과목만 있습니다.
- 소프트웨어학부·정보융합학부·환경공학과·미디어커뮤니케이션학부 등 일부는 2024~2025 필수과목표 행에 전공필수가 없어 그 입학연도 파일이 없습니다.
- 글로벌코리아전공: 교육과정 탭이 없습니다.
- 학부 안 전공 페이지 일부는 학부 표와 같습니다. 미디어커뮤니케이션학부와 두 전공(인터랙티브미디어·전략커뮤니케이션)은 같은 표, 국제금융전공과 글로벌비즈니스전공은 같은 표, 로봇학부와 정보제어·지능시스템전공은 같은 표입니다.
- 필수과목표와 www 표의 학점이 다른 과목이 있습니다(예: 소프트웨어학부 리눅스활용실습 2 대 3). 학과별 `notes`에 적었습니다. 필수과목표 칸이 학점인지 시수인지 확실하지 않습니다.

**Q&A를 쓰면서 Claude가 '문서에 없음'으로 남긴 질문(범주별 일부)**

1차 작성 때 남긴 목록입니다. 이 중 유고결석 허용기간, 폐강·수강인원 기준, 자율전공학부 전공 선택, 장학금 종류별 자격(장학 규정 별표 1), 창업휴학 기간, 정규학기 폐강 인원은 자료를 더 받아 2차에서 채웠습니다.
- 수강신청: 수강신청 장바구니(희망과목 담기) 제도 유무는 문서에 없음 / 선수과목 미이수 시 수강신청 제한 여부는 문서에 없음 / 학부생의 대학원 과목 수강 가능 여부는 문서에 없음 / 수강포기 가능 과목 수 제한과 성적표 표기 여부는 문서에 없음
- 재수강·성적: 2026학년도 1학기 이전 재수강 과목에 적용된 재수강 성적 상한(예: A0 등)은 문서에 없음 / 재수강 신청 방법(KLAS 메뉴 경로)은 문서에 없음 / 성적 열람·이의신청의 구체적 기간과 KLAS 메뉴는 문서에 없음 / 학사경고자 수강신청 학점 상한 여부는 문서에 없음
- 계절학기: 계절학기 수강료의 구체적 금액과 납부 방법·기간·환불 기준(규정은 총장이 개강 전에 정한다고만 함) / 정규학기 폐강기준의 구체적 인원 수 / 계절학기 재수강 시 취득 성적 상한 여부 / 계절학기 수강신청·정정 일정과 KLAS 메뉴 경로(분기별 공지 참조로만 안내됨)
- 수업·출석: 취업면접으로 인한 결석의 공결 인정 여부와 절차: 문서에 명시 없음(졸업예정자 조기취업만 규정). 교육지원팀(02-940-5022)에 확인 필요 / 유고결석 사유별 결석 허용기간(수업 운영 규정 별표4): 별표 내용이 제공되지 않음 / 예비군·병역 공결의 구체적 신청 경로(KLAS 메뉴, 제출 서류): 문서에 없음 / 본교 원격강좌(온라인 수업)의 출석 인정 기준: 별도 규정으로 정한다고만 되어 있고 내용이 제공되지 않음
- 학적변동: 휴학 중 계절학기 수강 가능 여부는 문서에 없습니다(교육지원팀 계절학기 담당 02-940-5022에 확인 필요) / 휴학 중 다전공 신청 가능 여부는 문서에 없습니다(교육지원팀 02-940-5024에 확인 필요) / 휴학·복학·유급·재입학 신청의 구체적인 날짜는 학기별 별도 공지로만 안내됩니다 / 개강 후 질병휴학을 몇 주차까지 받는지는 문서에 없습니다
- 졸업: 졸업사정 결과 확인 방법(KLAS 메뉴 경로 등)이 문서에 없음. 졸업사정은 교육지원팀(02-940-5022)이 담당한다는 사실만 확인됨 / 졸업유예 중 수강신청을 하지 않을 때 등록금(또는 등록) 의무 여부와 졸업유예 가능 횟수·학기 수가 문서에 없음 / 학위수여식의 구체적 날짜와 장소가 문서에 없음 / 다전공 포기 신청 절차·기한이 문서에 없음
- 다전공: 다전공을 최대 몇 개까지 동시에 이수할 수 있는지(개수 제한)는 문서에 규정이 없음 / 마이크로전공을 몇 개까지 이수할 수 있는지, 현재 개설된 마이크로전공 목록은 문서에 없음 / 다전공 신청·취소의 구체적 날짜와 KLAS 세부 메뉴 경로는 문서에 없음 / 학생설계융합전공 개설 신청기간 및 신청서 양식은 문서에 없음
- 전과·전공배정: 학부 내 전공배정 시 지원자가 많을 때의 선발 기준(성적 등)은 문서에 없음 / 연도별 전과·전공배정·전공변경의 구체적 신청 일정은 문서에 없음(홈페이지 공지사항 참조로만 안내됨) / 전과 전형료 금액과 단과대학별 세부 전형기준은 문서에 없음 / 전과 시 이전 학과에서 이수한 전공과목의 구체적 인정 방식은 전과 규정에 없음
- 학점교류·교환학생: 학점교류 가능한 국내 협약대학 목록: 자료에 없음(교육지원팀 02-940-5512 확인 필요) / 학점교류 신청 기간과 KLAS 신청 메뉴 경로: 자료에 없음 / 국내 학점교류 성적의 평점평균(GPA) 포함 여부: 세칙에 명시 없음 / 타대 계절학기 학점교류와 본교 계절수업을 함께 들을 때의 합산 학점 한도: 자료에 명시 없음
- 장학: 국가장학금Ⅱ유형의 구체적 자격요건과 지급액은 제공 문서에 없음 / 다자녀 국가장학금의 자녀 수별 지원 금액·세부 기준은 문서에 없음 / 국가장학금 소득구간별 지원 금액은 문서에 없음 / 장학금 신청용 KLAS 메뉴 경로는 문서에 제시되지 않음
- 등록·등록금: 등록금 분할납부 횟수, 회차별 금액, 신청·납부 기간(규정에 '별도로 정한다'고만 되어 있음) / 신용카드로 등록금 납부 가능 여부와 방법 / 등록기간을 놓친 경우 추가등록 기간 존재 여부 / 학자금 대출 자격·신청 기간·신청 방법(담당 부서만 확인됨)
- 증명서·학생증: 성적증명서 국내 우편 발송 절차와 비용은 문서에 없음 / '해외우편 신청' 메뉴는 있으나 신청 방법·비용·소요기간이 문서에 없음 / 행정기관 FAX 민원의 이용 가능 기관·비용·절차가 문서에 없음 / 학생증 분실 시 재발급 절차와 비용이 문서에 없음
- 기숙사: 기숙사 신청 기간·신청 사이트·제출 서류 / 기숙사비·보증금 금액 / 선발 기준(거리·성적 배점, 신입생/재학생 우선순위) / 호실 구성(인실), 동별 수용 인원, 남녀 동 구분
- 셔틀·교통: 주차: 학생 주차 가능 여부, 주차 요금, 차량 등록, 주차장 위치는 문서에 없습니다 / 오후 셔틀이나 학교→역 방향 셔틀 운행 여부는 문서에 없습니다 / 광운대역 출발 셔틀이 있는지는 문서에 없습니다(안내된 노선은 석계역·태릉 출발뿐입니다) / 계절학기 기간 셔틀 운행 여부는 문서에 없습니다(방학 기간 제외라고만 안내되어 있습니다)
- 도서관: 열람실 좌석 예약·배정 방법(앱/키오스크 등)은 자료에 없음 - 중앙도서관 확인 필요 / 도서 대출 권수·대출 기간·연장·연체료는 자료에 없음 / 졸업생·휴학생의 도서관 출입 및 대출 가능 여부는 자료에 없음 / 그룹스터디룸(집현전) 예약 절차, 인원·이용시간 제한은 자료에 없음
- 학식·편의시설: 교내 편의점·카페의 위치와 운영시간이 문서에 없습니다(학생복지팀 확인 필요) / 체력단련실(헬스장) 위치·이용시간·이용료가 문서에 없습니다 / 학생식당 저녁 운영 여부, 주말·방학 운영 여부, 함지마루 외 다른 식당 정보가 없습니다 / 천원의 아침밥 이용 대상, 수량 제한, 방학 중 운영 여부가 없습니다
- 병무·예비군: 예비군 훈련 참석 시 수업 공결(출석 인정) 여부와 신청 절차는 제공된 문서에 없습니다. 교무처 교육지원팀 또는 예비군연대에 확인이 필요합니다 / 군휴학·복학의 KLAS 메뉴 경로와 온라인 신청 가능 여부는 문서에 없습니다 / 현재 재학생 입영연기 제한연령과 병무청 출원 경로가 최신인지는 문서로 확인되지 않습니다(병사업무안내 페이지는 작성일 미상) / 올해 예비군 훈련 일정·장소와 2학기 전입신고 기간 등 구체 날짜는 현재 기준 문서가 없습니다(FAQ는 2003·2006년 작성)
- 기타: 교내 컴퓨터실(실습실) 위치·이용시간과 프린트 이용 방법·요금은 문서에 없음 / 학생상담실 상담 비용, 예약 방법, 운영시간은 문서에 없음 / 현장실습지원팀 전화번호·위치, 현장실습온라인시스템 주소, 학기별 모집 일정은 문서에 없음 / 창업휴학 신청 기간과 창업대체학점의 구체적 인정 한도(학점 수)는 문서에 없음

## 출처끼리 다른 곳

Q&A 항목의 `disagreement`에 하나씩 적었고 그 항목의 신뢰도는 medium 이하입니다. 주요한 것:

- `enroll-max-credits`: 학칙 제46조 제1항·제6항은 정규학기 수강신청학점을 12~19학점(2016학번까지 12~21학점)으로 정하고 예외를 두지 않지만, 수강신청 규정과 안내 페이지는 평점 3.5 이상 3학점 추가(2017학번부터)와 학점이월(2016학번까지)을 허용합니다.
- `enroll-extra-credits`: 수강신청 규정과 안내 페이지는 평점 3.5 이상 시 3학점 추가를 허용하지만, 학칙 제46조 제6항은 2017학년도 신입생부터 정규학기 수강신청학점을 12~19학점으로 정하고 예외를 두지 않습니다.
- `enroll-credit-carryover`: 수강신청 규정과 안내 페이지는 학점이월로 최대 신청학점을 1~2학점 초과할 수 있다고 하지만, 학칙 제46조 제1항은 정규학기 수강신청학점을 12~21학점으로 정하고 초과 예외를 두지 않습니다.
- `enroll-change-period`: 안내 페이지는 개강 후 정정기간에 잔여 여석으로 수강신청을 변경할 수 있다고 안내하지만, 수강신청 규정 제7조는 변경을 원칙적으로 불허하고 폐강·불가항력의 경우에만 허용한다고 정하고 있습니다. 실제 허용 범위는 해당 학기 공지로 확인하세요.
- `enroll-program-install`: FAQ(2022년 수정)는 KLAS에서 다운로드한다고 안내하고, 학사정보 페이지는 홈페이지 '재학생' 클릭 후 종합정보서비스에서 다운로드한다고 안내합니다.
- `enroll-online-limit`: e-러닝 안내는 최대 수강신청학점을 21학점으로 적고 있으나, 학칙과 수강신청 규정상 2017학번부터 최대는 19학점입니다. 본인 학번 기준 최대 학점을 적용하세요.
- `enroll-schedule-where`: 안내 페이지는 '참빛인재대학'으로 표기하지만, 학칙(2026.8.12. 개정)은 참빛인재대학을 산업융합대학으로 바꾸었고 해당 개정은 2028학년도 신입생부터(경과조치 2028.3.1.) 적용됩니다. 명칭 변경 이후 일정 배정은 해당 학기 공지로 확인하세요.
- `enroll-seat-quota`: 안내 페이지는 10% 예외 대상을 '참빛인재대학'으로 표기하지만, 학칙(2026.8.12. 개정)은 참빛인재대학을 산업융합대학으로 바꾸었고 해당 개정은 2028학년도 신입생부터(경과조치 2028.3.1.) 적용됩니다. 명칭 변경 이후 여석 운영은 해당 학기 수강신청 자료집으로 확인하세요.
- `enroll-credit-exchange`: 학칙 제46조의2는 교류대학 수학 요건을 1년 이상 이수·35학점 이상 취득으로 정하고, 안내 페이지는 신청자격을 2~4학년으로만 안내합니다.
- `grade-retake-limit`: 학칙과 수강신청규정은 재학 중 최대 8과목이라고만 정하고, 교육지원팀 페이지는 F·NP 과목을 과목 수에서 제외한다고 안내합니다. 본인 사례는 교육지원팀에 확인하세요.
- `grade-relative-distribution`: 시행세칙은 비상대평가 대상을 20명 이하·실험실습·군사학과목 등으로 적고, 교육지원팀 페이지는 설계·스포츠군 교양·교직과목 등을 추가로 나열합니다. 교직과정 조항은 학칙에서 삭제(2026.2.11.)되어 페이지 일부가 갱신되지 않았을 수 있습니다.
- `grade-gpa-calculation`: 시행세칙의 산식은 수강신청 학점수로 나눠 F(0.0)가 평균에 반영되는 구조이지만, 교육지원팀 페이지의 취득학점 포기 안내는 F학점을 '평량평균에 반영되지 않는 과목'으로 분류합니다.
- `grade-f-credit`: 시행세칙은 평점평균 분모를 수강신청 학점수로 정해 F(0.0)가 평균에 반영되는 구조인데, 교육지원팀 페이지의 취득학점 포기 안내는 F학점을 '평량평균에 반영되지 않는 과목'으로 분류합니다.
- `grade-credit-withdrawal`: 학칙은 '3개 학기 이상 연속 미개설' 과목으로 정하고, 교육지원팀 페이지는 '해당 학기 미개설이면서 직전 3개 학기도 연속 미개설'인 과목으로 안내해 기준 학기 수가 다르게 읽힐 수 있습니다. 또 학칙은 성적증명서에 'W' 표기라고만 하나, 페이지는 학적부 성적증명서에는 '삭제', 제출용에는 'W'로 표기한다고 안내합니다.
- `grade-withdrawal-restrictions`: 페이지는 F를 '평량평균에 반영되지 않는 과목'으로 분류해 포기 대상에서 제외하지만, 시행세칙의 평점평균 산식(수강신청 학점수로 나눔)상 F는 평균에 반영되는 구조입니다.
- `status-leave-limit`: 학칙은 '한 번에 두 학기 이내, 통산 6학기'처럼 학기 수로 한도를 정합니다. 반면 학사정보 페이지는 일반휴학을 '1년(두 학기), 3회'로 안내합니다. 그래서 한 학기씩 나눠 휴학할 때 몇 번까지 되는지는 두 문서가 다르게 읽힐 수 있습니다.
- `status-leave-first-semester`: 시행세칙은 신입·편입·재입학자의 첫 학기 휴학 예외를 '부득이한 사유'로 넓게 정하고, 복학생에 대한 제한은 두지 않습니다. 반면 학사정보 페이지는 예외를 군입대·질병으로 한정하고, 당해 학기 재입학생·복학생은 예외 없이 휴학 불가로 안내합니다.
- `status-leave-late-application`: 학사정보 페이지는 일반휴학 시 휴학 처리일 기준으로 반환 규정에 따라 등록금을 반환한다고 안내합니다. 그러나 학칙 제27조와 반환 규정 제1조는 반환 사유로 자퇴·입학포기·장학금 수혜자 휴학 등만 열거하고 일반휴학은 명시하지 않으므로 교육지원팀·재무팀에 확인이 필요합니다.
- `status-military-leave`: 시행세칙은 휴학원서를 '입영일자 15일 이내'에 제출하도록 정하고 있습니다. 학사정보 페이지는 '입영일자 15일전부터 신청 가능'으로 안내해 표현이 다르므로, 정확한 신청 가능 기간은 교육지원팀에 확인하십시오.
- `status-leave-tuition-refund`: 학사정보 페이지는 일반휴학 시 반환 규정에 따라 반환한다고 안내합니다. 그러나 학칙 제27조와 반환 규정 제1조는 반환 사유로 자퇴·입학포기·장학금 수혜자 휴학 등만 열거하고 일반휴학은 명시하지 않습니다. 또 시행세칙은 '등록금', 반환 규정은 '수업료'를 기준으로 적고 있으므로 교육지원팀·재무팀에 확인이 필요합니다.
- `status-return-apply`: 학칙 제33조는 복학을 개강 후 3주 이내에 허가할 수 있다고 정하고 있습니다. 반면 학사정보 페이지는 신청기간을 '개강 전 소정기간(반드시 준수)'으로 안내하므로, 개강 후 신청이 가능한지는 교육지원팀에 확인하십시오.
- `status-withdrawal-procedure`: 학칙 제34조는 자퇴원을 학부장 또는 학과장과 학장을 거쳐 교무처에 제출하도록 정하고 있습니다. 반면 종합 FAQ는 지도교수·학과장 서명만 안내하므로, 학장 확인이 필요한지는 교육지원팀에 확인하십시오.
- `status-readmission`: 시행세칙은 징계·입학 관련 제적자의 재입학을 '원칙적으로' 불허하되 신청자가 예외사정을 입증할 수 있게 하고, 상벌 시행세칙 제5조 해당자는 '불허할 수 있다'고 정합니다. 반면 학사정보 페이지는 두 경우 모두 예외 없이 '재입학 불허'로 안내합니다.
- `status-reserve-forces-leave`: 학사정보 페이지는 KLAS 행정서비스 메뉴에서 신고하고 기간은 별도 공지한다고 안내하지만, 예비군 FAQ는 인터넷 복학신청 화면에서 신고하고 기간을 복학신청일부터 개강 후 14일 이내로 안내합니다.
- `grad-requirements-overview`: 교육지원팀 안내 페이지는 모든 학생이 1학년 교양(공통)필수를 반드시 이수해야 한다고 적고 있습니다. 반면 별표 6 제14호와 학칙 부칙(2025.12.17.)은 2025학번 이전 입학자의 광운인되기와 2016~2024학번의 필수교양 이수를 면제하고 총 교양학점만 채우도록 합니다. 또한 별표 6 제14호는 2016~2024학번 면제 대상에서 '광운인되기'를 제외한다고 적고 있어, 2025학번 이전 입학자의 광운인되기를 면제한 학칙 부칙(2025.12.17.) 제2조와 문구가 맞지 않습니다.
- `grad-major-credits`: 학칙 [별표 6]과 학사정보 2025·2026학번 표는 복수전공 45학점(참빛인재대학 39, 건축학과 99), 부전공 21학점(행정학과 포함)으로 적지만, Daple은 공학계열 대상 복수전공 54학점, 법학부 36학점, 행정학과 부전공 30학점입니다. 마이크로전공도 공개 자료는 15학점이나 Daple에는 지능형로봇학과 12학점, 글로벌지속가능융합학과 9학점 과정이 있습니다.
- `grad-deferral-eligibility`: 교육지원팀 안내 페이지와 2018년 FAQ는 교직과목 미이수도 졸업연기 사유로 적고 있습니다. 그러나 현행 시행세칙 제33조의2(2026.2.11. 개정)에는 다전공 미이수와 교환학생 두 가지만 남아 있고, 학칙의 교직과정 조항(제47조)도 삭제되었습니다. 신청 시기도 FAQ는 '학기 초', 안내 페이지는 '개강 후~중간고사 개시일 이전'으로 표현이 다릅니다.
- `grad-deferral-tuition`: 부분 등록금 계산 기준이 다릅니다. 시행세칙은 '당해 학기 수업료', 재무팀 FAQ(2004년)는 '소속학과(부)의 4학년 수업료'를 기준으로 적고 있습니다.

전체 78개 중 28개만 옮겼습니다. 나머지는 `faq.json`에서 `disagreement`가 비어 있지 않은 항목입니다.

## rules/*.json과 비교한 결과 (별표 HWP 기준)

`rules_tables.json`의 `crosscheck`에 전체가 있습니다. `rules/*.json`은 고치지 않았습니다. 고칠지 판단할 때 아래를 보세요.

Claude 비교는 별표와 rules JSON 발췌만 보고 했습니다. 학칙 본문의 부칙까지 놓고 다시 본 결과를 함께 적습니다.

**확인됨 (rules JSON 값이 별표와 같음)**
- 2025·2026학번 단과대학별 표: 심화 70, 주전공 45, 복수 45, 부 21, 연계 30~51, 학생설계 24, 마이크로 15, 졸업 133(전정·인융·공대·자연)/130(인사·정법·경영).
- 2026학번 교양: AI리터러시 3 + 균형 30(9개 영역 중 4개 이상, 계열별 지정 영역) = 33.
- 건축학과(5년제) 전 연도 수치, 참빛인재대학 2024~2026(주전공 45, 다전공 이수 시 39), 지능형로봇학과 2022학번~ 부전공 24.
- 2003~2016학년도 기준표, 2019·2020~2023 주요 학과 수치(행정학과 부전공 제외).
- 연계전공 26개 목록과 학점(사회복지학 51, 나머지 30).

**고칠 것 (별표가 rules JSON과 다름)**
- 행정학과 부전공: 별표는 2017~2024학번 모두 21학점. JSON은 30(2019만 web-info11 21과 충돌로 표시). 별표 기준이면 JSON의 30은 틀립니다.
- 2024학번 동북아문화산업학부 주전공(단일전공): 별표 60, JSON 66(web-info12). web-info11도 60이라 60 쪽이 둘입니다.
- 공학계열 기초교양 상한: 별표 27학점 이하(2017~2023), JSON 24. 공학 교양 계 상한도 별표 49, JSON 46.
- 균형교양 '3·4학점 인정'은 2026학번부터입니다. 2016~2025학번 표는 '3학점 과목만 인정'. JSON은 연도 구분 없이 3·4학점으로 적었습니다.
- 2026학번 특별전형 교양 면제 각주에는 '만학도 전형'이 빠졌습니다(2016~2025 각주에는 있음). JSON은 2016~2026 공통으로 적었습니다.
- 2016~2024학번 균형교양 제외 강좌에 '실용영어 계열'이 있고, '매치업' 제외는 2024학번부터 명시됩니다.

**더할 것 (JSON에 없음)**
- 연계전공 학위명 26개(`rules_tables.json`의 `linked_majors`). JSON의 '융합소프트웨어 연계전공'은 별표에서 '융합S/W'이고, 학위명은 원문 그대로 '융합소트프웨어학사'(오기로 보임)입니다.
- 2025·2026학번 다전공 의무 예외: 외국인전형, 특성화고 재직자전형, 체육특기자, 편입생, 건축학과.
- 교양교과목 분류(별표2): 3대 중점역량 → 4대 영역 → 교과목군. 표제는 '12개 교과목군'인데 HWP 본문에서 읽히는 것은 11개입니다. 2026학번의 기초학문융합 영역과 AI리터러시는 별표2(2024.12.23. 개정)에 아직 없습니다.

**겉으로는 충돌, 실제로는 JSON이 맞는 것**
- 광운인되기(2016~2025학번): 별표 6의 14항은 '광운인되기를 뺀 나머지 필수교양'을 면제한 앞선 변경이라, 별표만 읽으면 광운인되기가 필수로 남아 보입니다. 학칙 부칙<2025.12.17.> 제2조(2026-03-01 적용)가 2025학년도 이전 입학자의 광운인되기까지 면제했고 bachelor_info12도 같습니다. 그래서 2016~2025학번은 필수교양 없이 입학연도별 총 교양학점만 채우면 되고, JSON의 면제 표기가 현행과 맞습니다. 별표가 부칙을 반영하지 않은 상태입니다.
- 2020~2023·2024학번 교양 구조(필수 13 + 균형 9 / 13 + 18): 별표는 원래 체계이고 JSON은 14항 변경을 적용한 현행 표기입니다. 숫자 차이는 위 '고칠 것'의 기초교양 상한뿐입니다.
- 2017~2019학번 학과별 기초교양 학점과 야간학과 교양 30: 별표에는 근거가 없고 웹 페이지에만 있습니다. 틀렸다는 뜻은 아니고 출처가 웹뿐이라는 뜻입니다.
- 사회복지학 연계전공 45학점 경과조치: 별표는 '2020학년도 이전 신입학생', JSON은 '2019학번까지'. 2020학번이 들어가는지 학과 확인이 필요합니다.

## 바뀌기 쉬운 것과 다시 만들 때

**바뀌기 쉬운 것**
- 장학: 교내장학금 표는 학교 스스로 '2025학년도 기준'이라고 적었고, 금액·선발 기준은 매 학기 공지로 바뀝니다. 국가장학금 일정과 소득구간 기준은 한국장학재단이 해마다 정합니다. 학기마다(2월·8월) 다시 만드는 것이 좋습니다.
- 수강신청·계절학기·정정·포기 날짜: 지식베이스에는 날짜를 넣지 않았습니다(규정은 '매 학기 공지'). 학사일정은 공개 페이지가 POST로 불러와 이번에 읽지 않았습니다.
- 다전공: 신청 기간(2·4·8·10월) 공지마다 마이크로·연계전공 목록과 교육과정이 바뀝니다. 다전공 이수에 관한 내규는 2024~2026년에 7번 개정됐습니다.
- 교육과정: www 학과 '교육과정' 탭은 현행 표 하나만 보여 줍니다. 새 학년도 교육과정이 확정되는 2~3월에 다시 받아야 합니다. 필수과목표 엑셀은 파일명에 연도(must_2026_NN)가 있어 2027년에는 주소가 바뀝니다.
- 학과 개편: 참빛인재대학 → 산업융합대학(2028학번부터), 영어산업학과 → 영어영문학과(2027-03-01), 정보융합학부 → 데이터사이언스학부, 동북아문화산업학부 → 문화산업학부. 개편이 시행되면 학과 이름 검색과 curricula 파일명을 바꿔야 합니다.
- 연락처: 부서 대표번호는 담당 업무표에서 왔습니다. 인사이동이 있으면 업무별 번호가 바뀝니다.
- Daple: 스냅숏은 2026-11-07 하루치입니다. 다전공 신청 기간마다 트랙이 바뀌므로 소유자가 새 스냅숏을 떠 주면 `apply_daple.py`를 다시 돌려야 합니다.
- 셔틀: 위치 안내 페이지의 버스 노선표는 스스로 '2016년 12월 1일자'라고 적혀 있어 오래됐을 수 있습니다.

**다시 만들 때** (모두 `scripts/knowledge/`에서, `KB_WORK`로 작업 폴더 지정)

```sh
export KB_WORK=/path/to/work   # 기본값: 시스템 임시 폴더/kw-knowledge
python discover.py --seed                     # 출처 목록(sources.json) 시작점
python fetch.py --sources --dry-run           # 받을 목록만 보기
python fetch.py --sources                     # 정중하게 받기(UA, 3.5초, robots, GET, 350건 상한)
python discover.py --derive && python fetch.py --sources   # 규정 본문·학과 교육과정 탭·FAQ 글
uv run --frozen --with xlrd python extract.py
CLAUDE="uv run --frozen --with anthropic --with 'botocore[crt]' --with boto3 --with xlrd python"
$CLAUDE build_rules_tables.py --budget 45     # 별표 HWP 3개 → rules_tables.json
$CLAUDE build_curricula.py --budget 45 && $CLAUDE build_curricula.py --korean --budget 45
python build_curricula.py --assemble          # curricula/*.json
$CLAUDE build_faq.py --dry-run                # 범주별 문서 크기
$CLAUDE build_faq.py --budget 45              # 범주마다 작성 + 검토
$CLAUDE build_faq.py --supplement --budget 45 # 2차: 빈 곳 보충과 '기타'
$CLAUDE build_faq.py --audit --budget 45      # 7개 범주 독립 감사(AUDIT_CATEGORIES)
$CLAUDE build_faq.py --crosscheck --budget 45 # 범주 사이 모순·중복 정리
$CLAUDE build_faq.py --audit --only 계절학기 수업·출석 전과·전공배정 학점교류·교환학생 증명서·학생증 병무·예비군 기타 기숙사 --budget 45
$CLAUDE build_faq.py --round3 --budget 56     # 3차: 휴·복학, 등록금 반환, 장학 환수, 출석, 기숙사·도서관·셔틀
$CLAUDE build_faq.py --round4 --budget 87     # 4차: IT·계정, 학생증, 상담, 시설, 진로·취업, 동아리, 수강신청 빈 곳
python build_contacts.py                      # 학과 사무실·교학팀 번호(Claude 없음)
python apply_links.py                         # 링크형 항목에 공식 주소
$CLAUDE apply_daple.py --snapshot <소유자가 뜬 Daple 스냅숏.json> --budget 45   # 다전공 값을 Daple에 맞춤
python build_faq.py --assemble                # faq.json
$CLAUDE eval_search.py --budget 45 --augment  # 새 질문으로 검색 점검, 놓친 질문은 항목에 추가(assemble 뒤에)
uv run --frozen python validate.py            # 스키마·출처·인용·개인 이름 점검
uv run --frozen pytest tests/test_knowledge.py
```

- 모든 Claude 호출은 지출 장부에 기록됩니다. 호출 전에 남은 예산(`--budget`에서 장부상 'knowledge' 지출을 뺀 값)이 0.5달러 이하면 멈춥니다.
- 규정이 개정되면 `lawFullView.do?SEQ=…`에서 새 `SEQ_HISTORY`를 찾아야 본문을 받을 수 있습니다(`discover.py --derive`가 함).
- 새 학년도에는 `discover.py`의 `MUST_XLS` 이름(must_2026_NN)과 `build_curricula.py`의 `CURRENT_YEAR`를 바꿉니다.
