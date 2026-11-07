# KLAS 학생 메뉴 조사 (2026-11-07)

운영자 계정으로 로그인한 KLAS에서 메뉴 64개와, 아직 쓰지 않는 메뉴가 부르는 JSON 응답의 **필드 이름**을 확인했습니다. 값은 기록하지 않았습니다. 화면이 부르는 조회용 엔드포인트만 호출했고, 신청·취소·저장 엔드포인트(`*Insert.do`, `*Cancel.do`, `*Cancle.do`, `CompnoDayOptCheck.do` 등)는 부르지 않았습니다.

## 이미 쓰는 메뉴

| 메뉴 | 쓰는 곳 |
|---|---|
| 수업시간표, 학습지원실(과제·퀴즈·온라인시험·팀플·토론·설문·게시판·강의종합), 온라인 강의 진도 | 기존 도구 전부 |
| 출석관리(KW출첵) | `get_attendance` |
| 강의계획서 조회 | `get_syllabus`, `get_exam_info` |
| 수강/성적 조회, 석차 조회 | `get_grades` |
| 교양(필수, 균형) 이수현황 | `get_graduation_progress` |
| 장학 조회 | `get_scholarships`(수혜 내역), 학사 기한(장학 신청 기간) |
| 취득학점포기 신청 | 학사 기한(신청 기간) |
| 수업평가 | `get_course_evaluation` |
| 졸업 사정(메뉴 밖 `ext/grdtn`) | `get_graduation_progress.official_check` |

## 아직 안 쓰는 메뉴 중 쓸 만한 것

| 메뉴 | 엔드포인트 (POST, 본문 없음) | 주는 것 | 학생 질문 |
|---|---|---|---|
| 학적관리 > 휴복학 신청 | `/std/hak/hakjuk/TmpabssklGetHakjuk.do` | 일반휴학·일반휴학연기·군입휴학·군입휴학연기·일반복학 등 유형별 지금 신청 가능 여부와 신청 기간·시간(`commitStr0N`, `commentStr0N`, HTML 섞임) | "휴학 신청 언제야?", "지금 군휴학 돼?" |
| 〃 | `/std/hak/hakjuk/TmpabssklStatu.do` | 내 휴·복학 신청 내역(`statu[]`: 구분·신청일·처리 상태·처리일·비고), 학적 상태, 복학 예정일 | "휴학 신청 처리됐어?", "복학 언제야?" |
| 학적관리 > 복수/부/심화전공 신청/조회 | `/std/hak/hakjuk/CompnoApplyResult.do` | 내 다전공 신청·결과(`resultList[]`: 유형·전공명·신청일·이수 여부) | 다전공 시뮬레이션이 학생이 이름을 대지 않아도 신청한 전공으로 계산 |
| 학적관리 > 마이크로전공, 연계전공 | `/std/hak/hakjuk/MicroMajorResult.do`, `CntcSbjectResult.do` | 같은 모양 | 〃 |
| 등록관리 > 등록금 고지서 | `/std/hak/erollmnt/TutionNtInfo.do` | 이번 학기 고지 금액 항목(입학금·수업료·장학 감면·기타), 납부 기간 | "등록금 얼마 내야 돼? 언제까지?", "장학금이 등록금에서 빠지는 거야?" |
| 등록관리 > 이전학기 등록내역 | `/std/hak/erollmnt/TutionEduList.do` | 학기별 등록(납부) 날짜 | "몇 학기 등록했지?"(졸업 등록 학기 요건) |
| 학습결과 > 어학성적 조회 | `/std/cps/inqire/ToeicInfoStd.do` | 어학 졸업요건 대상·통과 여부, 시험명·점수·날짜 | 졸업 시뮬레이션의 어학 항목 |
| 수강관리 > 수강포기 신청 | 페이지 HTML(`/std/cps/atnlc/GiveupStdPage.do`) | 기간이 아니면 "수강포기 기간이 아닙니다" | "드랍 지금 돼?" |

## 넣지 않을 필드

- 모든 `hakjukMap`: 이름(`kname`), 학번(`hakbun`), 지도교수 이름·이메일(`jidoName`, `jidoEmail`)
- 등록금 고지서: 가상계좌(`cyberAccount`), `hashData`
- 상담관리 > 소속학과 교수 상담시간(`/std/hak/cnslt/CnsltTimeStdList.do`): 교수 295명의 이메일·휴대전화(`hpNo`)·연구실 전화가 함께 옵니다. 쓰더라도 내 수강 과목 교수의 상담 시간(`bigo`)과 연구실 전화만, 휴대전화는 절대 넣지 않습니다. 운영자 결정이 필요합니다.

## 쓰지 않을 메뉴

포트폴리오, 광운역량이력서, 조교 메뉴, 교직적성검사, 모바일학생증, 장소사용 게시판, 수학계획서, 공학인증 점검(해당 학생만, 운영자 계정은 빈 응답), CDP 출석·상담내역(운영자 계정은 빈 목록), 일정관리(개인 일정, 요청 형식 미확인).
