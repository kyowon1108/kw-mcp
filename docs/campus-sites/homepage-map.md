# 광운대 홈페이지와 연결 사이트 지도

조사일 2026-11-07. www.kw.ac.kr의 메뉴·사이트맵·푸터에서 출발해, 연결된 학교 사이트의 첫 화면과 공지 목록 1페이지만 봤습니다. 개별 글은 열지 않았습니다.

## 요약

- 게시판 **127개**를 정리했습니다. 지금 수집 중 30개, 로드맵에는 있지만 수집하지 않는 곳 48개, **로드맵과 수집기 어디에도 없는 곳 49개**입니다.
- 새로 찾은 49개 가운데 최근 두 달 안에 글이 올라온 공지 게시판은 9개입니다. 대부분 사업단·국제·대학원 쪽이고, 학과 공지 게시판은 로드맵이 거의 다 잡아 두었습니다.
- 새 공지 게시판 대부분(반도체특성화대학사업단, 한국어교육센터, HUSS 사업단, 인권센터 등)은 kw-campus `deptboards`의 A 그룹 파서(`BoardMode=view&UID`)로 저장한 HTML을 그대로 읽었습니다. 파서를 새로 만들 필요는 없고, `BOARDS`에 행을 더하고 robots 기록을 남기면 됩니다.
- **로드맵과 어긋나는 사실이 둘 있습니다.** 중앙도서관(kupis)과 교수학습센터(ontl)의 robots.txt가 둘 다 `Disallow: /`입니다. 로드맵 4절은 두 곳을 공개 데이터 소스로 적어 두었습니다.
- 로드맵 기록보다 새 글이 있는 곳: 참빛인재대학 대학공지(10-16 → 11-06). 반대로 학생상담실 공지는 2025-05-09 이후 새 글이 없습니다.
- 요청은 **244회**(robots.txt 56회 포함)입니다. 같은 서버(IP)에 보낸 요청 사이의 가장 짧은 간격은 3.51초입니다. 403·429·CAPTCHA는 없었습니다.

## 1. 조사 방법

- User-Agent `kw-campus-research (contact kyowon1108@gmail.com)`, GET만 썼습니다. 로그인·폼·검색은 하지 않았습니다.
- 같은 IP를 쓰는 호스트는 한 서버로 묶어 3.5초 이상 간격을 두었습니다. robots.txt는 호스트마다 먼저 받고, Allow/Disallow는 RFC 9309의 최장 일치로 판단했습니다. Crawl-delay가 있으면 그 값을 따랐습니다(job.kw 10초, kutec 600초).
- 학과 사이트 27개 호스트는 kw-campus `politeness.ROBOTS`에 어제(2026-11-06) 손으로 확인한 기록이 있어 그 기록을 썼습니다. 이 호스트들의 robots.txt는 다시 받지 않았습니다.
- kupis.kw.ac.kr과 math.kw.ac.kr은 인증서 체인이 불완전해 TLS 검증을 끄고 요청했습니다(kupis는 robots.txt 1회, math는 첫 화면과 robots.txt).
- 실수 하나: http의 robots.txt가 https로 302된 호스트(iacf, compro, kwmooc, icerink, math)는 처음에 '파일 없음'으로 처리하고 페이지를 받았습니다. 끝난 뒤 https의 robots.txt를 따로 받아 보니 모두 파일이 없거나(302·404) 전체 허용(kwmooc)이라 어긴 곳은 없었습니다.
- '최신 글' 열의 근거: **목록** = 오늘 목록 1페이지를 직접 받음, **첫 화면** = 사이트 첫 화면 위젯에서 본 날짜, **로드맵** = 2026-11-05 조사 기록을 그대로 옮김.

## 2. www.kw.ac.kr 구조

### 2-1. 전체 메뉴(GNB) 요약

GNB는 대분류 6개입니다. 각 하위 메뉴의 3~4단계는 페이지 왼쪽 메뉴(LNB)에서 채웠습니다. 전체 트리는 `homepage-map.json`의 `www.gnb`에 있습니다.

- **광운**
  - 광운소개: 연혁, 창학정신 및 교육이념, 대학발전계획, 광운상징, 광운학원
  - 총장실: 총장인사말, 프로필, 역대총장
  - 대학현황: 현황, 조직 및 기구표, 예결산공고, 대학규정, 대학요람, 자매결연대학, 등록금심의위원회, 기금운용심의회, 대학평의원회, 업무추진비, 연간기부금 모금액 및 활용실적 명세서, 적립금 적립 및 사용 현황, 청렴행정
  - 총동문회
  - 광운캠퍼스안내: 캠퍼스투어, 위치 및 교통안내, 조회서비스
  - 기관소개: 총장 직속 기구, 교무행정부총장 직속 기구, 대외부총장 직속 기구, 행정본부, 부속기관, 부설기관, 부속교육기관, 부설연구기관, 기타기관
- **입학**
  - 대학 ↗
  - 대학원 ↗
  - 환경대학원 ↗
  - 경영대학원 ↗
  - 스마트융합대학원 ↗
  - 교육대학원 ↗
  - 상담복지정책대학원 ↗
  - 건설법무대학원 ↗
  - 정보과학교육원 ↗
- **교육**
  - 대학: 한눈에 보는 대학, 전자정보공과대학, 인공지능융합대학, 공과대학, 자연과학대학, 인문사회과학대학, 정책법학대학, 경영대학, 참빛인재대학, 인제니움대학
  - 대학원 ↗: 일반대학원
  - 특수대학원: 환경대학원, 경영대학원, 스마트융합대학원, 교육대학원, 상담복지정책대학원, 건설법무대학원
- **취업**
  - 경력개발팀 ↗
  - 현장실습지원팀 ↗
  - KW-IPP공동훈련센터 ↗
  - 학생포트폴리오 & 취업통계 시스템 ↗
  - 취업게시판 ↗
- **연구/산학** (http://iacf.kw.ac.kr/)
- **KW-LIFE**
  - 학사안내: 학사일정, 학사정보
  - 장학안내: 학부 장학안내, 교내장학금, 교외장학금, 장학재단 예우
  - 제증명안내: 제증명안내, 학생증발급 안내, 국제학생증 발급 안내
  - 병무안내: 병무상담, 병사업무안내
  - 학생자치활동: 학생자치기구, 중앙동아리, 졸업준비위원회, 비마응원단, 홍보대사 비마랑, ROTC, 로봇게임단 로:빛, 사회봉사단, 입학전형홍보대사 광운알리미
  - 복지 편의시설: 건강생활지원, 문화학습지원, 전산멀티미디어지원, Wi-Fi 이용 안내, 편의시설안내, 장소 사용(신청)안내, 식단안내
  - 알림광장: 코로나19, 공지사항, 자유게시판, 취업정보, 자료실
  - 광운미디어 ↗: 포커스, 광운소식, 뉴스레터 광운Story, 브로슈어, 홍보아이템 제보, 최신연구성과, 세계2%과학자, AI 활용 수업 사례, 지금 광운대, +1 Campaign 안내
  - 학부모서비스

- 사이트맵 페이지(`/ko/info/sitemap.jsp`)는 상위 묶음 7개만 보여 줍니다. 하위 메뉴는 GNB가 더 자세합니다.
- '연구/산학'은 하위 메뉴 없이 iacf.kw.ac.kr로 바로 갑니다. '취업' 대분류의 링크는 입학 사이트(iphak)로 잘못 걸려 있습니다(하위 메뉴는 정상).

### 2-2. 첫 화면과 머리글·푸터

- **머리글**: KLAS 종합정보서비스, 발전기금, WEB-MAIL, SITEMAP, 로그인, Search
- **첫 화면 공지 탭**: 전체·일반·학사·취업·등록/장학·봉사·국제. 모두 메인 공지(`notice.jsp?srCategoryId=`)와 취업게시판으로 연결됩니다.
- **첫 화면 서비스 바로가기**: KLAS, 중앙도서관, KW 출첵, 교육혁신원·참빛인재·KW MOOC, 글로벌전략팀·국제교육원, 광운대신문·광운소식·광운story·미디어 속 광운, 발전기금, KW COMMONS, 경력개발팀·현장실습지원팀·KW-IPP·학생포폴, 창업, 교내전화번호·캠퍼스투어, 학부모 서비스·인터넷증명·학사정보·학사일정·타교생 강의계획서
- **푸터 '관련 기관' 목록**: 51개 링크. 학교 기관, 직원 업무 시스템(전자결재·자산관리·구매 등), 학교가 위탁 운영하는 지역 청소년센터 6곳이 한 목록에 섞여 있습니다.
- **SNS**: 대학 Facebook·Instagram·YouTube·네이버 블로그, KWBC Facebook·YouTube.

### 2-3. 단과대·학과 → 홈페이지

| 단과대 | 단과대 사이트 | 학과(전공) → 사이트 |
|---|---|---|
| 전자정보공과대학 | https://ei.kw.ac.kr/ | 전자공학과 → https://ee.kw.ac.kr/; 전자통신공학과 → https://elcomm.kw.ac.kr/; 전자융합공학과 → https://radiowave.kw.ac.kr/; 전기공학과 → https://electric.kw.ac.kr/; 전자재료공학과 → https://snme.kw.ac.kr/; 반도체시스템공학부 → https://semicon.kw.ac.kr/ |
| 인공지능융합대학 | https://aicon.kw.ac.kr/ | 컴퓨터정보공학부 → https://ce.kw.ac.kr/; 소프트웨어학부 → https://cs.kw.ac.kr/; 정보융합학부 → https://ic.kw.ac.kr/; 로봇학부 AI로봇전공 → https://cni.kw.ac.kr/; 로봇학부 정보제어·지능시스템전공 → https://cni.kw.ac.kr/; 지능형로봇학과 → http://share.kw.ac.kr/ |
| 공과대학 | 없음 | 건축공학과 → http://archi.kw.ac.kr/; 화학공학과 → https://chemng.kw.ac.kr/; 환경공학과 → https://www.envkw.com; 건축학과 → https://www.kwuarchitecture.com/ |
| 자연과학대학 | 없음 | 수학과 → 없음; 전자바이오물리학과 → 없음; 화학과 → http://chem.kw.ac.kr; 스포츠융합과학과 → https://sports.kw.ac.kr/; 정보콘텐츠학과(야) → 없음 |
| 인문사회과학대학 | http://chss.kw.ac.kr/ | 국어국문학과 → https://korean.kw.ac.kr/; 영어산업학과 → https://english.kw.ac.kr/; 미디어커뮤니케이션학부(미디어엔터테인먼트·인터랙티브미디어커뮤니케이션·전략커뮤니케이션전공) → https://www.kwmedia.info/; 산업심리학과 → https://psy.kw.ac.kr/; 동북아문화산업학부(문화교류·문화콘텐츠개발전공) → https://dnaci.kw.ac.kr/ |
| 정책법학대학 | 없음 | 행정학과 → https://kwpa.kw.ac.kr/; 법학부(일반법학·기업법무·과학기술법무·국제법무(~2023학번)전공) → https://law.kw.ac.kr/; 국제학부 국제지역전공 → https://kwdois.my.canva.site; 자산관리학과(야) → 없음 |
| 경영대학 | http://biz.kw.ac.kr/ | 경영학부(경영학·빅데이터경영전공) → https://biz.kw.ac.kr/; 국제통상학부(국제금융·글로벌비즈니스전공) → https://biz.kw.ac.kr/ |
| 참빛인재대학 | http://kwlife.kw.ac.kr/ | 금융부동산법무학과 → http://kwlaw.kw.ac.kr/; 게임콘텐츠학과 → http://kwgame.kw.ac.kr/; 스마트전기전자학과 → http://kwsee.kw.ac.kr/ (www 소개 페이지는 kwlife로 연결); 스포츠상담재활학과 → http://kwsports.kw.ac.kr/ |
| 인제니움대학 | https://ingenium.kw.ac.kr/ | 자율전공학부 → https://liberal.kw.ac.kr/ |

- 학과 소개 페이지(`/ko/univ/depart_intro.jsp`)에 홈페이지 링크가 없는 곳: 수학과, 전자바이오물리학과, 정보콘텐츠학과(야), 자산관리학과(야). 로드맵의 '공개 게시판 없음'과 같습니다.
- math.kw.ac.kr은 DNS에는 있지만 2021-04-30에 종료된 학교 웹호스팅 안내 페이지입니다. 수학과 사이트가 아닙니다.

**대학원**: 일반대학원 → https://grad.kw.ac.kr/; 환경대학원 → https://gses.kw.ac.kr/; 경영대학원 → http://gsba.kw.ac.kr (404로 넘어감); 스마트융합대학원 → https://compro.kw.ac.kr/; 교육대학원 → https://gedu.kw.ac.kr/new2017/; 상담복지정책대학원 → https://isw.kw.ac.kr/; 건설법무대학원 → https://kwcl.kw.ac.kr/; 정보과학교육원(부속교육기관) → http://iit.kw.ac.kr/

### 2-4. 행정부서·부속기관 → 홈페이지

기관소개(`/ko/department/`)의 부서 페이지 중 '홈페이지 바로가기'가 있는 곳만 적었습니다. 없는 부서는 www 소개 페이지가 전부입니다.

| 분류 | 부서 → 사이트 |
|---|---|
| 총장 직속 기구 | 교육혁신원(성과관리팀) → https://icei.kw.ac.kr/; 인권센터 인권·성평등상담실 → https://humanrights.kw.ac.kr/; 인권센터 학생상담실 → https://sangdam.kw.ac.kr/ (사이트 없음: 비서실, 인권센터 장애학생지원실, 공간혁신본부(자산개발팀)) |
| 교무행정부총장 직속 기구 | – (사이트 없음: 교무행정부총장, 감사실) |
| 대외부총장 직속 기구 | 홍보기획실 → https://news.kw.ac.kr/ (광운미디어, 첫 화면에서 연결); 발전기금본부 → https://fund.kw.ac.kr/ (머리글에서 연결) (사이트 없음: 대외부총장) |
| 행정본부 | 기획처 대학혁신사업단 → https://inno.kw.ac.kr/; 학생처 경력개발팀 → https://job.kw.ac.kr/; 학생처 현장실습지원팀 → https://internship.kw.ac.kr/; 학생처 KW-IPP공동훈련센터 → http://ipp.kw.ac.kr/; 입학처 입학관리팀 → https://iphak.kw.ac.kr/; 국제처 글로벌전략팀 → https://oia.kw.ac.kr/; 국제처 한국어교육센터 → http://kwiie.kw.ac.kr (사이트 없음: 기획처 전략기획팀, 기획처 예산팀, 교무처 교수지원팀, 교무처 교육지원팀, 학생처 학생복지팀, 학생처 체육지원팀, 입학처 입학사정관실, 총무처 총무팀, 총무처 재무팀, 관리처 시설안전관리팀, 정보통신처 정보운영팀, 정보통신처 통신운영팀) |
| 부속기관 | 중앙도서관 → http://kupis.kw.ac.kr/; 동해문화예술관 → http://dac.kw.ac.kr/main/main.php; 광운대 신문사 → https://kwnews.kw.ac.kr/ (첫 화면에서 연결); 생활관 → https://kw.happydorm.or.kr/ (사이트 없음: 글로컬교육센터) |
| 부설기관 | 산학협력단(산학사업·연구지원·연구진흥·경영관리팀) → http://iacf.kw.ac.kr/ (연구관리 n-kuris.kw.ac.kr) (사이트 없음: 기술지주회사) |
| 부속교육기관 | 정보과학교육원 → http://iit.kw.ac.kr/ |
| 부설연구기관 | 나노소자응용연구소 → http://www.ndac.re.kr/; kutec → http://kutec.kw.ac.kr/; 국가인적자원개발센터 → http://kwhrd.com/ |
| 기타기관 | 학생군사교육단(ROTC) → https://instagram.com/kw.142rotc_official (KW-LIFE 메뉴는 http://142rotc.kw.ac.kr/); 지능형로봇혁신융합대학사업단 → http://share.kw.ac.kr; 인문사회융합인재양성사업단 → https://huss.kw.ac.kr/; 반도체특성화대학사업단 → https://semi.kw.ac.kr/; 디지털경제인재양성사업단 → https://hussde.kw.ac.kr (사이트 없음: 예비군 연대, SW중심대학사업단(푸터에만 있음)) |

### 2-5. www 안에서 로그인이 필요한 곳, 깨진 링크

- 종합 Q&A, 자료실, 지금 광운대, 자유게시판은 열면 KLAS 로그인 화면으로 넘어갑니다.
- 푸터 SW중심대학사업단: https://www.kw.ac.kr/ko/department/affiliated_etc05.jsp → HTTP 200이지만 '요청하신 페이지가 존재하지 않습니다' 페이지
- GNB·사이트맵 경영대학원: http://gsba.kw.ac.kr/main/main.php → 302 → http://i-web.kr/404.html
- 푸터 대학혁신사업단: https://performance.kw.ac.kr/main.do → 읽기 타임아웃(15초). 현재 사이트는 inno.kw.ac.kr
- 푸터 교직과정, KW-LIFE ROTC: https://teacher.kw.ac.kr/, http://142rotc.kw.ac.kr/ → robots.txt 연결 타임아웃(로드맵 때와 같음)

### 2-6. 연결 사이트 목록

| 호스트 | 이름 | 분류 | 어디서 연결 | robots.txt | 요청 | 메모 |
|---|---|---|---|---|---|---|
| klas.kw.ac.kr | KLAS 종합정보서비스 | 학사 포털 | 머리글, 첫 화면 서비스 | 요청하지 않음 | 0 | 로그인. 요청하지 않음 |
| wmail.kw.ac.kr | 웹메일 | 학사 포털 | 머리글 | 요청하지 않음 | 0 | 로그인. 요청하지 않음 |
| kwcommons.kw.ac.kr | KW COMMONS | 학사 포털 | 첫 화면 서비스 | 요청하지 않음 | 0 | 로그인 페이지로 바로 연결. 요청하지 않음 |
| rule.kw.ac.kr | 대학규정 | 학사 포털 | GNB 광운>대학현황 | 요청하지 않음 | 0 | 규정 열람. 이번에는 요청하지 않음(로드맵에서 확인함) |
| kwmooc.kw.ac.kr | KW MOOC | 교육 | 첫 화면 서비스, 배너 | User-agent: * / Disallow: | 5 | 공지 목록은 자바스크립트(/api/v1) |
| mooc.kw.ac.kr | 원격교육지원센터(광운MOOC센터) | 교육 | 푸터 | 파일 없음(404) | 3 | WordPress. 공지 목록이 HTML에 없음 |
| ontl.kw.ac.kr | 교수학습센터 | 교육 | 푸터 | User-agent: * / Disallow: / / Disallow: /shop.tail.php / Disallow: /shop.head.php | 1 | robots.txt Disallow: / → 요청하지 않음 |
| icei.kw.ac.kr | 교육혁신원 | 교육 | 첫 화면 서비스, 기관소개 | 파일 없음(404) | 3 |  |
| itplusinfo.kw.ac.kr | 참빛인재(비교과) | 교육 | 첫 화면 서비스 | User-agent: * / Disallow: / | 1 | robots.txt Disallow: / → 요청하지 않음. SSO |
| dream.kw.ac.kr | 공학교육혁신센터 드림캐처 | 교육 | (로드맵) | 파일 없음(404) | 2 | 공지 2021년 이후 없음 |
| iphak.kw.ac.kr | 입학처 | 입학 | GNB 입학, 사이트맵, 학부모서비스 | 파일 없음(302, redirect: https://iphak.kw.ac.kr/error_c.php) | 3 |  |
| grad.kw.ac.kr | 일반대학원 | 대학원 | GNB 입학·교육, 사이트맵 | 파일 없음(404) | 3 |  |
| gses.kw.ac.kr | 환경대학원 | 대학원 | GNB 입학, 사이트맵 | User-agent: * / Allow: / | 4 | 메뉴가 자바스크립트 |
| gsba.kw.ac.kr | 경영대학원 | 대학원 | GNB 입학, 사이트맵 | User-agent: * / Allow: / | 2 | i-web.kr/404.html로 넘어감(링크 깨짐) |
| compro.kw.ac.kr | 스마트융합대학원 | 대학원 | GNB 입학, 사이트맵 | http는 https로 302, https는 302(파일 없음) | 4 |  |
| gedu.kw.ac.kr | 교육대학원 (+ /Cham-Bit 심리건강증진센터) | 대학원 | GNB 입학, 사이트맵, 푸터 | 파일 없음(404) | 5 |  |
| isw.kw.ac.kr | 상담복지정책대학원 | 대학원 | GNB 입학, 사이트맵 | User-agent: * / Allow:/ | 4 |  |
| kwcl.kw.ac.kr | 건설법무대학원 | 대학원 | GNB 입학, 사이트맵 | User-agent: * / Allow: / | 2 |  |
| iit.kw.ac.kr | 정보과학교육원 | 대학원 | GNB 입학, 사이트맵, 푸터, 기관소개 | 파일 없음(302, redirect: https://iit.kw.ac.kr/robots.txt) | 3 | TLS 인증서 체인 오류로 받지 못함 |
| job.kw.ac.kr | 경력개발팀(인재개발원) | 취업 | GNB 취업, 사이트맵, 첫 화면, 푸터 | User-agent: * / Disallow: /recommend/ / Disallow: /mobile/recommend/ / Disallow: /internship/ / Disallow: /job/ / Disallow: /give/story.php / Disallow: /notice/news.php / Crawl-delay: 10 | 3 | robots: /recommend/ /job/ 등 Disallow, Crawl-delay 10 |
| internship.kw.ac.kr | 현장실습지원팀 | 취업 | GNB 취업, 첫 화면, 기관소개 | User-agent: * / Disallow: / / allow: /index.do | 2 | robots: /index.do만 허용 |
| ipp.kw.ac.kr | KW-IPP공동훈련센터 | 취업 | GNB 취업, 첫 화면, 푸터 | 파일 없음(404) | 4 | 목록은 AJAX |
| kwjob.kw.ac.kr | 학생포트폴리오 & 취업통계시스템 | 취업 | GNB 취업, 첫 화면, 푸터 | 요청하지 않음 | 0 | 로그인. 요청하지 않음 |
| oia.kw.ac.kr | 국제처 글로벌전략팀 | 국제 | 첫 화면 서비스, 학부모서비스, 기관소개 | 파일 없음(404) | 4 |  |
| kwiie.kw.ac.kr | 국제처 한국어교육센터 (kile.kw.ac.kr → 여기) | 국제 | 첫 화면 서비스, 푸터(국제교육원), 기관소개 | 파일 없음(404) | 4 |  |
| sangdam.kw.ac.kr | 학생상담실 | 학생지원 | 기관소개, 학부모서비스('인권센터'라는 이름으로) | 파일 없음(302, redirect: http://sangdam.kw.ac.kr/error/error.html) | 3 |  |
| humanrights.kw.ac.kr | 인권센터 인권·성평등상담실 | 학생지원 | 기관소개 | 파일 없음(302, redirect: http://humanrights.kw.ac.kr/error/error.html) | 3 |  |
| kw.happydorm.or.kr | 행복기숙사(생활관) | 학생지원 | 첫 화면 배너, 기관소개(생활관) | 파일 없음(404) | 3 | 외부 업체 운영, 목록은 JS POST |
| kupis.kw.ac.kr | 중앙도서관 | 학생지원 | 첫 화면 서비스, 푸터, 기관소개 | User-agent: * / Disallow: / | 2 | robots.txt Disallow: / (인증서 체인 문제로 검증 끄고 robots만 받음) |
| dac.kw.ac.kr | 동해문화예술관(대강당) | 학생지원 | KW-LIFE 복지편의시설, 푸터, 기관소개 | User-agent: * / Allow: / / Disallow:/adminok | 2 | 공지 게시판 없음(공연·자료실) |
| icerink.kw.ac.kr | 아이스링크 | 학생지원 | KW-LIFE 복지편의시설, 푸터 | http는 https로 302, https는 404(파일 없음) | 4 | 첫 화면이 /intro/intro.php로 넘어감. 게시판 확인 안 함 |
| www.kwu-studentcouncil.co.kr | 총학생회 이음 | 학생자치 | KW-LIFE 학생자치기구 | 파일 없음(404) | 2 |  |
| 142rotc.kw.ac.kr | 학생군사교육단 | 학생자치 | KW-LIFE 학생자치활동 LNB | 받지 못함(타임아웃·TLS) | 1 | robots.txt 요청이 타임아웃 → 요청하지 않음 |
| teacher.kw.ac.kr | 교직과정 | 교육 | 푸터 | 받지 못함(타임아웃·TLS) | 1 | robots.txt 요청이 타임아웃 → 요청하지 않음 |
| coms.kw.ac.kr | 중앙동아리 사이트 | 학생자치 | 중앙동아리 페이지 | 요청하지 않음 | 0 | 요청하지 않음 |
| inno.kw.ac.kr | 대학혁신사업단 | 사업단 | 기관소개(행정본부) | User-agent: * / Allow: / / Sitemap: https://inno.kw.ac.kr/sitemap.xml | 3 |  |
| performance.kw.ac.kr | 대학혁신사업단 옛 사이트 | 사업단 | 푸터 | User-agent: * / Disallow: / / Allow: /main.do | 2 | robots가 /main.do만 허용. 요청이 15초 타임아웃 |
| huss.kw.ac.kr | 인문사회융합인재양성사업단 | 사업단 | 기관소개(기타기관) | User-agent: * / Allow: / | 4 |  |
| hussde.kw.ac.kr | 디지털경제인재양성사업단 | 사업단 | 기관소개(기타기관) | User-agent: * / Allow: / | 3 | iframe+JS. GET으로 메뉴가 보이지 않음 |
| semi.kw.ac.kr | 반도체특성화대학사업단 | 사업단 | 기관소개(기타기관) | User-agent: * / Allow: / | 3 |  |
| share.kw.ac.kr | 지능형로봇혁신융합대학사업단(지능형로봇학과) | 사업단 | 기관소개(기타기관), 학과 소개 | 파일 없음(404) | 3 |  |
| sw.kw.ac.kr | 인공지능융합대학(같은 서버의 다른 이름) | 단과대 | (링크 없음, DNS로 확인) | 파일 없음(404) | 3 | aicon과 같은 페이지 |
| startup.kw.ac.kr | 창업지원단 | 창업·산학 | 푸터 | User-agent: * / Allow: / | 4 |  |
| iacf.kw.ac.kr | 산학협력단 | 창업·산학 | GNB 연구/산학, 첫 화면(창업), 푸터, 기관소개 | http는 https로 302, https는 302(파일 없음) | 4 |  |
| kwcampustown.startup-plus.kr | 캠퍼스타운 사업단 | 창업·산학 | (로드맵, 메인 공지 작성 부서) | User-agent: * / Allow: / / Disallow: /sp-admin / Sitemap: https://www.startup-plus.kr/sitemap.xml / Disallow: /index.do / Allow: /default.do / Disallow: /project/ / Disallow: /tech/ / Disallow: /renta | 4 | startup-plus 플랫폼, 목록 JS |
| fund.kw.ac.kr | 발전기금 | 기타 | 머리글, 첫 화면, 푸터 | User-agent: * / Disallow: /recommend/ / Disallow: /mobile/recommend/ / Disallow: /internship/ / Disallow: /job/ / Disallow: /give/story.php / Disallow: /notice/news.php / Crawl-delay: 10 | 3 |  |
| news.kw.ac.kr | 광운미디어(광운소식·광운Story·브로슈어) | 홍보 | GNB KW-LIFE>광운미디어, 첫 화면 | 파일 없음(302, redirect: http://news.kw.ac.kr/error/error.html) | 2 |  |
| kwnews.kw.ac.kr | 광운대신문 | 홍보 | 첫 화면 서비스 | User-agent: * / Disallow: /admin/ / Sitemap: http://kwnews.kw.ac.kr/sitemap.xml | 3 |  |
| www.ndac.re.kr | 나노소자응용연구소 | 연구 | 기관소개(부설연구기관) | User-agent: * / Allow: / / Sitemap: http://www.ndac.re.kr/sitemap.xml | 2 |  |
| kutec.kw.ac.kr | 부설연구기관 kutec | 연구 | 기관소개(부설연구기관) | User-agent: bingbot / Disallow: / / User-agent: * / Disallow: /adm / Disallow: /adm_w / Disallow: /*.pdf$ / Disallow: /*.gif$ / Disallow: /*.jpg$ / Disallow: /*.png$ / Disallow: /data / Disallow: /css | 1 | robots Crawl-delay 600 → robots만 받고 첫 화면은 요청하지 않음 |
| www.kwhrd.com | 국가인적자원개발센터 | 연구 | 기관소개, 푸터 | User-agent: * / Content-Signal: search=yes,ai-train=no,use=reference / Allow: / / User-agent: Amazonbot / Disallow: / / User-agent: Applebot-Extended / Disallow: / / User-agent: Bytespider / Disallow: | 3 | 게시판 링크를 찾지 못함 |
| math.kw.ac.kr | (링크 없음) 옛 웹호스팅 | 기타 | DNS로만 확인 | http는 https로 302, https는 404(파일 없음) | 5 | 2021-04-30 웹호스팅 종료 안내 페이지 |

- 직원 업무용이라 요청하지 않은 곳: safety.kw.ac.kr(연구실 안전정보망, 로그인), sangjo.kw.ac.kr(교수상조회), nkuris.kw.ac.kr / n-kuris.kw.ac.kr(연구관리, 로그인), jasan.kw.ac.kr(자산관리), gw.kw.ac.kr(전자결재), www.ebiz4u.co.kr(전자구매), kw.mrosystem.com(단가계약), kw.ubob.com(직원 교육), 9011.co.kr/kwu(원격지원)
- 학교 밖 기관(요청 안 함): www.gbiwill.or.kr(강북Iwill센터), www.gb1318.or.kr(강북구청소년상담복지센터), www.nanna.seoul.kr(시립강북청소년센터), www.andyouth.or.kr(시립노원청소년미래진로센터), www.sbyouth.or.kr(시립성북청소년센터), www.cdyouth.or.kr(시립창동청소년센터), academyinfo.go.kr(대학정보공시), www.wa.or.kr(웹접근성 인증), SNS: Facebook·Instagram·YouTube·네이버 블로그, KWBC Facebook·YouTube
- 중앙동아리 페이지의 '홈페이지 바로가기' 48개는 대부분 Instagram 계정입니다. 공지 수집 대상이 아닙니다.

### 2-7. 서버 묶음(속도 제한 단위)

수집기는 호스트가 아니라 IP로 묶어야 합니다. 학과 사이트만이 아니라 지원 부서 사이트도 같은 서버에 있습니다.

- 61.111.8.4 (E1): ei, ee, elcomm, radiowave, electric, snme, semicon, law, job, startup
- 61.111.6.200 (E2): archi, chss, korean, english, psy, dnaci, kwpa, biz + grad, gedu, humanrights, icei, kwcl, kwiie, oia, sangjo
- 211.233.72.248 (E3, 외부 호스팅): aicon(ce, cs, ic, cni, sw), kwlife, kwlaw, kwgame, kwsee, kwsports, ingenium + liberal, fund, huss, inno, kile, news, sangdam, semi, compro
- 114.203.87.122 (E4): chemng, sports + share, isw, dac, icerink
- www.kw.ac.kr과 klas.kw.ac.kr은 같은 IP(223.194.1.180)입니다.

## 3. 게시판 표

열: 최신 글 = 목록 1페이지에서 보인 가장 최근 게시일(고정 글 포함). 근거 = 목록/첫 화면/로드맵. 수집 = 지금 kw-notice·kw-campus가 모으는지. 로드맵 = campus-roadmap.md에 이 게시판이 적혀 있는지.

### 3-1. 본부와 단과대·학과

#### 본부(www.kw.ac.kr)

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 본부 | [공지사항 (분류 0~10: 일반·학사·학생·봉사·등록/장학·입학·시설·병무·외부·국제교류·국제학생)](https://www.kw.ac.kr/ko/life/notice.jsp) | jwxe | 2026-11-07 | 목록 | 활발 | – | O | O | kw-notice가 수집 중. 본부 부서와 일부 단과대 교학팀(자연대·인제니움) 글이 여기에 올라옴 |
| 본부 | [취업정보](https://www.kw.ac.kr/ko/life/job.jsp) | jwxe | 2026-11-06 | 목록 | 활발 | – | O | O | kwcampus.wwwboards가 수집 |
| 본부 | [종합 FAQ](https://www.kw.ac.kr/ko/life/faq.jsp) | jwxe | 2026-08-11 | 목록 | 뜸함 | – | O | – | 수정일 기준으로는 2026-09-15. kwcampus.wwwboards가 수집하지만 로드맵 3절 표에는 없음 |
| 본부 | [포커스 (홍보기획실 기사)](https://www.kw.ac.kr/ko/life/newsletter.jsp) | jwxe | 2026-11-03 | 목록 | 활발 | – | – | – | 월별 목록(sy, sm 파라미터). 홍보 기사라 공지는 아님 |
| 본부 | [최신연구성과](https://www.kw.ac.kr/ko/life/research.jsp) | jwxe | 2026-11-06 | 목록 | 활발 | – | – | – | 교수 연구 홍보. 학생 공지 아님 |
| 본부 | [미디어 속 광운](https://www.kw.ac.kr/ko/life/media.jsp) | jwxe | 2024-11 | 목록 | 멈춤 | – | – | – | 언론 기사 링크 모음. 1페이지 최신 링크가 2024-11 기사 |
| 본부 | [병무상담 (질의응답)](https://www.kw.ac.kr/ko/life/military_consulting.jsp) | jwxe | 2026-09-01 | 목록 | 뜸함 | – | – | – | 학생이 쓰는 질문 게시판이고 작성자 실명이 보임. 수집 대상 아님 |
| 본부 | [종합 Q&A](https://www.kw.ac.kr/ko/life/qna.jsp) | jwxe | – | – | 로그인 | O | – | – | 열면 KLAS 로그인 화면으로 넘어감 |
| 본부 | [자료실](https://www.kw.ac.kr/ko/life/data.jsp) | jwxe | – | – | 로그인 | O | – | – | KLAS 로그인 필요 |
| 본부 | [자유게시판](https://www.kw.ac.kr/ko/life/bbs.jsp) | jwxe | – | 로드맵 | 로그인 | O | – | O | 학생 글. 로드맵에서 쓰지 않기로 함 |
| 본부 | [지금 광운대](https://www.kw.ac.kr/ko/life/nowkw.jsp) | jwxe | – | – | 로그인 | O | – | – | KLAS 로그인 필요 |
| 본부 | [AI 활용 수업 사례](https://www.kw.ac.kr/ko/life/AIexample.jsp) | jwxe | – | – | 미확인 | – | – | – | 메뉴와 첫 화면 위젯에서 확인. 목록은 요청하지 않음 |
| 본부 | [코로나19](https://www.kw.ac.kr/ko/life/corona.jsp) | jwxe | – | – | 미확인 | – | – | – | 메뉴에만 남아 있음. 요청하지 않음 |

#### 전자정보공과대학

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 전자정보공과대학 | [공지사항](https://ei.kw.ac.kr/community/notice.php) | boardmode | 2026-09-16 | 로드맵 | 뜸함 | – | O | O |  |
| 전자정보공과대학 | [KWIX 공지](https://ei.kw.ac.kr/kwix/kwix_notice.php) | boardmode | 2026-09-16 | 로드맵 | 뜸함 | – | – | O | KWIX 프로그램 전용 |
| 전자공학과 | [학과소식(학부)](https://ee.kw.ac.kr/HTML/department/undergrad_info.php) | boardmode | 2026-11-04 | 첫 화면 | 활발 | – | O | O |  |
| 전자공학과 | [대학원 공지](https://ee.kw.ac.kr/HTML/department/grad_info.php) | boardmode | 2026-09-03 | 로드맵 | 뜸함 | – | – | O |  |
| 전자공학과 | [학과뉴스](https://ee.kw.ac.kr/HTML/department/kwee_news.php) | boardmode | – | 로드맵 | 미확인 | – | – | O | 로드맵: 뉴스성, 약 235KB |
| 전자통신공학과 | [학과공지사항](https://elcomm.kw.ac.kr/department/office_notice.php) | boardmode | 2026-11-04 | 로드맵 | 활발 | – | O | O |  |
| 전자융합공학과 | [공지사항](https://radiowave.kw.ac.kr/community/s_notice.php) | boardmode | 2026-11-04 | 첫 화면 | 활발 | – | O | O |  |
| 전자융합공학과 | [취업정보](https://radiowave.kw.ac.kr/community/employment.php) | boardmode | 2026-09-21 | 로드맵 | 뜸함 | – | – | O |  |
| 전자융합공학과 | [자유게시판·학과소모임·포토갤러리](https://radiowave.kw.ac.kr/community/freeboard.php) | boardmode | – | – | 미확인 | – | – | – | 학생 커뮤니티 메뉴. 공지 아님, 요청하지 않음 |
| 전기공학과 | [학과 공지사항](https://electric.kw.ac.kr/community/s_notice.php) | boardmode | 2026-11-04 | 로드맵 | 활발 | – | O | O |  |
| 전기공학과 | [학과소식](https://electric.kw.ac.kr/autonomy_active/college_notice.php) | boardmode | 2026-09-17 | 로드맵 | 뜸함 | – | – | O |  |
| 전기공학과 | [취업정보·대외활동](https://electric.kw.ac.kr/autonomy_active/employment_field.php) | boardmode | 2026-11-04 | 로드맵 | 활발 | – | – | O |  |
| 전기공학과 | [대학원 공지](https://electric.kw.ac.kr/graduate_school/gradschool_notice.php) | boardmode | 2026-09-03 | 로드맵 | 뜸함 | – | – | O |  |
| 전자재료공학과 | [학과공지사항](https://snme.kw.ac.kr/college/college_notice.php) | boardmode | 2026-11-04 | 첫 화면 | 활발 | – | O | O |  |
| 전자재료공학과 | [학년별 게시판(1~4학년)](https://snme.kw.ac.kr/college/college_04.php) | boardmode | 2025-05-30 | 목록 | 멈춤 | – | – | – | college_01~04.php. 4학년 게시판 최신 2025-05-30, 1학년 게시판 최신 2020-11-13. 첫 화면에 바로가기가 있지만 사실상 멈춤 |
| 반도체시스템공학부 | [공지사항(학부)](https://semicon.kw.ac.kr/HTML/community/notice.php) | boardmode | 2026-10-29 | 첫 화면 | 활발 | – | O | O |  |
| 반도체시스템공학부 | [학부뉴스·포커스](https://semicon.kw.ac.kr/HTML/community/issue.php) | boardmode | – | – | 미확인 | – | – | – | news.php는 로드맵에 있음(뉴스성). issue.php(포커스)는 새로 확인, 요청하지 않음 |

#### 인공지능융합대학

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 인공지능융합대학(4개 학부) | [메인 위젯 대학 공지 탭](https://aicon.kw.ac.kr/main/main.php) | aicon | 2026-11-06 | 첫 화면 | 활발 | – | O | O | sw.kw.ac.kr/main/main.php도 같은 페이지(같은 서버의 또 다른 이름) |
| 인공지능융합대학 | [대학 공지사항](https://aicon.kw.ac.kr/administration/notice.php) | aicon | 2026-11-04 | 로드맵 | 활발 | – | – | O | 1페이지가 전부 고정 글. 위젯 수집으로 대신함 |
| 인공지능융합대학 | [대학원 공지사항](https://aicon.kw.ac.kr/administration/notice_graduate.php) | aicon | 2025-06 | 로드맵 | 멈춤 | – | – | O |  |
| 인공지능융합대학 | [Q&A·자유게시판](https://aicon.kw.ac.kr/community/qna.php) | aicon | – | – | 미확인 | – | – | – | 학생 글 게시판. 요청하지 않음 |
| 컴퓨터정보공학부 | [학부 공지](https://ce.kw.ac.kr/department_office/lecture.php) | aicon | 2026-10-30 | 로드맵 | 활발 | – | – | O | 위젯이 대신 수집 |
| 컴퓨터정보공학부 | [대학원 공지](https://ce.kw.ac.kr/graduate_school/notice.php) | aicon | 2026-08-25 | 로드맵 | 뜸함 | – | – | O |  |
| 소프트웨어학부 | [학부 공지](https://cs.kw.ac.kr/department_office/lecture.php) | aicon | 2026-11-04 | 로드맵 | 활발 | – | – | O | 위젯이 대신 수집 |
| 정보융합학부 | [학부 공지](https://ic.kw.ac.kr/department_office/lecture.php) | aicon | 2026-11-04 | 로드맵 | 활발 | – | – | O | 위젯이 대신 수집 |
| 로봇학부 | [학부 공지](https://cni.kw.ac.kr/department_office/lecture.php) | aicon | 2026-11-04 | 로드맵 | 활발 | – | – | O | 위젯이 대신 수집 |
| 로봇학부 | [대학원 공지](https://cni.kw.ac.kr/graduate_school/notice.php) | aicon | 2026-08-28 | 로드맵 | 뜸함 | – | – | O |  |
| 지능형로봇학과(사업단) | [공지사항](https://share.kw.ac.kr/notice/notice01.php?tmenu=4&smenu=1) | other(tmenu/smenu, admin_mode) | 2026-10-23 | 첫 화면 | 활발 | – | – | O |  |
| 지능형로봇학과(사업단) | [사업단 소식](https://share.kw.ac.kr/notice/notice02.php?tmenu=4&smenu=2) | other(tmenu/smenu) | 2023-12 | 로드맵 | 멈춤 | – | – | O |  |
| 지능형로봇학과(사업단) | [COSS 활동공간·카드뉴스](https://share.kw.ac.kr/notice/notice03.php?tmenu=4&smenu=3) | other(tmenu/smenu) | – | – | 미확인 | – | – | – | 새로 확인. 요청하지 않음 |

#### 공과대학

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 건축공학과 | [공지사항](http://archi.kw.ac.kr/community/notice.php) | boardmode | 2026-08-19 | 로드맵 | 뜸함 | – | O | O |  |
| 건축공학과 | [자료실](http://archi.kw.ac.kr/community/information.php) | boardmode | 2026-10-27 | 로드맵 | 활발 | – | – | O | 홈 화면 '정보' 위젯이 이 게시판 |
| 화학공학과 | [학부공지사항](https://chemng.kw.ac.kr/community/notice.php) | other(admin_mode) | 2026-07-01 | 로드맵 | 뜸함 | – | O | O |  |
| 건축학과 | [NEWS&EVENTS (Wix 블로그)](https://www.kwuarchitecture.com/blank-1) | wix | 2026-09-16 | 로드맵 | 뜸함 | – | – | O | RSS로 수집 중 |
| 건축학과 | [블로그 RSS](https://www.kwuarchitecture.com/blog-feed.xml) | wix | 2026-09-16 | 로드맵 | 뜸함 | – | O | O |  |

#### 자연과학대학

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 자연과학대학 교학팀 | [메인 공지 작성자 필터(자연과학대학)](https://www.kw.ac.kr/ko/life/notice.jsp?searchKey=4&searchVal=자연과학대학) | jwxe | 2026-09-03 | 로드맵 | 뜸함 | – | O | O | 메인 공지의 검색 결과라 메인 게시판 수집으로 이미 들어옴 |
| 스포츠융합과학과 | [공지사항](https://sports.kw.ac.kr/community/notice.php) | other(admin_mode) | 2026-08-24 | 로드맵 | 뜸함 | – | O | O |  |
| 화학과 | [학과 게시판(superboard)](https://chem.kw.ac.kr/board/department) | other(superboard) | 2024-02 | 로드맵 | 멈춤 | – | – | O |  |

#### 인문사회과학대학

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 인문사회과학대학 | [공지사항](https://chss.kw.ac.kr/notice/news.php) | agency | 2026-11-04 | 로드맵 | 활발 | – | O | O |  |
| 국어국문학과 | [공지사항](https://korean.kw.ac.kr/community/notice.php) | agency | 2026-10-14 | 로드맵 | 활발 | – | O | O |  |
| 영어산업학과 | [Notice](https://english.kw.ac.kr/new/bulletin/notice.php) | agency | 2026-10-29 | 로드맵 | 활발 | – | O | O |  |
| 미디어커뮤니케이션학부 | [Notices 2026 (Wix CMS)](https://www.kwmedia.info/notices-2026) | wix | 2026-11-04 | 로드맵 | 활발 | – | – | O | 실제 공지 목록. RSS 피드로는 일부만 잡힘 |
| 미디어커뮤니케이션학부 | [블로그 RSS](https://www.kwmedia.info/blog-feed.xml) | wix | 2026-11-04 | 로드맵 | 활발 | – | O | O |  |
| 산업심리학과 | [공지사항](https://psy.kw.ac.kr/community/notice.php) | agency | 2026-10-29 | 로드맵 | 활발 | – | O | O |  |
| 동북아문화산업학부 | [공지사항](https://dnaci.kw.ac.kr/notice/news.php) | agency | 2026-11-04 | 로드맵 | 활발 | – | O | O |  |

#### 정책법학대학

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 행정학과 | [학부공지사항](https://kwpa.kw.ac.kr/notice/faculty.php) | boardmode | 2026-10-16 | 로드맵 | 활발 | – | O | O |  |
| 법학부 | [공지사항](https://law.kw.ac.kr/bulletin/notice.php) | boardmode | 2026-11-04 | 첫 화면 | 활발 | – | O | O |  |
| 법학부 | [취업정보](https://law.kw.ac.kr/bulletin/job.php) | boardmode | 2026-04-16 | 로드맵 | 뜸함 | – | – | O |  |
| 법학부 | [자료실·미래LAW·활동&소식](https://law.kw.ac.kr/bulletin/law.php) | boardmode | – | – | 미확인 | – | – | – | data.php, law.php, gallery.php. 새로 확인, 요청하지 않음 |
| 국제학부 | [학과 공지 (Facebook 그룹)](https://www.facebook.com/groups/264661916941585/) | facebook | – | – | 로그인 | O | – | O | robots와 약관 때문에 수집 안 함. 링크만 안내 |

#### 경영대학

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 경영대학(전공 공용) | [공지사항](https://biz.kw.ac.kr/community/notice.php) | boardmode | 2026-11-04 | 첫 화면 | 활발 | – | O | O |  |
| 경영대학 | [메인 공지 탭 위젯](https://biz.kw.ac.kr/) | boardmode | 2026-11-04 | 첫 화면 | 활발 | – | – | O |  |
| 경영대학 | [뉴스](https://biz.kw.ac.kr/community/news.php) | boardmode | – | 로드맵 | 미확인 | – | – | O | 보도자료 |
| 경영대학 | [스터디그룹·공인회계사반 자료실](https://biz.kw.ac.kr/activity/reference01.php) | boardmode | – | – | 미확인 | – | – | – | reference01/02.php. 새로 확인, 요청하지 않음 |

#### 참빛인재대학

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 참빛인재대학 교학팀 | [대학공지사항](http://kwlife.kw.ac.kr/notice/notice.php) | boardmode | 2026-11-06 | 첫 화면 | 활발 | – | O | O | 로드맵 기록(10-16)보다 새 글이 있음 |
| 참빛인재대학 | [FAQ·Q&A·자유게시판·학생회·동아리](http://kwlife.kw.ac.kr/notice/qna.php) | boardmode | – | – | 미확인 | – | – | – | 학생 커뮤니티 메뉴. 새로 확인, 요청하지 않음 |
| 금융부동산법무학과 | [공지사항](http://kwlaw.kw.ac.kr/notice/notice.php) | boardmode | 2026-10-26 | 로드맵 | 활발 | – | O | O |  |
| 게임콘텐츠학과 | [공지사항](http://kwgame.kw.ac.kr/notice/notice.php) | boardmode | 2026-05-11 | 로드맵 | 뜸함 | – | O | O |  |
| 스포츠상담재활학과 | [공지사항](http://kwsports.kw.ac.kr/notice/notice.php) | boardmode | 2024-07 | 로드맵 | 멈춤 | – | O | O | 시드 글 3개뿐 |
| 스마트전기전자학과 | [공지사항](http://kwsee.kw.ac.kr/notice/notice.php) | boardmode | 2024-07 | 로드맵 | 멈춤 | – | – | O | www 학과 소개 페이지는 kwlife로 연결 |

#### 인제니움대학

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 인제니움대학 | [공지사항](https://ingenium.kw.ac.kr/inform/notice.php) | ingenium | 2026-06-15 | 첫 화면 | 뜸함 | – | O | O |  |
| 인제니움대학 | [양식·일반·미디어 자료실](https://ingenium.kw.ac.kr/inform/form.php) | ingenium | – | – | 미확인 | – | – | – | 새로 확인, 요청하지 않음 |
| 자율전공학부 | [공지사항](https://liberal.kw.ac.kr/bulletin/notice.php) | ingenium | 2026-11-05 | 첫 화면 | 활발 | – | – | O | 로드맵이 '가장 쓸모 있음'이라 했지만 아직 수집하지 않음. 첫 화면만 1.7MB |
| 자율전공학부 | [학부소식](https://liberal.kw.ac.kr/bulletin/news.php) | ingenium | 2026-04-09 | 목록 | 뜸함 | – | – | O |  |

### 3-2. 대학원·행정부서·부속기관·사업단

#### 대학원

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 일반대학원 | [게시판(교학팀공지·학사·장학·졸업·입학·취업)](https://grad.kw.ac.kr/notice/news.php) | agency | 2026-10-23 | 목록 | 활발 | – | – | O | 기존 boardmode 파서로 27행 읽힘(고정 10) |
| 일반대학원 | [포커스·뉴스속 광운·FAQ](https://grad.kw.ac.kr/notice/press.php) | agency | – | – | 미확인 | – | – | – | focus.php, press.php, FAQ.php. 홍보성 |
| 교육대학원 | [공지사항](https://gedu.kw.ac.kr/new2017/HTML/community/cmnotice.php) | boardmode | 2026-11-05 | 첫 화면 | 활발 | – | – | – | 채용 및 교육(camb.php), 원우회·동문회 게시판도 있음 |
| 상담복지정책대학원 | [공지사항](https://isw.kw.ac.kr/info/01.php?sub=1) | other(admin_mode) | 2026-11-03 | 첫 화면 | 활발 | – | – | – | 채용게시판(comm/05.php), 자유게시판, Q&A도 있음 |
| 건설법무대학원 | [공지사항](https://kwcl.kw.ac.kr/bulletin/notice.php) | boardmode | 2026-11-04 | 첫 화면 | 활발 | – | – | – |  |
| 스마트융합대학원 | [공지사항](https://compro.kw.ac.kr/community/notice.php) | boardmode | 2026-10-23 | 첫 화면 | 활발 | – | – | – | 원우회 공지·소식 게시판도 있음 |
| 환경대학원 | [(게시판 미확인)](https://gses.kw.ac.kr/frontpage.asp?catalogid=kwgses2021&language=ko) | other(asp) | – | – | 미확인 | – | – | – | 메뉴가 자바스크립트라 첫 화면에서 게시판 주소를 찾지 못함 |
| 경영대학원 | [(사이트 없음)](http://gsba.kw.ac.kr/main/main.php) | - | – | – | 접속 불가 | – | – | – | i-web.kr/404.html로 넘어감. www 메뉴 링크가 끊긴 상태 |

#### 취업·진로

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 경력개발팀 | [공지사항](https://job.kw.ac.kr/community/notice.php) | boardmode | 2026-11-05 | 목록 | 활발 | – | – | O | robots 허용, Crawl-delay 10. 기존 boardmode 파서로 34행 읽힘(고정 14). www 취업게시판과 내용이 상당히 겹침 |
| 경력개발팀 | [학교제공 채용정보](https://job.kw.ac.kr/recommend/business.php) | boardmode | 2026-11-06 | 첫 화면 | robots 차단 | – | – | O | robots Disallow /recommend/. 첫 화면 위젯 날짜만 봄. 링크만 안내 |
| 경력개발팀 | [외부 채용정보(워크넷)](https://job.kw.ac.kr/job/worknet_job.php) | boardmode | – | 로드맵 | robots 차단 | – | – | O |  |
| 경력개발팀 | [동문멘토(취업성공사례집)](https://job.kw.ac.kr/community/story.php) | boardmode | – | – | 미확인 | – | – | – | 새로 확인, 요청하지 않음 |
| 현장실습지원팀 | [현장실습 공지](https://internship.kw.ac.kr/home/notice/index.do) | other(.do) | 2026-11-02 | 첫 화면 | robots 차단 | – | – | O | robots가 /index.do만 허용. 첫 화면(index.do)에 최신 공지가 보임(2026-11-02 인턴 채용 안내) |
| KW-IPP공동훈련센터 | [알림마당](http://ipp.kw.ac.kr/common/notice.do?BD_NO=1&MAIN_MENU_NO=4-1) | other(.do, AJAX) | – | – | JS 목록 | – | – | O | 직접 GET하면 사이트 첫 화면으로 302. 목록은 AJAX |
| 참빛인재(비교과) | [itplusinfo](https://itplusinfo.kw.ac.kr/main.do) | other(.do) | – | – | robots 차단 | O | – | O | robots Disallow: / , SSO 로그인 |
| 공학교육혁신센터 드림캐처 | [공지사항(공학교육 안내)](https://dream.kw.ac.kr/resource/edu_info.php) | boardmode | 2021-05-18 | 첫 화면 | 멈춤 | – | – | O |  |

#### 국제

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 국제처 글로벌전략팀 | [Announcement(유학생 공지)](https://oia.kw.ac.kr/campus/notice.php) | boardmode | 2026-11-06 | 목록 | 활발 | – | – | O | 기존 boardmode 파서로 31행 읽힘(고정 15) |
| 국제처 글로벌전략팀 | [교환학생 Community(파견 수기)](https://oia.kw.ac.kr/exchange/community.php) | boardmode | 2021-05-18 | 목록 | 멈춤 | – | – | – |  |
| 국제처 글로벌전략팀 | [Q&A·FAQ](https://oia.kw.ac.kr/campus/Q&A.php) | boardmode | – | – | 미확인 | – | – | – | 새로 확인, 요청하지 않음 |
| 국제처 한국어교육센터(옛 국제교육원) | [공지사항](https://kwiie.kw.ac.kr/community/notice.php) | boardmode | 2026-11-05 | 목록 | 활발 | – | – | – | kile.kw.ac.kr가 여기로 넘어감. 기존 boardmode 파서로 26행 읽힘(고정 6) |
| 국제처 한국어교육센터 | [외부활동·채용](https://kwiie.kw.ac.kr/community/event.php) | boardmode | – | – | 미확인 | – | – | – | event.php, recruitment.php. 새로 확인, 요청하지 않음 |

#### 학생지원·상담·생활

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 인권센터 인권·성평등상담실 | [공지사항](https://humanrights.kw.ac.kr/community/notice.php) | boardmode | 2026-10-16 | 목록 | 활발 | – | – | – | 기존 boardmode 파서로 12행 읽힘. 공지 밖(상담)은 접근 금지 |
| 인권센터 학생상담실 | [공지사항](https://sangdam.kw.ac.kr/board/notice.php) | boardmode(BOARD_MODE=VIEW&ARTICLE_UID) | 2025-05-09 | 목록 | 멈춤 | – | – | O | 링크 형식이 달라 기존 파서로는 0행. 1년 넘게 새 글 없음 |
| 심리건강증진센터 | [공지사항 및 자료](https://gedu.kw.ac.kr/Cham-Bit/new2018/community/notice.php) | boardmode | – | – | 미확인 | – | – | – | www 푸터에서 연결. 지역 아동·성인 대상 바우처 센터라 재학생 공지와는 거리가 있음. 요청하지 않음 |
| 행복기숙사(생활관) | [공지사항](https://kw.happydorm.or.kr/60/6010.do) | other(.do, JS POST) | – | – | JS 목록 | – | – | O | GET으로 받은 HTML에 목록이 없음 |
| 중앙도서관 | [공지(KUPIS)](https://kupis.kw.ac.kr/) | other | – | – | robots 차단 | – | – | O | robots.txt가 'User-agent: * / Disallow: /'. 로드맵의 '공개 검색·공지 사용' 계획과 충돌 |
| 총학생회 이음 | [공지사항](https://www.kwu-studentcouncil.co.kr/notices) | nextjs | 2026-09-09 | 첫 화면 | 뜸함 | – | – | O | 첫 화면 기준. 일정(calendar)은 12월 일정까지 올라와 있음 |

#### 교육혁신·사업단

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 대학혁신사업단 | [공지사항](https://inno.kw.ac.kr/bulletin/notice.php) | boardmode | 2026-11-05 | 목록 | 활발 | – | – | O | 기존 boardmode 파서로 20행 읽힘 |
| 대학혁신사업단 | [관련소식·KW혁신서포터즈·자료실](https://inno.kw.ac.kr/bulletin/related.php) | boardmode | – | – | 미확인 | – | – | – | 새로 확인, 요청하지 않음 |
| 교육혁신원 | [공지사항](https://icei.kw.ac.kr/community/notice.php) | boardmode | 2026-07-22 | 목록 | 뜸함 | – | – | – | 2023년 이후 글이 1건(홈페이지 점검 안내) |
| 교수학습센터 | [프로그램(gnuboard)](https://ontl.kw.ac.kr/bbs/board.php?bo_table=program2) | gnuboard | – | – | robots 차단 | – | – | O | robots.txt가 'Disallow: /'. 로드맵 4절의 수집 후보와 충돌 |
| 인문사회융합인재양성사업단(HUSS) | [공지사항](https://huss.kw.ac.kr/bulletin/notice.php) | boardmode | 2026-11-05 | 목록 | 활발 | – | – | – | 고정 글 포함 최신 2026-11-05(일반 글은 10-13). 기존 boardmode 파서로 30행 읽힘 |
| 인문사회융합인재양성사업단(HUSS) | [참여대학 공지](https://huss.kw.ac.kr/bulletin/notice2.php) | boardmode | – | – | 미확인 | – | – | – | 요청하지 않음 |
| 인문사회융합인재양성사업단(HUSS) | [취업정보](https://huss.kw.ac.kr/support/info.php) | boardmode | 2025-03-31 | 목록 | 멈춤 | – | – | – |  |
| 반도체특성화대학사업단 | [공지사항](https://semi.kw.ac.kr/communication/notice.php) | boardmode | 2026-10-27 | 목록 | 활발 | – | – | – | 양성인원 선발·교육 신청. 기존 boardmode 파서로 23행 읽힘 |
| 반도체특성화대학사업단 | [사업단 소식·문의](https://semi.kw.ac.kr/communication/news.php) | boardmode | – | – | 미확인 | – | – | – | 문의 게시판(faq.php)은 학생 질문, 2026-11-04 글이 보임 |
| 디지털경제인재양성사업단 | [(게시판 미확인)](https://hussde.kw.ac.kr/kwhuss/) | other(JS) | – | – | JS 목록 | – | – | – | 첫 화면이 iframe+자바스크립트라 GET으로는 메뉴가 보이지 않음 |
| KW MOOC | [공지사항](https://kwmooc.kw.ac.kr/boards/62133af843ec0b3c1f5d6b69/posts) | other(JS, /api/v1) | – | – | JS 목록 | – | – | – |  |
| 원격교육지원센터(광운MOOC센터) | [공지사항](http://mooc.kw.ac.kr/?page_id=12) | wordpress | – | – | JS 목록 | – | – | – | HTML에 목록 행이 없음 |

#### 창업·산학

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 창업지원단 | [공지사항](https://startup.kw.ac.kr/communication/notice.php) | boardmode | 2026-11-05 | 목록 | 활발 | – | – | O | 고정 글 포함 최신 11-05(일반 글은 10-28). 기존 boardmode 파서로 30행 읽힘 |
| 창업지원단 | [프로그램 홍보](https://startup.kw.ac.kr/communication/report.php) | boardmode | 2025-05-24 | 목록 | 멈춤 | – | – | – |  |
| 산학협력단 | [공지사항](https://iacf.kw.ac.kr/sub05/sub01.php) | other(type=view&uid) | 2026-10-28 | 첫 화면 | 활발 | – | – | O | 직원 채용·외부 창업 프로그램 위주 |
| 산학협력단 | [입찰공고·뉴스레터·예결산](https://iacf.kw.ac.kr/sub05/sub06.php) | other(type=view&uid) | 2024-04 | 첫 화면 | 멈춤 | – | – | – | 학생 대상 아님 |
| 캠퍼스타운 사업단 | [공지사항](https://kwcampustown.startup-plus.kr/board/B000779) | other(startup-plus, /api/cportal/board) | – | – | JS 목록 | – | – | – | 목록을 자바스크립트로 불러옴. 메인 공지에 '캠퍼스타운사업단' 글이 따로 올라옴 |
| 캠퍼스타운 사업단 | [뉴스·창업 정보·홍보(외부 프로그램 참여 안내)·자료 공간](https://kwcampustown.startup-plus.kr/board/B000777) | other(startup-plus) | – | – | JS 목록 | – | – | – | B000775~B000778, B001165 |
| 발전기금 | [공지사항(기부 이야기·광운 Hot Issue)](https://fund.kw.ac.kr/family/notice.php) | boardmode | 2026-05-26 | 목록 | 뜸함 | – | – | – | 기부 소식. 학생 공지 아님 |

#### 홍보·미디어·입학

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 광운대신문 | [전체기사 RSS](https://kwnews.kw.ac.kr/rss/allArticle.xml) | rss | 2026-11-03 | 목록 | 활발 | – | – | O | 50건 |
| 홍보기획실 | [광운소식(PDF 소식지)](https://news.kw.ac.kr/kw_news/kw_news.html) | other(정적 HTML) | – | 첫 화면 | 미확인 | – | – | O | 호 단위 PDF(최신 126호). 날짜 표기 없음 |
| 입학처 | [입학 공지](https://iphak.kw.ac.kr/intro.php) | other(notice_view.php?bn=) | – | 첫 화면 | 활발 | – | – | – | 게이트 페이지에 '2027 수시 최초합격자 발표 11/6' 등 최신 공지가 뜸. 지원자 대상 |

#### 연구기관

| 소유 | 게시판 | 엔진 | 최신 글 | 근거 | 상태 | 로그인 | 수집 | 로드맵 | 메모 |
|---|---|---|---|---|---|---|---|---|---|
| 나노소자응용연구소(NDAC) | [공지사항](http://www.ndac.re.kr/bbs/board.php?bo_table=gongji) | gnuboard | 2026-05-08 | 첫 화면 | 뜸함 | – | – | – | 연구소 행사. 학부생 대상 아님 |

## 4. 놓친 곳

로드맵과 수집기 어디에도 없는 게시판과 사이트입니다. 학생에게 중요한 순서로 적었습니다.

### 4-1. 학생에게 직접 쓸모 있는 공지 게시판

- **반도체특성화대학사업단 공지** (semi.kw.ac.kr/communication/notice.php, 최신 2026-10-27). 양성인원 선발, 파운드리 공정 교육 신청, 심포지엄 참가 신청이 올라옵니다. 사업단 FAQ에 '반도체 전공이 아니어도 참여할 수 있는지', '장학금을 받을 수 있는지'가 올라와 있을 만큼 학부생 전체가 대상이고, 마감이 있는 모집 공지가 대부분입니다. 이 공지 일부만 전정대 공지에 섞여 올라온다는 로드맵 메모가 있지만 게시판 자체는 빠져 있었습니다.
- **국제처 한국어교육센터 공지** (kwiie.kw.ac.kr/community/notice.php, 최신 2026-11-05). 로드맵은 '국제교육원'으로 사이트만 적고 게시판은 보지 않았습니다. 외국인 유학생·어학연수생 대상 행사, 외부 프로그램, 설문이 올라옵니다. kile.kw.ac.kr도 여기로 넘어갑니다.
- **인문사회융합인재양성사업단(HUSS) 공지** (huss.kw.ac.kr/bulletin/notice.php, 고정 글 최신 2026-11-05). 동계 계절학기 학점 교류, 지산학 리더십 아카데미(1학점), 취업 페스티벌, 해외 프로그램 모집이 올라옵니다. 인문사회 계열 학생에게 학점과 직결됩니다. 교원 대상 글도 섞여 있어 제목으로 거를 필요가 있습니다.
- **인권센터 인권·성평등상담실 공지** (humanrights.kw.ac.kr/community/notice.php, 최신 2026-10-16). 폭력예방교육, 특강(기프티콘 제공) 안내. 글은 한두 달에 1건으로 적지만 전교생 대상입니다. 로드맵은 사이트를 '공지 밖은 접근 금지'로만 적었습니다.
- **특수대학원 4곳 공지** (교육대학원 11-05, 건설법무대학원 11-04, 상담복지정책대학원 11-03, 스마트융합대학원 10-23). 모두 활발하지만 그 대학원생만 볼 내용입니다. 학부생 도구에는 넣지 않아도 됩니다.

### 4-2. 있다는 것만 알아 두면 되는 곳

- **캠퍼스타운 사업단 게시판** (kwcampustown.startup-plus.kr). 공지·뉴스·창업 정보·홍보(외부 프로그램 참여 안내) 게시판이 있지만 목록을 자바스크립트로 불러와 GET으로는 보이지 않습니다. 같은 사업단 글이 메인 공지에도 올라오므로(예: 11-06 'Quantum AI 인재 양성 교육') 메인 공지 수집으로 일부는 잡힙니다.
- **디지털경제인재양성사업단** (hussde.kw.ac.kr). www 기관소개에만 있고 로드맵에는 없는 사이트입니다. 첫 화면이 iframe과 자바스크립트라 게시판을 확인하지 못했습니다.
- **교육혁신원 공지** (icei.kw.ac.kr). 2023년 이후 글이 1건뿐입니다.
- **입학처 공지** (iphak.kw.ac.kr). 게이트 페이지에 수시 합격자 발표 같은 최신 공지가 뜨지만 지원자 대상입니다.
- **전자재료공학과 학년별 게시판**(college_01~04.php). 첫 화면에 바로가기가 있지만 4학년 게시판도 2025-05가 마지막입니다.
- **KW MOOC 공지, 광운MOOC센터 공지**. 둘 다 목록이 자바스크립트라 GET으로는 비어 있습니다.
- **발전기금 공지, 산학협력단 입찰공고, 나노소자응용연구소 공지, 국제처 교환학생 수기, 창업지원단 프로그램 홍보**. 학생 공지가 아니거나 멈춘 게시판입니다.
- **sw.kw.ac.kr**: 인공지능융합대학 사이트의 또 다른 이름입니다(aicon과 같은 페이지). 새 게시판은 아니지만, 링크 정규화와 robots 기록에 이 이름도 넣어야 합니다.

### 4-3. 로드맵과 어긋나는 것

- **중앙도서관 kupis.kw.ac.kr**: robots.txt가 `User-agent: *` / `Disallow: /`입니다. 로드맵 4절은 '검색·신착·공지는 공개'로 적고 공개 검색을 쓰기로 했습니다. robots를 따르면 자동 조회는 할 수 없고 링크 안내만 됩니다.
- **교수학습센터 ontl.kw.ac.kr**: robots.txt가 `Disallow: /`입니다. 로드맵 4절의 '목록은 공개, gnuboard' 후보는 수집할 수 없습니다.
- **참빛인재 itplusinfo.kw.ac.kr**: robots.txt `Disallow: /`. 로드맵은 SSO 로그인 대상으로만 적었는데, 공개 부분도 막혀 있습니다.
- **현장실습지원팀 internship.kw.ac.kr**: robots가 `/index.do`만 허용합니다. 공지 게시판은 막혀 있지만 허용된 첫 화면에 최신 공지 제목과 날짜가 보입니다(오늘 2026-11-02 인턴 채용 안내). 첫 화면만 읽는 것은 robots 범위 안이지만, 학교가 나머지를 막은 뜻을 생각하면 문의 메일에 같이 묻는 편이 안전합니다.
- **학생상담실 공지**: 로드맵에는 수집 후보로 있지만 마지막 글이 2025-05-09입니다. 그리고 링크 형식이 `BOARD_MODE=VIEW&ARTICLE_UID=`라 지금 파서로는 0행입니다.
- **참빛인재대학 대학공지**: 로드맵의 최신 글은 10-16이지만 오늘 첫 화면에 11-06 글이 있습니다.

## 5. 새 수집 후보 순위

로드맵과 수집기 어디에도 없는 게시판 중에서, 최근 활동과 학생 관심도로 순위를 매겼습니다. 모두 robots가 허용하고, 저장한 HTML을 kw-campus `deptboards.parse_board`(A 그룹)에 넣어 읽히는 것을 확인했습니다(요청 추가 없음).

| 순위 | 게시판 | 서버 | 최근 활동 | 파서 확인 | 이유 |
|---|---|---|---|---|---|
| 1 | 반도체특성화대학사업단 공지 `semi.kw.ac.kr/communication/notice.php` | E3 | 최신 10-27. 1페이지 기준 10월 3건, 9월 5건, 8월 4건 (글 번호 34까지) | 23행, 고정 3 | 양성인원 선발·교육 신청 마감. 비전공자도 참여 가능(사업단 FAQ) |
| 2 | HUSS 사업단 공지 `huss.kw.ac.kr/bulletin/notice.php` | E3 | 최신 11-05(고정 글). 고정 포함 11월 2건, 10월 7건, 9월 7건 (글 번호 136까지) | 30행, 고정 10 | 계절학기 학점 교류, 1학점 프로그램, 취업 행사. 교원 대상 글이 섞임 |
| 3 | 한국어교육센터 공지 `kwiie.kw.ac.kr/community/notice.php` | E2 | 최신 11-05. 11월 2건, 10월 2건, 9월 5건 (글 번호 45까지) | 26행, 고정 6 | 외국인 학생·어학연수생 대상 |
| 4 | 인권센터 공지 `humanrights.kw.ac.kr/community/notice.php` | E2 | 10-16, 09-08, 07-30 | 12행, 고정 2 | 전교생 대상 교육·특강. 글은 적음 |
| 5 | 교육대학원·건설법무대학원·상담복지정책대학원·스마트융합대학원 공지 | E2, E4, E3 | 10-23~11-05 | 목록 미확인(첫 화면만) | 활발하지만 대학원생 전용. 학부생 도구라면 뒤로 미룸 |

수집기에 넣을 때 유의할 점:

- E3에 semi와 huss가 더해지면 E3 차례가 aicon 위젯과 게시판 7개로 늘어납니다. 서버당 한 회차 1요청 규칙을 그대로 두면 E3 게시판 하나를 다시 읽는 간격이 지금(3시간 20분)보다 길어집니다. 위젯처럼 한 번에 여러 글을 주는 곳이 아니므로, 활동이 적은 kwsports(2024-07 이후 멈춤)를 빼는 것과 같이 검토하세요.
- kwiie와 humanrights는 E2(8개 게시판)에 붙습니다.
- 새 호스트마다 `politeness.ROBOTS`에 오늘 확인한 결과를 적어야 합니다: semi·huss는 `User-agent: * / Allow: /`, kwiie·icei는 404(파일 없음), humanrights는 302로 오류 페이지(파일 없음).
- 모두 kw-mcp `notices.py`의 `PAGE_HOSTS` 허용 목록에도 넣어야 상세 보기가 됩니다.

참고로 로드맵에는 있지만 아직 모으지 않는 곳 가운데 오늘 활발했던 곳은 이렇습니다. 새 후보보다 이쪽이 학생에게 더 중요합니다.

- 자율전공학부 공지 `liberal.kw.ac.kr/bulletin/notice.php` (첫 화면 기준 11-05). 로드맵 표기 '가장 쓸모 있음'. 로드맵은 고정 행에 `<tr>`이 없다고 적었는데, deptboards의 `_rows`가 법학부 때문에 같은 경우를 이미 처리하고 인제니움대학(같은 엔진)도 A 그룹으로 수집 중이라 A 그룹으로 읽힐 가능성이 큽니다(오늘 목록은 받지 않아 미확인).
- 국제처 유학생 공지 `oia.kw.ac.kr/campus/notice.php` (11-06), 대학혁신사업단 공지 `inno.kw.ac.kr/bulletin/notice.php` (11-05), 창업지원단 공지 `startup.kw.ac.kr/communication/notice.php` (11-05), 일반대학원 게시판 `grad.kw.ac.kr/notice/news.php` (10-23). 넷 다 A 그룹 파서로 읽힙니다.
- 경력개발팀 공지 `job.kw.ac.kr/community/notice.php` (11-05). A 그룹 파서로 34행이 읽히지만 www 취업게시판과 많이 겹치고 Crawl-delay가 10초입니다.
- 학과 취업 게시판: 전기공학과 취업정보·대외활동(11-04), 전자융합공학과 취업정보(09-21), 법학부 취업정보(04-16).

## 6. 확인하지 못한 곳

- 연결 실패: teacher.kw.ac.kr(교직과정), 142rotc.kw.ac.kr, performance.kw.ac.kr(옛 대학혁신사업단), iit.kw.ac.kr(TLS 인증서 체인 오류). 앞의 셋은 로드맵 때도 타임아웃이었습니다.
- kutec.kw.ac.kr: robots.txt의 Crawl-delay가 600초라 첫 화면을 요청하지 않았습니다.
- 환경대학원(gses): 메뉴가 자바스크립트라 게시판 주소를 찾지 못했습니다.
- 행복기숙사, KW-IPP, 캠퍼스타운, KW MOOC, 광운MOOC센터, 디지털경제인재양성사업단: 목록이 자바스크립트나 POST로만 나옵니다.
- 표에서 '미확인'인 게시판은 메뉴에서 이름과 주소만 봤고 목록은 요청하지 않았습니다(대부분 자료실·자유게시판·Q&A·뉴스).
- 학과 게시판의 최신 글은 오늘 첫 화면을 본 곳(전자공학과, 전자융합공학과, 전자재료공학과, 반도체시스템공학부, 법학부, 경영대학, 참빛인재대학, 인제니움대학, 인공지능융합대학, 지능형로봇학과)만 새로 확인했고, 나머지는 로드맵(11-05) 날짜를 옮겼습니다.

