# 광운대학교 웹사이트 전수 조사

기준일 2026-11-07. 호스트 하나에 첫 페이지와 robots.txt만 GET으로 받았습니다. 로그인, 폼 제출, 사이트 안쪽 탐색은 하지 않았습니다. 기계가 읽는 전체 자료는 같은 폴더의 `domains.json`(호스트 1개당 객체 1개)에 있습니다.

## 1. 어떻게 찾았나

- **인증서 투명성**: crt.sh에서 `%.kw.ac.kr`, `%.kwangwoon.ac.kr`, `%.gwu.ac.kr`, `%.kwuniv.com`, 학과 외부 도메인(kwmedia.info, kwuarchitecture.com, envkw.com, kwu-studentcouncil.co.kr), 조직명 `Kwangwoon`을 조회했습니다. certspotter도 한 번 봤습니다.
  - kw.ac.kr 사이트 대부분은 `*.kw.ac.kr` 와일드카드 인증서 하나를 씁니다. 그래서 crt.sh에 이름이 직접 나오는 kw.ac.kr 호스트는 40개 남짓입니다. 나머지의 `crt_first_seen`은 비어 있고 `crt_source`에 와일드카드라고 적었습니다.
- **수동 DNS 집계 사이트**: hackertarget, rapiddns, subdomain.center에서 이름을 더 모았습니다. subdomain.center 결과에는 긁어 온 쓰레기 이름이 많아, DNS가 응답하지 않으면 버렸습니다(257개).
- **로드맵과 로컬 저장소**: `campus-roadmap.md`와 KW_MCP·kw-mcp·kw-campus 저장소에 적힌 호스트를 합쳤습니다. 테스트용 이름(a, b, example, unchecked)은 뺐습니다.
- **첫 페이지 링크**: 받은 첫 페이지의 링크에서 새 KW 호스트 6개와 학교 전용 외부 서비스 몇 개(카피킬러, 구매관리, 어학특강 등)를 더 찾았습니다.
- **DNS**: 후보 1,159개를 `dig +short`로 풀었습니다(kw.ac.kr 쪽 330개 응답). kw.ac.kr에는 와일드카드 DNS가 없어서, 응답이 있으면 실제로 등록된 이름입니다. kwuniv.com은 와일드카드라 모든 이름이 학교 IP 223.194.46.134로 풀립니다.

**요청 예절**
- UA `kw-campus-research (contact kyowon1108@gmail.com)`, GET만 사용, 타임아웃 10초.
- 요청 시작 사이 1초 이상, 같은 IP에는 앞 요청이 끝난 뒤 3초 이상, 같은 IP에 동시 요청 없음.
- https가 실패하면 http로 한 번 더. 리다이렉트는 한 단계씩 따라감(최대 6번). 메타 리프레시, 짧은 JS `location` 이동, 프레임 하나짜리 페이지도 리다이렉트로 봤습니다.
- 2차 확인 두 가지만 했습니다.
  - http가 https로 되돌려 보내고 https 인증서가 깨져 끝난 23개 호스트는 인증서 검증을 끄고 첫 페이지를 한 번 더 받았습니다(robots 재요청 없음).
  - JS 리다이렉트를 놓친 iphak, dac, pay13은 이동 대상 URL을 한 번 받았습니다.
- 요청 수: 학교·관련 사이트 871회(그중 robots.txt 252회, 리다이렉트를 따라간 Google Sites·네이버 등 외부 요청 포함), 수동 조회용 제3자 서비스 34회(crt.sh 21회 포함). 합계 905회.
- 403, 429, CAPTCHA 응답은 없었습니다.

**읽을 때 주의할 점**
- **요청이 교내망에서 나갔습니다.** info.kw.ac.kr 원격근무 로그인 화면이 '접속 아이피 223.194.46.241'을 보여 줬습니다. 그러니 이 결과는 교내에서 본 모습입니다. 그런데도 128.134.x 대역 호스트 대부분은 교내에서도 응답하지 않았습니다.
- druid, esal, sswlab(모두 223.194.46.x, 이 PC와 같은 대역)과 npsw(203.251.81.21)는 이 PC에서 'Network is unreachable'이 났습니다. 이 PC의 라우팅 문제일 수 있어, dead로 적었지만 확실하지 않습니다.
- 상태 정의: `live`는 내용이 있는 페이지, `login-only`는 첫 화면이 로그인뿐인 곳, `redirect`는 다른 호스트로 넘어가는 곳(www↔apex 이동은 제외), `dead`는 응답 없음·4xx/5xx·기본 서버 페이지·안내문만 남은 곳, `not-requested`는 인프라라 요청하지 않은 곳입니다.
- '공지'는 첫 페이지 링크에 공지·notice·board·bbs·news 같은 말이 있는지로만 판단했습니다. JS로 그리는 앱은 '모름'입니다.

## 2. 집계

| 분류 | live | login-only | redirect | dead | 미요청 | 합계 |
|---|---|---|---|---|---|---|
| 대학본부/행정부서 | 9 | 5 | 2 | 3 | 0 | 19 |
| 단과대 | 7 | 0 | 0 | 0 | 0 | 7 |
| 학과 | 35 | 0 | 1 | 6 | 0 | 42 |
| 대학원 | 9 | 0 | 0 | 0 | 0 | 9 |
| 부속·연구기관 | 31 | 2 | 14 | 42 | 0 | 89 |
| 학생지원 | 15 | 4 | 3 | 4 | 0 | 26 |
| 학습시스템 | 3 | 6 | 0 | 0 | 0 | 9 |
| 사업단 | 6 | 0 | 0 | 2 | 0 | 8 |
| 학생자치 | 6 | 0 | 1 | 0 | 0 | 7 |
| 인프라 | 0 | 1 | 0 | 11 | 28 | 40 |
| 기타 | 4 | 0 | 1 | 85 | 12 | 102 |
| **합계** | **125** | **18** | **22** | **153** | **40** | **358** |

- 기타의 dead 85개 가운데 62개는 옛 웹호스팅 서버(128.134.45.154) 한 대에 걸린 이름입니다. 모두 같은 안내 페이지(2006년 공지)를 내서 아래 표에서는 한 줄로 묶었습니다.
- **미러 도메인 두 개**: `kwangwoon.ac.kr`과 `gwu.ac.kr`은 kw.ac.kr과 같은 네임서버(dobong, dobong2)를 쓰고, kw.ac.kr 이름 거의 전부(각각 289개, 288개)가 같은 IP로 풀립니다. 대표 홈페이지는 www.kwangwoon.ac.kr·www.gwu.ac.kr로 들어오면 JS로 www.kw.ac.kr에 보냅니다. 미러 이름은 따로 요청하지 않았고 `domains.json`의 `mirror_names`에 적었습니다. 미러에만 있는 이름은 찾지 못했습니다.

## 3. 분류별 목록

### 대학본부/행정부서 (19)

| 호스트 | 상태 | 용도 | 공지 | robots | 로드맵 | 비고 |
|---|---|---|---|---|---|---|
| fund.kw.ac.kr | live | 발전기금 | 있음 | 일부/허용 |  | 같은 IP 24개 |
| iphak.kw.ac.kr | live | 입학처 입학 홈페이지(게이트 페이지) | 있음 | 없음 |  |  |
| iphakpg.kw.ac.kr | live | 입학 신청 프로그램(입학설명회 신청) | 없음 | 없음 |  |  |
| jasan.kw.ac.kr | live | 자산(물품)관리 시스템으로 추정. Angular 앱이라 내용 미확인 | 모름 | 없음 |  |  |
| m.kw.ac.kr | live | 대표 홈페이지(모바일 주소, 같은 서버) | 있음 | 없음 |  |  |
| news.kw.ac.kr | live | 광운미디어, 온라인 홍보 페이지 | 있음 | 없음 | O | 같은 IP 24개 |
| oia.kw.ac.kr | live | 글로벌전략팀(국제처), 유학생·교환학생 | 있음 | 없음 | O | 같은 IP 23개 |
| rule.kw.ac.kr | live | 규정관리시스템 | 있음 | 없음 | O |  |
| www.kw.ac.kr | live | 대표 홈페이지 | 있음 | 없음 | O |  |
| gw.kw.ac.kr | login-only | 전자결재(그룹웨어), 교직원 로그인 | 모름 | 없음 |  |  |
| info.kw.ac.kr | login-only | 행정시스템 원격근무 로그인 | 모름 | 없음 | O |  |
| kw.mrosystem.com | login-only | 단가계약 구매관리 시스템(외부 업체 운영) | 모름 | 없음 |  |  |
| n-kuris.kw.ac.kr | login-only | n-KURIS 업무 시스템(Nexacro 앱). kwhrd 메뉴에 '업무지원 n-kuris'로 연결 | 모름 | 없음 |  |  |
| safety.kw.ac.kr | login-only | 연구실안전정보망 로그인 | 모름 | 없음 |  |  |
| oiaeng.kw.ac.kr | redirect | 글로벌전략팀 영문 주소 → oia로 이동 | 있음 | 없음 |  | → https://oia.kw.ac.kr; 같은 IP 23개 |
| oiavn.kw.ac.kr | redirect | 글로벌전략팀 베트남어 주소 → oia로 이동 | 있음 | 없음 |  | → https://oia.kw.ac.kr; 같은 IP 23개 |
| nkuris.kw.ac.kr | dead | 옛 KURIS 주소. IIS 기본 페이지만 나옴 | 없음 | 없음 |  | 빈 페이지/기본 페이지 |
| pay13.kw.ac.kr | dead | 납부 관련 서버로 추정(루트가 :80/2025로 JS 이동, 그 주소는 타임아웃) | 없음 | 없음 |  | 리다이렉트 뒤 응답 없음 |
| performance.kw.ac.kr | dead | 성과관리 시스템으로 추정. main.do 읽기 타임아웃, robots는 전체 차단 | 없음 | 전체 차단 | O | 리다이렉트 뒤 응답 없음 |

### 단과대 (7)

| 호스트 | 상태 | 용도 | 공지 | robots | 로드맵 | 비고 |
|---|---|---|---|---|---|---|
| aicon.kw.ac.kr | live | 인공지능융합대학(4개 학부 최신 공지 위젯) | 있음 | 없음 | O | 같은 IP 24개 |
| biz.kw.ac.kr | live | 경영대학(4개 전공 공용) | 있음 | 없음 | O | 같은 IP 23개 |
| chss.kw.ac.kr | live | 인문사회과학대학 | 있음 | 없음 | O | 같은 IP 23개 |
| ei.kw.ac.kr | live | 전자정보공과대학 | 있음 | 없음 | O | 같은 IP 10개 |
| ingenium.kw.ac.kr | live | 인제니움학부대학 | 있음 | 일부/허용 | O | 같은 IP 24개 |
| kwlife.kw.ac.kr | live | 참빛인재대학(야간·성인 단과대) | 있음 | 없음 | O | 같은 IP 24개 |
| sw.kw.ac.kr | live | 인공지능융합대학 별칭 주소(aicon과 같은 화면) | 있음 | 없음 |  | 같은 IP 24개 |

### 학과 (42)

| 호스트 | 상태 | 용도 | 공지 | robots | 로드맵 | 비고 |
|---|---|---|---|---|---|---|
| airobot-dap.kw.ac.kr | live | 국방(방산)AI로봇융합학과, 방위산업 계약학과 | 있음 | 일부/허용 |  | 같은 IP 10개 |
| airobot-mss.kw.ac.kr | live | 방산AI로봇융합학과(계약학과, dap와 같은 서버) | 있음 | 일부/허용 |  | 같은 IP 10개 |
| archi.kw.ac.kr | live | 건축공학과 | 있음 | 없음 | O | 같은 IP 23개 |
| ce.kw.ac.kr | live | 컴퓨터정보공학부 | 있음 | 없음 | O | 같은 IP 24개 |
| chem.kw.ac.kr | live | 화학과 | 있음 | 일부/허용 | O |  |
| chemng.kw.ac.kr | live | 화학공학과 | 있음 | 없음 | O | 같은 IP 10개 |
| cni.kw.ac.kr | live | 로봇학부 | 있음 | 없음 | O | 같은 IP 24개 |
| cs.kw.ac.kr | live | 소프트웨어학부 | 있음 | 없음 | O | 같은 IP 24개 |
| dnaci.kw.ac.kr | live | 동북아문화산업학부 | 있음 | 없음 | O | 같은 IP 23개 |
| ee.kw.ac.kr | live | 전자공학과 | 있음 | 없음 | O | 같은 IP 10개 |
| elcomm.kw.ac.kr | live | 전자통신공학과 | 있음 | 없음 | O | 같은 IP 10개 |
| electric.kw.ac.kr | live | 전기공학과 | 있음 | 없음 | O | 같은 IP 10개 |
| english.kw.ac.kr | live | 영어산업학과(EUC-KR 페이지) | 있음 | 없음 | O | 같은 IP 23개 |
| envkw.com | live | 환경공학과 Wix 사이트(www로 이동) | 없음 | 일부/허용 | O |  |
| ic.kw.ac.kr | live | 정보융합학부 | 있음 | 없음 | O | 같은 IP 24개 |
| korean.kw.ac.kr | live | 국어국문학과 | 있음 | 없음 | O | 같은 IP 23개 |
| kwdois.my.canva.site | live | 국제학부 Canva 한 페이지 사이트(JS 렌더링) | 없음 | 없음 | O |  |
| kwgame.kw.ac.kr | live | 게임콘텐츠학과(참빛인재대학) | 있음 | 없음 | O | 같은 IP 24개 |
| kwlaw.kw.ac.kr | live | 금융부동산법무학과(참빛인재대학) | 있음 | 없음 | O | 같은 IP 24개 |
| kwmedia.info | live | 미디어커뮤니케이션학부 Wix 사이트(www로 이동) | 있음 | 일부/허용 | O |  |
| kwpa.kw.ac.kr | live | 행정학과 | 있음 | 없음 | O | 같은 IP 23개 |
| kwsee.kw.ac.kr | live | 스마트전기전자학과(참빛인재대학) | 있음 | 없음 | O | 같은 IP 24개 |
| kwsports.kw.ac.kr | live | 스포츠상담재활학과(참빛인재대학) | 있음 | 없음 | O | 같은 IP 24개 |
| kwuarchitecture.com | live | 건축학과 Wix 사이트(www로 이동) | 있음 | 일부/허용 | O |  |
| law.kw.ac.kr | live | 법학부 | 있음 | 일부/허용 | O | 같은 IP 10개 |
| liberal.kw.ac.kr | live | 자율전공학부 | 있음 | 일부/허용 | O | 같은 IP 24개 |
| psy.kw.ac.kr | live | 산업심리학과 | 있음 | 없음 | O | 같은 IP 23개 |
| radiowave.kw.ac.kr | live | 전자융합공학과 | 있음 | 없음 | O | 같은 IP 10개 |
| sdt.kw.ac.kr | live | 반도체 전공트랙(사업단형 트랙) | 있음 | 없음 |  | 같은 IP 24개 |
| semicon.kw.ac.kr | live | 반도체시스템공학부 | 있음 | 없음 | O | 같은 IP 10개 |
| snme.kw.ac.kr | live | 전자재료공학과 | 있음 | 없음 | O | 같은 IP 10개 |
| sports.kw.ac.kr | live | 스포츠융합과학과 | 있음 | 일부/허용 | O | 같은 IP 10개 |
| www.envkw.com | live | 환경공학과 Wix 사이트 | 없음 | 일부/허용 | O |  |
| www.kwmedia.info | live | 미디어커뮤니케이션학부 Wix 사이트 | 있음 | 일부/허용 | O |  |
| www.kwuarchitecture.com | live | 건축학과 Wix 사이트 | 있음 | 일부/허용 | O |  |
| inter.kw.ac.kr | redirect | 국제학부. Wix 사이트(sjang21.wixsite.com/dois-kw)로 이동 | 없음 | 없음 |  | → https://sjang21.wixsite.com/dois-kw; 인증서 오류; 같은 IP 18개 |
| chemi.kw.ac.kr | dead | 화학 계열 옛 주소로 추정 | 모름 | - |  | 응답 없음(URLError) |
| comeng.kw.ac.kr | dead | 컴퓨터공학 옛 주소로 추정 | 모름 | - |  | 응답 없음(URLError) |
| electronic.kw.ac.kr | dead | 전자공학 계열 옛 주소로 추정 | 모름 | - |  | 응답 없음(URLError) |
| env.kw.ac.kr | dead | 환경공학과 옛 주소로 추정. HTTP 500 빈 페이지 | 없음 | 없음 |  | HTTP 500; 같은 IP 10개 |
| media.kw.ac.kr | dead | 미디어 계열 옛 주소로 추정 | 모름 | - |  | 응답 없음(URLError) |
| physics.kw.ac.kr | dead | 물리 계열 학과로 추정 | 모름 | - |  | 응답 없음(URLError) |

### 대학원 (9)

| 호스트 | 상태 | 용도 | 공지 | robots | 로드맵 | 비고 |
|---|---|---|---|---|---|---|
| compro.kw.ac.kr | live | 스마트융합대학원 | 있음 | 없음 | O | 같은 IP 24개 |
| gedu.kw.ac.kr | live | 교육대학원 | 있음 | 없음 | O | 같은 IP 23개 |
| grad.kw.ac.kr | live | 일반대학원 | 있음 | 없음 | O | 같은 IP 23개 |
| graden.kw.ac.kr | live | 일반대학원(영문/별도 화면) | 있음 | 없음 |  | 같은 IP 23개 |
| grd.kw.ac.kr | live | 일반대학원 별칭 주소(grad와 같은 화면) | 있음 | 없음 |  | 같은 IP 23개 |
| gsba.kw.ac.kr | live | 경영대학원. 첫 응답이 빈 세션 페이지라 내용 미확인 | 모름 | 일부/허용 | O |  |
| gses.kw.ac.kr | live | 환경대학원(외부 호스팅 ASP) | 있음 | 일부/허용 | O |  |
| isw.kw.ac.kr | live | 상담복지정책대학원 | 있음 | 일부/허용 | O | 같은 IP 10개 |
| kwcl.kw.ac.kr | live | 건설법무대학원 | 있음 | 일부/허용 | O | 같은 IP 23개 |

### 부속·연구기관 (89)

| 호스트 | 상태 | 용도 | 공지 | robots | 로드맵 | 비고 |
|---|---|---|---|---|---|---|
| aser.kw.ac.kr | live | 연구실: 센서·에너지(ASER Lab) | 있음 | 없음 |  |  |
| bcml.kw.ac.kr | live | 연구실: 바이오컴퓨팅·머신러닝(GitHub Pages) | 있음 | 일부/허용 |  |  |
| bic.kw.ac.kr | live | 연구실: Bio-IT 융합 | 없음 | 없음 |  |  |
| cg.kw.ac.kr | live | 연구실: 컴퓨터그래픽스(교수 홈페이지) | 없음 | 없음 |  |  |
| cglab.kw.ac.kr | live | 연구실: 컴퓨터그래픽스(cg와 같은 화면) | 없음 | 없음 |  |  |
| cmc.kw.ac.kr | live | 정신건강과 지역사회 연구센터 | 있음 | 일부/허용 |  |  |
| dac.kw.ac.kr | live | 동해문화예술관(공연장) 인트로 | 없음 | 일부/허용 |  | 같은 IP 10개 |
| drl.kw.ac.kr | live | 연구실: 로봇 조작(DREAM Lab, GitHub Pages) | 있음 | 일부/허용 |  |  |
| iacf.kw.ac.kr | live | 산학협력단 | 있음 | 없음 | O |  |
| icdc.kw.ac.kr | live | 실감콘텐츠 단말 기술 연구센터(ICDC) | 있음 | 일부/허용 |  |  |
| icei.kw.ac.kr | live | 교육혁신원 | 있음 | 없음 | O | 같은 IP 23개 |
| icerink.kw.ac.kr | live | 아이스링크 인트로 | 없음 | 없음 |  | 같은 IP 10개 |
| icon.kw.ac.kr | live | 연구실: 지능형 컴퓨팅·네트워크(Icon Lab) | 있음 | 없음 |  |  |
| iit.kw.ac.kr | live | 정보과학교육원(평생교육, 인증서 오류) | 있음 | 없음 | O | 인증서 오류 |
| int.kw.ac.kr | live | 연구실: 인터랙티브 미디어(IML) | 없음 | 전체 차단 |  |  |
| ipsl.kw.ac.kr | live | 연구실: 비디오 코딩 표준화(Wix, www로 이동) | 있음 | 일부/허용 |  |  |
| kutec.kw.ac.kr | live | 중소기업산학협력센터 | 있음 | 일부/허용 |  |  |
| kwalsc.kw.ac.kr | live | 성인학습성공센터 | 있음 | 없음 |  | 같은 IP 24개 |
| kwiie.kw.ac.kr | live | 국제교육원 한국어교육센터 | 있음 | 없음 | O | 같은 IP 23개 |
| kwnews.kw.ac.kr | live | 광운대신문(국문·KW Times 게이트) | 없음 | 일부/허용 | O |  |
| lab3d.kw.ac.kr | live | 연구실: 입체 3D·공간 미디어 | 있음 | 일부/허용 |  |  |
| micronano.kw.ac.kr | live | 연구실: ASER Lab 별칭 주소 | 있음 | 없음 |  |  |
| mislab.kw.ac.kr | live | 교수 개인 홈페이지(MIS 연구실, FrontPage 시절 HTML) | 없음 | - |  |  |
| nano.kw.ac.kr | live | 연구실: 반도체·나노소자(SNDL) 링크 페이지 | 없음 | 없음 |  | 같은 IP 23개 |
| nedl.kw.ac.kr | live | 연구실: 반도체 공정(SEMATEC) | 있음 | 없음 |  |  |
| pelab.kw.ac.kr | live | 연구실: 전력전자(인증서 오류) | 있음 | 없음 |  | 인증서 오류 |
| robotai.kw.ac.kr | live | 연구실: 로보틱스·AI(GitHub Pages) | 있음 | 없음 |  |  |
| ssl.kw.ac.kr | live | 연구실: 스마트시스템(SSL) 블로그 | 있음 | 없음 |  |  |
| www.ipsl.kw.ac.kr | live | 연구실: 비디오 코딩 표준화(Wix) | 있음 | 일부/허용 |  |  |
| www.kwhrd.com | live | 국가인적자원개발센터(국비 직업훈련) | 있음 | 일부/허용 |  |  |
| xr.kw.ac.kr | live | 연구실: XR·공간 미디어 | 없음 | 일부/허용 |  |  |
| hicsl.kw.ac.kr | login-only | 연구실 Google Sites. 비공개라 구글 로그인 거부 화면 | 모름 | 없음 |  | 인증서 오류; 같은 IP 18개 |
| iconas.kw.ac.kr | login-only | Icon Lab Nextcloud 저장소 로그인 | 모름 | 전체 차단 |  |  |
| ai.kw.ac.kr | redirect | ssl.kw.ac.kr의 CNAME. 스마트시스템 연구실로 이동 | 있음 | 없음 |  | → https://ssl.kw.ac.kr/blog/ |
| aqnmol.kw.ac.kr | redirect | 연구실: 양자나노소재·광전자 → aqnmol.or.kr로 이동 | 있음 | 없음 |  | → http://aqnmol.or.kr; 인증서 오류; 같은 IP 18개 |
| cdsl.kw.ac.kr | redirect | 연구실: 제어·동역학 → Google Sites | 있음 | 없음 |  | → https://sites.google.com/site/cdslkw/; 인증서 오류; 같은 IP 18개 |
| cmskwnews.kw.ac.kr | redirect | 광운대신문 CMS 주소 → kwnews로 이동 | 없음 | 일부/허용 |  | → http://kwnews.kw.ac.kr/ |
| cona.kw.ac.kr | redirect | 연구실: 통신 네트워킹 → Google Sites | 없음 | 없음 |  | → https://sites.google.com/view/kw5441/; 인증서 오류; 같은 IP 18개 |
| datasci.kw.ac.kr | redirect | 연구실: 데이터사이언스(Google Sites로 이동) | 있음 | 없음 |  | → https://sites.google.com/site/datasciencelaboratory |
| dsplab.kw.ac.kr | redirect | 연구실: 통신 신호처리 → Google Sites | 있음 | 없음 |  | → https://sites.google.com/view/csplab/home; 인증서 오류; 같은 IP 18개 |
| efn.kw.ac.kr | redirect | 연구실: 친환경 나노소재 → Google Sites | 없음 | 없음 |  | → https://sites.google.com/site/zorropro/; 인증서 오류; 같은 IP 18개 |
| ict.kw.ac.kr | redirect | 연구실: 지능형 ICT → Google Sites | 없음 | 없음 |  | → https://sites.google.com/site/hyhwangs/; 인증서 오류; 같은 IP 18개 |
| kile.kw.ac.kr | redirect | 한국어교육센터 옛 주소 → kwiie로 이동 | 있음 | 없음 |  | → https://kwiie.kw.ac.kr/; 같은 IP 24개 |
| mclab.kw.ac.kr | redirect | 연구실: CINe Lab → Google Sites | 있음 | 없음 |  | → https://sites.google.com/site/mclabkw/; 인증서 오류; 같은 IP 18개 |
| mpl.kw.ac.kr | redirect | 연구실: 미디어 프로세싱 → Google Sites | 없음 | 없음 |  | → https://sites.google.com/view/media-processor-lab/ |
| skseo.kw.ac.kr | redirect | 교수 개인 홈페이지 → mislab.kw.ac.kr로 이동 | 모름 | 없음 |  | → http://mislab.kw.ac.kr/; 인증서 오류; 같은 IP 18개 |
| swkim.kw.ac.kr | redirect | 교수 개인 홈페이지 → Google Sites | 없음 | 없음 |  | → https://sites.google.com/site/mswkim3; 인증서 오류; 같은 IP 18개 |
| 3dmedia.kw.ac.kr | dead | 3D 미디어 연구센터로 추정 | 모름 | - |  | 응답 없음(URLError) |
| 3drc.kw.ac.kr | dead | 3D 연구센터로 추정 | 모름 | - |  | 응답 없음(URLError) |
| adams.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| ailab.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| apollo.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| asic.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| bicar.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| cclab.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| champ.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| cnlab3.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| coco3.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| coco7.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| comlab.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| comlab11.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| comm21.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| cpe.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| dallas.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| drrc.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| druid.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| esal.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| icee.kw.ac.kr | dead | dream.kw.ac.kr가 링크하지만 DNS 없음 | 모름 | - |  | DNS 응답 없음(요청하지 않음) |
| icslp.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| image.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| ims.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| imsp.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| ipcl.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| iradar.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| lifelong.kw.ac.kr | dead | 평생교육원으로 추정 | 모름 | - |  | 응답 없음(URLError) |
| march.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| netcom.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| oemic.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| opto.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| phycom.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| pllab.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| power.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| research.kw.ac.kr | dead | 연구 관련 주소(산학협력단과 같은 IP). 403 | 없음 | 없음 |  | HTTP 403 |
| rolab.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| soc2012.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| sswlab.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| wdmlink.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| wine.kw.ac.kr | dead | 연구실 주소로 보임(이름으로 추정) | 모름 | - |  | 응답 없음(URLError) |
| www.iacf.kw.ac.kr | dead | 산학협력단 www 이름(인증서 2017~2022) | 모름 | - | O | DNS 응답 없음(요청하지 않음) |

### 학생지원 (26)

| 호스트 | 상태 | 용도 | 공지 | robots | 로드맵 | 비고 |
|---|---|---|---|---|---|---|
| dream.kw.ac.kr | live | 드림캐처(공학교육혁신센터 e-포트폴리오) | 있음 | 없음 | O |  |
| humanrights.kw.ac.kr | live | 인권센터 | 있음 | 없음 | O | 같은 IP 23개 |
| internship.kw.ac.kr | live | 현장실습 온라인 시스템 | 있음 | 전체 차단 | O |  |
| ipp.kw.ac.kr | live | KW-IPP 공동훈련센터(장기현장실습) | 있음 | 없음 | O |  |
| itplusinfo.kw.ac.kr | live | 참빛인재양성 통합관리(비교과·역량진단), 대부분 로그인 | 있음 | 전체 차단 | O |  |
| job.kw.ac.kr | live | 경력개발팀(취업) | 있음 | 일부/허용 | O | 같은 IP 10개 |
| kupis.kw.ac.kr | live | 중앙도서관(인증서 오류) | 있음 | 없음 | O | 인증서 오류 |
| kw.happydorm.or.kr | live | 행복기숙사(외부 업체 운영) | 있음 | 없음 | O |  |
| kwcampustown.startup-plus.kr | live | 캠퍼스타운(창업, 외부 플랫폼) | 있음 | 일부/허용 | O |  |
| kwu.ttceducation.net | live | 교내 어학특강·모의토익(국제교육원 위탁 업체) | 있음 | 전체 차단 |  |  |
| mobileid.kw.ac.kr | live | 열람실 좌석 서버. 루트는 IIS 기본 페이지, 좌석 현황은 /seatweb/ 경로 | 모름 | 없음 | O |  |
| ontl.kw.ac.kr | live | 교수학습센터 | 있음 | 전체 차단 | O |  |
| reading.kw.ac.kr | live | 도서관 독서 프로그램 '리딩리딩' | 있음 | 없음 |  | 인증서 오류 |
| sangdam.kw.ac.kr | live | 학생상담실 | 있음 | 없음 | O | 같은 IP 24개 |
| startup.kw.ac.kr | live | 창업지원센터 | 있음 | 일부/허용 | O | 같은 IP 10개 |
| eclinic.kw.ac.kr | login-only | 영어클리닉 예약(글로컬교육센터) | 모름 | 없음 |  | 같은 IP 24개 |
| kwjob.kw.ac.kr | login-only | 취업 포트폴리오 시스템 로그인 | 모름 | 전체 차단 | O |  |
| libproxy.kw.ac.kr | login-only | 도서관 학외 접속 프록시. 루트는 '비정상적인 접근' 문구 | 모름 | 없음 |  | 같은 IP 10개 |
| office365.kw.ac.kr | login-only | Office 365 신청 포털. 직접 접속하면 403 '학교 포탈을 통해 접근하세요' | 모름 | 없음 |  |  |
| kw.copykiller.co.kr | redirect | 카피킬러 캠퍼스(표절검사) → kw.copykiller.com | 있음 | 전체 차단 |  | → https://kw.copykiller.com/ |
| kwctl.kw.ac.kr | redirect | 교수학습센터 옛 주소 → ontl로 이동 | 있음 | 없음 |  | → https://ontl.kw.ac.kr |
| ontl-el.kw.ac.kr | redirect | 교수학습센터 e-러닝 주소 → ontl로 이동 | 있음 | 일부/허용 |  | → https://ontl.kw.ac.kr/ |
| 142rotc.kw.ac.kr | dead | 학군단 ROTC(로드맵 기록) | 모름 | - | O | 응답 없음(URLError) |
| dorm.kw.ac.kr | dead | 옛 기숙사 주소(인증서 2017~2021, 행복기숙사와 같은 인증서) | 모름 | - |  | DNS 응답 없음(요청하지 않음) |
| mkupis.kw.ac.kr | dead | 옛 모바일 도서관(인증서 2014~2016) | 모름 | - |  | DNS 응답 없음(요청하지 않음) |
| teacher.kw.ac.kr | dead | 교직과정(이름·로드맵 기록으로 추정) | 모름 | - | O | 응답 없음(URLError) |

### 학습시스템 (9)

| 호스트 | 상태 | 용도 | 공지 | robots | 로드맵 | 비고 |
|---|---|---|---|---|---|---|
| kwmate.kw.ac.kr | live | 광운AI메이트(구성원용 AI 워크스페이스, Vercel) | 있음 | 전체 차단 |  |  |
| kwmooc.kw.ac.kr | live | KWMOOC 강좌 사이트 | 있음 | 일부/허용 |  |  |
| mooc.kw.ac.kr | live | MOOC센터(원격교육지원) | 있음 | 없음 | O |  |
| canvas.kw.ac.kr | login-only | Canvas 주소. 커먼즈 로그인으로 이동 | 모름 | 일부/허용 |  |  |
| klas.kw.ac.kr | login-only | KLAS 종합정보서비스 로그인 | 모름 | 없음 | O |  |
| kw.ubob.com | login-only | 광운e러닝(외부 업체, 로그인) | 모름 | 일부/허용 |  |  |
| kwcommons.kw.ac.kr | login-only | 커먼즈(이러닝 LMS) 로그인 | 모름 | 없음 |  |  |
| kwiie-lms.kw.ac.kr | login-only | 한국어문화센터 학사관리 LMS 로그인 | 모름 | 없음 |  | 같은 IP 23개 |
| survey.kw.ac.kr | login-only | 설문 시스템. KLAS 로그인으로 넘어감 | 모름 | 없음 |  |  |

### 사업단 (8)

| 호스트 | 상태 | 용도 | 공지 | robots | 로드맵 | 비고 |
|---|---|---|---|---|---|---|
| huss.kw.ac.kr | live | 인문사회융합인재양성사업단(HUSS) | 있음 | 일부/허용 | O | 같은 IP 24개 |
| inno.kw.ac.kr | live | 대학혁신사업단 | 있음 | 일부/허용 | O | 같은 IP 24개 |
| kwshareservice.com | live | 로봇 사업단 마이크로모듈 이수증·장학금 신청(React 앱) | 모름 | 없음 |  |  |
| robofest2027.kw.ac.kr | live | AI·로봇 미래교육 비전 선포식 초대장(2026-10-29 행사, GitHub Pages) | 없음 | 없음 |  |  |
| semi.kw.ac.kr | live | 반도체특성화대학사업단 | 있음 | 일부/허용 | O | 같은 IP 24개 |
| share.kw.ac.kr | live | 지능형로봇혁신공유대학사업단 | 있음 | 없음 | O | 같은 IP 10개 |
| ace.kw.ac.kr | dead | ACE 사업단으로 추정(teacher와 같은 외부 IP) | 모름 | - |  | 응답 없음(URLError) |
| npsw.kw.ac.kr | dead | 인융대 학부 사이트들이 링크하는 SW 관련 사이트(이 PC에서 네트워크 도달 불가) | 모름 | - |  | 응답 없음(URLError) |

### 학생자치 (7)

| 호스트 | 상태 | 용도 | 공지 | robots | 로드맵 | 비고 |
|---|---|---|---|---|---|---|
| blackcat.kw.ac.kr | live | 정보보안연구회 BlackCat(동아리) | 없음 | 일부/허용 |  |  |
| cia.kw.ac.kr | live | 만화 동아리 C.I.A.(CartoonIsArt) | 있음 | 없음 |  |  |
| coms.kw.ac.kr | live | 컴퓨터 학술동아리 KW COM's(React 앱) | 모름 | 일부/허용 |  |  |
| kitel.kw.ac.kr | live | KITEL 전자연구회(학술동아리) | 있음 | 일부/허용 |  |  |
| kwu-studentcouncil.co.kr | live | 총학생회 '이음'(www와 같은 서버) | 있음 | 없음 | O |  |
| www.kwu-studentcouncil.co.kr | live | 총학생회 '이음' | 있음 | 없음 | O |  |
| baram.kw.ac.kr | redirect | 로봇 학술소모임 바람 → 네이버 카페 | 있음 | 없음 |  | → https://cafe.naver.com/roboticsbaram/; 인증서 오류; 같은 IP 18개 |

### 인프라 (40)

| 호스트 | 상태 | 용도 | 공지 | robots | 로드맵 | 비고 |
|---|---|---|---|---|---|---|
| riseai.kw.ac.kr | login-only | riseai 웹메일 로그인(RISE·AI 사업 쪽 메일로 보임) | 모름 | 전체 차단 |  |  |
| cpanel.envkw.com | dead | 옛 호스팅 부속 이름(cPanel 등) | 모름 | - |  | DNS 응답 없음(요청하지 않음) |
| devinfo.kw.ac.kr | dead | 개발 서버(devwww의 CNAME 대상) | 모름 | - |  | 응답 없음(URLError) |
| devwww.kw.ac.kr | dead | 대표 홈페이지 개발 서버로 추정 | 모름 | - |  | 응답 없음(URLError) |
| kw.ac.kr | dead | 도메인 apex. A 레코드 없음 | 모름 | - | O | DNS 응답 없음(요청하지 않음) |
| kwangwoon.ac.kr | dead | 미러 도메인 apex. A 레코드 없음(하위 이름은 kw.ac.kr과 같은 IP) | 모름 | - |  | DNS 응답 없음(요청하지 않음) |
| mail.envkw.com | dead | 옛 호스팅 부속 이름(cPanel 등) | 모름 | - |  | DNS 응답 없음(요청하지 않음) |
| search.kw.ac.kr | dead | 통합검색 백엔드로 추정. HTTP 500 | 없음 | 없음 |  | HTTP 500; 같은 IP 10개 |
| webdisk.envkw.com | dead | 옛 호스팅 부속 이름(cPanel 등) | 모름 | - |  | DNS 응답 없음(요청하지 않음) |
| webhost.kw.ac.kr | dead | 옛 웹호스팅 서버. 옛 교내 웹호스팅 서버(IIS 5.0)의 공통 안내 페이지. 사이트 내용 없음 | 없음 | 없음 |  | 같은 IP 64개 |
| webhost2.kw.ac.kr | dead | 옛 웹호스팅 서버 2. 교내 웹호스팅 종료(2021-04-30) 안내 페이지 | 없음 | 없음 |  | 인증서 오류; 같은 IP 18개 |
| webmail.envkw.com | dead | 옛 호스팅 부속 이름(cPanel 등) | 모름 | - |  | DNS 응답 없음(요청하지 않음) |
| autodiscover.3dkiff.org | not-requested | cPanel 호스팅 부속 이름 | 모름 | - |  | 같은 IP 17개 |
| cdnkwnews.kw.ac.kr | not-requested | 광운대신문 CDN | 모름 | - |  |  |
| co.kr.libproxy.kw.ac.kr | not-requested | 도서관 원문 프록시(EZproxy) 경유 주소 | 모름 | - |  | 같은 IP 10개 |
| cpanel.3dkiff.org | not-requested | cPanel 호스팅 부속 이름 | 모름 | - |  | 같은 IP 17개 |
| cpcalendars.3dkiff.org | not-requested | cPanel 호스팅 부속 이름 | 모름 | - |  | 같은 IP 17개 |
| cpcontacts.3dkiff.org | not-requested | cPanel 호스팅 부속 이름 | 모름 | - |  | 같은 IP 17개 |
| daisy.kw.ac.kr | not-requested | 메일 서버와 같은 IP | 모름 | - |  | 같은 IP 5개 |
| dbpia.co.kr.libproxy.kw.ac.kr | not-requested | 도서관 원문 프록시(EZproxy) 경유 주소 | 모름 | - |  | 같은 IP 10개 |
| dobong.kw.ac.kr | not-requested | DNS 서버(NS) | 모름 | - |  |  |
| dobong2.kw.ac.kr | not-requested | DNS 서버(NS) | 모름 | - |  |  |
| downloadk.dbpia.co.kr.libproxy.kw.ac.kr | not-requested | 도서관 원문 프록시(EZproxy) 경유 주소 | 모름 | - |  | 같은 IP 10개 |
| groupmail.kw.ac.kr | not-requested | 단체 메일 발송 | 모름 | - |  |  |
| iitmail.kw.ac.kr | not-requested | 메일 서버와 같은 IP | 모름 | - |  | 같은 IP 5개 |
| kiss-kstudy-com.libproxy.kw.ac.kr | not-requested | 도서관 원문 프록시(EZproxy) 경유 주소 | 모름 | - |  | 같은 IP 10개 |
| kr.libproxy.kw.ac.kr | not-requested | 도서관 원문 프록시(EZproxy) 경유 주소 | 모름 | - |  | 같은 IP 10개 |
| mail.3dkiff.org | not-requested | cPanel 호스팅 부속 이름 | 모름 | - |  | 같은 IP 17개 |
| mail.kw.ac.kr | not-requested | 메일 서버 | 모름 | - |  | 같은 IP 5개 |
| slvkwnews.kw.ac.kr | not-requested | 광운대신문 복제 서버 | 모름 | - |  |  |
| smtp.kw.ac.kr | not-requested | SMTP | 모름 | - |  |  |
| smtp1.kw.ac.kr | not-requested | SMTP | 모름 | - |  |  |
| smtp2.kw.ac.kr | not-requested | SMTP | 모름 | - |  |  |
| webdisk.3dkiff.org | not-requested | cPanel 호스팅 부속 이름 | 모름 | - |  | 같은 IP 17개 |
| webmail.3dkiff.org | not-requested | cPanel 호스팅 부속 이름 | 모름 | - |  | 같은 IP 17개 |
| webmail.kw.ac.kr | not-requested | 웹메일(메일 서버 daisy의 CNAME) | 모름 | - |  | 같은 IP 5개 |
| wildcard.libproxy.kw.ac.kr | not-requested | 도서관 원문 프록시(EZproxy) 경유 주소 | 모름 | - |  | 같은 IP 10개 |
| wmail.kw.ac.kr | not-requested | 메일 서버와 같은 IP(웹메일) | 모름 | - |  | 같은 IP 5개 |
| www-dbpia-co-kr.libproxy.kw.ac.kr | not-requested | 도서관 원문 프록시(EZproxy) 경유 주소 | 모름 | - |  | 같은 IP 10개 |
| www-earticle-net.libproxy.kw.ac.kr | not-requested | 도서관 원문 프록시(EZproxy) 경유 주소 | 모름 | - |  | 같은 IP 10개 |

### 기타 (102)

| 호스트 | 상태 | 용도 | 공지 | robots | 로드맵 | 비고 |
|---|---|---|---|---|---|---|
| dongmoon.kw.ac.kr | live | 총동문회 | 있음 | 없음 |  |  |
| python.kw.ac.kr | live | 데이터 분석 수업 자료 파일 목록(디렉터리형 공개 페이지) | 없음 | 없음 |  |  |
| sangjo.kw.ac.kr | live | 교수상조회 | 있음 | 전체 차단 |  | 같은 IP 23개 |
| www.kwuaa.com | live | 총동문회 외부 도메인(dongmoon과 같은 서버) | 있음 | 없음 |  |  |
| tak.kw.ac.kr | redirect | 네이버 블로그로 이동(개인 블로그로 보임) | 없음 | 없음 |  | → https://blog.naver.com/PostList.naver?blogId=positiveant&widgetTypeCall=true&noT; 인증서 오류; 같은 IP 18개 |
| 3dkiff.org | dead | 옛 3D 국제영화제 도메인. 지금은 중국어 도박 스팸 사이트 | 없음 | 없음 |  | 도메인이 남에게 넘어감. 2022년에는 xr.kw.ac.kr와 같은 인증서에 있었음; 같은 IP 17개 |
| computer.kw.ac.kr | dead | 교내 웹호스팅 종료(2021-04-30) 안내 페이지 | 없음 | 없음 |  | 인증서 오류; 같은 IP 18개 |
| dpse.kw.ac.kr | dead | 403 Forbidden | 없음 | 없음 |  | HTTP 403 |
| family.kw.ac.kr | dead | 패밀리사이트로 추정 | 없음 | 없음 |  | 리다이렉트 뒤 응답 없음 |
| foodcourt.kw.ac.kr | dead | 푸드코트 옛 주소. 교내 웹호스팅 종료(2021-04-30) 안내 페이지 | 없음 | 없음 | O | 인증서 오류; 같은 IP 18개 |
| gwangunai.myfgi.kr | dead | airobot-mss가 링크한 외부 호스트. Plesk 기본 페이지 | 없음 | 없음 |  | 빈 페이지/기본 페이지 |
| icc.kw.ac.kr | dead | 403 Forbidden | 없음 | 없음 |  | HTTP 403 |
| icnt.kw.ac.kr | dead | 용도 모름 | 없음 | 없음 |  | 리다이렉트 뒤 응답 없음 |
| itrade.kw.ac.kr | dead | 웹서버 기본 페이지(Default Site) | 없음 | 없음 |  | 기본 페이지; 같은 IP 23개 |
| kwci.kw.ac.kr | dead | 교내 웹호스팅 종료(2021-04-30) 안내 페이지 | 없음 | 없음 |  | 인증서 오류; 같은 IP 18개 |
| kwcyber.or.kr | dead | 2014년 인증서에 kwcyber@kw.ac.kr 연락처. 지금은 DNS 없음 | 모름 | - |  | DNS 응답 없음(요청하지 않음) |
| kwf.kw.ac.kr | dead | 이름만으로는 용도 모름 | 모름 | - |  | 응답 없음(URLError) |
| kwmusic.kw.ac.kr | dead | 403 Forbidden | 없음 | 없음 |  | HTTP 403 |
| kwuniv.com | dead | *.kwuniv.com 와일드카드가 학교 IP(223.194.46.134)를 가리킴. 루트는 연결 끊김 | 모름 | - |  | 응답 없음(RemoteDisconnected) |
| kwusj.kw.ac.kr | dead | 옛 웹호스팅 서버(128.134.45.154)의 이름. http는 https로 보내고 https는 TLS 협상 실패 | 모름 | 없음 |  | 인증서 오류; 리다이렉트 뒤 응답 없음; 같은 IP 64개 |
| shobs.kw.ac.kr | dead | 인증서 2017년 1건뿐 | 모름 | - |  | DNS 응답 없음(요청하지 않음) |
| sso.kwuniv.com | dead | kwuniv.com 쪽 SSO API. 루트는 JSON 404 | 없음 | 없음 |  | HTTP 404 |
| travis.kw.ac.kr | dead | Apache 기본 페이지 | 없음 | 없음 |  | 빈 페이지/기본 페이지 |
| tulipapp.kw.ac.kr | dead | 앱 서버로 추정 | 모름 | - |  | 응답 없음(URLError) |
| www-eng.kw.ac.kr | dead | 옛 영문 홈페이지 주소. 교내 웹호스팅 종료(2021-04-30) 안내 페이지 | 없음 | 없음 |  | 인증서 오류; 같은 IP 18개 |
| www.kwcyber.or.kr | dead | kwcyber.or.kr의 www | 모름 | - |  | DNS 응답 없음(요청하지 않음) |
| www.shobs.kw.ac.kr | dead | shobs의 www | 모름 | - |  | DNS 응답 없음(요청하지 않음) |
| xyz.kw.ac.kr | dead | 연결 거부. crt.sh 기록 2022~2024 | 모름 | - |  | 응답 없음(URLError) |
| crm.3dkiff.org | not-requested | 3dkiff.org와 같은 서버, KW 소유 불확실해 미요청 | 모름 | - |  | 같은 IP 17개 |
| daple.kwuniv.com | not-requested | DAPLE(이미 분석함). 존재만 기록 | 모름 | - |  |  |
| oc.3dkiff.org | not-requested | 3dkiff.org와 같은 서버, KW 소유 불확실해 미요청 | 모름 | - |  | 같은 IP 17개 |
| sd.3dkiff.org | not-requested | 3dkiff.org와 같은 서버, KW 소유 불확실해 미요청 | 모름 | - |  | 같은 IP 17개 |
| vr.3dkiff.org | not-requested | 3dkiff.org와 같은 서버, KW 소유 불확실해 미요청 | 모름 | - |  | 같은 IP 17개 |
| www.3dkiff.org | not-requested | 3dkiff.org와 같은 서버, KW 소유 불확실해 미요청 | 모름 | - |  | 같은 IP 17개 |
| www.crm.3dkiff.org | not-requested | 3dkiff.org와 같은 서버, KW 소유 불확실해 미요청 | 모름 | - |  | 같은 IP 17개 |
| www.libproxy.kw.ac.kr | not-requested | libproxy 와일드카드 별칭 | 모름 | - |  | 같은 IP 10개 |
| www.oc.3dkiff.org | not-requested | 3dkiff.org와 같은 서버, KW 소유 불확실해 미요청 | 모름 | - |  | 같은 IP 17개 |
| www.sd.3dkiff.org | not-requested | 3dkiff.org와 같은 서버, KW 소유 불확실해 미요청 | 모름 | - |  | 같은 IP 17개 |
| www.sso.kwuniv.com | not-requested | *.kwuniv.com 와일드카드 별칭 | 모름 | - |  |  |
| www.vr.3dkiff.org | not-requested | 3dkiff.org와 같은 서버, KW 소유 불확실해 미요청 | 모름 | - |  | 같은 IP 17개 |
| (옛 웹호스팅 이름 62개, 아래 참고) | dead | 옛 교내 웹호스팅 서버(IIS 5.0)의 공통 안내 페이지 | 없음 | 없음 |  | 128.134.45.154 |

옛 웹호스팅 서버(128.134.45.154, IIS 5.0)에 걸린 이름 62개: abeek, adhoc, air, allsports, analysis, annals, awst, baseball, bi, bklee, ce95, cemlab, cheer, chinese, cis, cm21, conea, dongari, eem, ewal, fs, gosi, hbchung, hklee, human, jcci, kspc07, kusa, kw70th, kwac, kwm, kwmedia, kwsel, kyungbok, lawlab, mathematics, mis, mmedia, mpm21, msdl, mwantenna, nosound, nsrl, pic, point, powerlab, rebt, rfic, rficlab, rfmdl, sarang, sicogg9, srslab, srwct, ssd, tg, theochem, tyoung, tyy, wnlab, youthlab, zeus (모두 `.kw.ac.kr`). 연구실·동아리 이름이 많지만 지금은 내용이 없습니다. 같은 IP의 kwusj는 https 협상이 실패해 확인하지 못했습니다.

## 4. 로드맵에 없는 호스트 (놓친 후보)

`campus-roadmap.md`에 호스트 이름이 나오지 않는 곳입니다. www와 apex는 한쪽만 나와도 나온 것으로 봤고, kwsee·kwsports는 3절에 이름만 적혀 있어 나온 것으로 쳤습니다.

모두 275개입니다. 이 가운데 지금 열리는 곳(live, login-only, redirect)이 88개입니다.

### 4-1. 지금 열리는 곳

**대학본부/행정부서**
- `fund.kw.ac.kr` (live, 공지 있음): 발전기금
- `gw.kw.ac.kr` (login-only, 공지 모름): 전자결재(그룹웨어), 교직원 로그인
- `iphak.kw.ac.kr` (live, 공지 있음): 입학처 입학 홈페이지(게이트 페이지)
- `iphakpg.kw.ac.kr` (live, 공지 없음): 입학 신청 프로그램(입학설명회 신청)
- `jasan.kw.ac.kr` (live, 공지 모름): 자산(물품)관리 시스템으로 추정. Angular 앱이라 내용 미확인
- `kw.mrosystem.com` (login-only, 공지 모름): 단가계약 구매관리 시스템(외부 업체 운영)
- `m.kw.ac.kr` (live, 공지 있음): 대표 홈페이지(모바일 주소, 같은 서버)
- `n-kuris.kw.ac.kr` (login-only, 공지 모름): n-KURIS 업무 시스템(Nexacro 앱). kwhrd 메뉴에 '업무지원 n-kuris'로 연결
- `oiaeng.kw.ac.kr` (redirect, 공지 있음): 글로벌전략팀 영문 주소 → oia로 이동 → https://oia.kw.ac.kr
- `oiavn.kw.ac.kr` (redirect, 공지 있음): 글로벌전략팀 베트남어 주소 → oia로 이동 → https://oia.kw.ac.kr
- `safety.kw.ac.kr` (login-only, 공지 모름): 연구실안전정보망 로그인

**단과대**
- `sw.kw.ac.kr` (live, 공지 있음): 인공지능융합대학 별칭 주소(aicon과 같은 화면)

**학과**
- `airobot-dap.kw.ac.kr` (live, 공지 있음): 국방(방산)AI로봇융합학과, 방위산업 계약학과
- `airobot-mss.kw.ac.kr` (live, 공지 있음): 방산AI로봇융합학과(계약학과, dap와 같은 서버)
- `inter.kw.ac.kr` (redirect, 공지 없음): 국제학부. Wix 사이트(sjang21.wixsite.com/dois-kw)로 이동 → https://sjang21.wixsite.com/dois-kw
- `sdt.kw.ac.kr` (live, 공지 있음): 반도체 전공트랙(사업단형 트랙)

**대학원**
- `graden.kw.ac.kr` (live, 공지 있음): 일반대학원(영문/별도 화면)
- `grd.kw.ac.kr` (live, 공지 있음): 일반대학원 별칭 주소(grad와 같은 화면)

**부속·연구기관**
- `ai.kw.ac.kr` (redirect, 공지 있음): ssl.kw.ac.kr의 CNAME. 스마트시스템 연구실로 이동 → https://ssl.kw.ac.kr/blog/
- `aqnmol.kw.ac.kr` (redirect, 공지 있음): 연구실: 양자나노소재·광전자 → aqnmol.or.kr로 이동 → http://aqnmol.or.kr
- `aser.kw.ac.kr` (live, 공지 있음): 연구실: 센서·에너지(ASER Lab)
- `bcml.kw.ac.kr` (live, 공지 있음): 연구실: 바이오컴퓨팅·머신러닝(GitHub Pages)
- `bic.kw.ac.kr` (live, 공지 없음): 연구실: Bio-IT 융합
- `cdsl.kw.ac.kr` (redirect, 공지 있음): 연구실: 제어·동역학 → Google Sites → https://sites.google.com/site/cdslkw/
- `cg.kw.ac.kr` (live, 공지 없음): 연구실: 컴퓨터그래픽스(교수 홈페이지)
- `cglab.kw.ac.kr` (live, 공지 없음): 연구실: 컴퓨터그래픽스(cg와 같은 화면)
- `cmc.kw.ac.kr` (live, 공지 있음): 정신건강과 지역사회 연구센터
- `cmskwnews.kw.ac.kr` (redirect, 공지 없음): 광운대신문 CMS 주소 → kwnews로 이동 → http://kwnews.kw.ac.kr/
- `cona.kw.ac.kr` (redirect, 공지 없음): 연구실: 통신 네트워킹 → Google Sites → https://sites.google.com/view/kw5441/
- `dac.kw.ac.kr` (live, 공지 없음): 동해문화예술관(공연장) 인트로
- `datasci.kw.ac.kr` (redirect, 공지 있음): 연구실: 데이터사이언스(Google Sites로 이동) → https://sites.google.com/site/datasciencelaboratory
- `drl.kw.ac.kr` (live, 공지 있음): 연구실: 로봇 조작(DREAM Lab, GitHub Pages)
- `dsplab.kw.ac.kr` (redirect, 공지 있음): 연구실: 통신 신호처리 → Google Sites → https://sites.google.com/view/csplab/home
- `efn.kw.ac.kr` (redirect, 공지 없음): 연구실: 친환경 나노소재 → Google Sites → https://sites.google.com/site/zorropro/
- `hicsl.kw.ac.kr` (login-only, 공지 모름): 연구실 Google Sites. 비공개라 구글 로그인 거부 화면
- `icdc.kw.ac.kr` (live, 공지 있음): 실감콘텐츠 단말 기술 연구센터(ICDC)
- `icerink.kw.ac.kr` (live, 공지 없음): 아이스링크 인트로
- `icon.kw.ac.kr` (live, 공지 있음): 연구실: 지능형 컴퓨팅·네트워크(Icon Lab)
- `iconas.kw.ac.kr` (login-only, 공지 모름): Icon Lab Nextcloud 저장소 로그인
- `ict.kw.ac.kr` (redirect, 공지 없음): 연구실: 지능형 ICT → Google Sites → https://sites.google.com/site/hyhwangs/
- `int.kw.ac.kr` (live, 공지 없음): 연구실: 인터랙티브 미디어(IML)
- `ipsl.kw.ac.kr` (live, 공지 있음): 연구실: 비디오 코딩 표준화(Wix, www로 이동)
- `kile.kw.ac.kr` (redirect, 공지 있음): 한국어교육센터 옛 주소 → kwiie로 이동 → https://kwiie.kw.ac.kr/
- `kutec.kw.ac.kr` (live, 공지 있음): 중소기업산학협력센터
- `kwalsc.kw.ac.kr` (live, 공지 있음): 성인학습성공센터
- `lab3d.kw.ac.kr` (live, 공지 있음): 연구실: 입체 3D·공간 미디어
- `mclab.kw.ac.kr` (redirect, 공지 있음): 연구실: CINe Lab → Google Sites → https://sites.google.com/site/mclabkw/
- `micronano.kw.ac.kr` (live, 공지 있음): 연구실: ASER Lab 별칭 주소
- `mislab.kw.ac.kr` (live, 공지 없음): 교수 개인 홈페이지(MIS 연구실, FrontPage 시절 HTML)
- `mpl.kw.ac.kr` (redirect, 공지 없음): 연구실: 미디어 프로세싱 → Google Sites → https://sites.google.com/view/media-processor-lab/
- `nano.kw.ac.kr` (live, 공지 없음): 연구실: 반도체·나노소자(SNDL) 링크 페이지
- `nedl.kw.ac.kr` (live, 공지 있음): 연구실: 반도체 공정(SEMATEC)
- `pelab.kw.ac.kr` (live, 공지 있음): 연구실: 전력전자(인증서 오류)
- `robotai.kw.ac.kr` (live, 공지 있음): 연구실: 로보틱스·AI(GitHub Pages)
- `skseo.kw.ac.kr` (redirect, 공지 모름): 교수 개인 홈페이지 → mislab.kw.ac.kr로 이동 → http://mislab.kw.ac.kr/
- `ssl.kw.ac.kr` (live, 공지 있음): 연구실: 스마트시스템(SSL) 블로그
- `swkim.kw.ac.kr` (redirect, 공지 없음): 교수 개인 홈페이지 → Google Sites → https://sites.google.com/site/mswkim3
- `www.ipsl.kw.ac.kr` (live, 공지 있음): 연구실: 비디오 코딩 표준화(Wix)
- `www.kwhrd.com` (live, 공지 있음): 국가인적자원개발센터(국비 직업훈련)
- `xr.kw.ac.kr` (live, 공지 없음): 연구실: XR·공간 미디어

**학생지원**
- `eclinic.kw.ac.kr` (login-only, 공지 모름): 영어클리닉 예약(글로컬교육센터)
- `kw.copykiller.co.kr` (redirect, 공지 있음): 카피킬러 캠퍼스(표절검사) → kw.copykiller.com → https://kw.copykiller.com/
- `kwctl.kw.ac.kr` (redirect, 공지 있음): 교수학습센터 옛 주소 → ontl로 이동 → https://ontl.kw.ac.kr
- `kwu.ttceducation.net` (live, 공지 있음): 교내 어학특강·모의토익(국제교육원 위탁 업체)
- `libproxy.kw.ac.kr` (login-only, 공지 모름): 도서관 학외 접속 프록시. 루트는 '비정상적인 접근' 문구
- `office365.kw.ac.kr` (login-only, 공지 모름): Office 365 신청 포털. 직접 접속하면 403 '학교 포탈을 통해 접근하세요'
- `ontl-el.kw.ac.kr` (redirect, 공지 있음): 교수학습센터 e-러닝 주소 → ontl로 이동 → https://ontl.kw.ac.kr/
- `reading.kw.ac.kr` (live, 공지 있음): 도서관 독서 프로그램 '리딩리딩'

**학습시스템**
- `canvas.kw.ac.kr` (login-only, 공지 모름): Canvas 주소. 커먼즈 로그인으로 이동
- `kw.ubob.com` (login-only, 공지 모름): 광운e러닝(외부 업체, 로그인)
- `kwcommons.kw.ac.kr` (login-only, 공지 모름): 커먼즈(이러닝 LMS) 로그인
- `kwiie-lms.kw.ac.kr` (login-only, 공지 모름): 한국어문화센터 학사관리 LMS 로그인
- `kwmate.kw.ac.kr` (live, 공지 있음): 광운AI메이트(구성원용 AI 워크스페이스, Vercel)
- `kwmooc.kw.ac.kr` (live, 공지 있음): KWMOOC 강좌 사이트
- `survey.kw.ac.kr` (login-only, 공지 모름): 설문 시스템. KLAS 로그인으로 넘어감

**사업단**
- `kwshareservice.com` (live, 공지 모름): 로봇 사업단 마이크로모듈 이수증·장학금 신청(React 앱)
- `robofest2027.kw.ac.kr` (live, 공지 없음): AI·로봇 미래교육 비전 선포식 초대장(2026-10-29 행사, GitHub Pages)

**학생자치**
- `baram.kw.ac.kr` (redirect, 공지 있음): 로봇 학술소모임 바람 → 네이버 카페 → https://cafe.naver.com/roboticsbaram/
- `blackcat.kw.ac.kr` (live, 공지 없음): 정보보안연구회 BlackCat(동아리)
- `cia.kw.ac.kr` (live, 공지 있음): 만화 동아리 C.I.A.(CartoonIsArt)
- `coms.kw.ac.kr` (live, 공지 모름): 컴퓨터 학술동아리 KW COM's(React 앱)
- `kitel.kw.ac.kr` (live, 공지 있음): KITEL 전자연구회(학술동아리)

**인프라**
- `riseai.kw.ac.kr` (login-only, 공지 모름): riseai 웹메일 로그인(RISE·AI 사업 쪽 메일로 보임)

**기타**
- `dongmoon.kw.ac.kr` (live, 공지 있음): 총동문회
- `python.kw.ac.kr` (live, 공지 없음): 데이터 분석 수업 자료 파일 목록(디렉터리형 공개 페이지)
- `sangjo.kw.ac.kr` (live, 공지 있음): 교수상조회
- `tak.kw.ac.kr` (redirect, 공지 없음): 네이버 블로그로 이동(개인 블로그로 보임) → https://blog.naver.com/PostList.naver?blogId=positiveant&widgetTypeCall=true&noTrackingCode=true&directAccess=true
- `www.kwuaa.com` (live, 공지 있음): 총동문회 외부 도메인(dongmoon과 같은 서버)

### 4-2. 열리지 않거나 요청하지 않은 곳

- **응답 없음(타임아웃·연결 실패)** (56): 3dmedia.kw.ac.kr, 3drc.kw.ac.kr, ace.kw.ac.kr, adams.kw.ac.kr, ailab.kw.ac.kr, apollo.kw.ac.kr, asic.kw.ac.kr, bicar.kw.ac.kr, cclab.kw.ac.kr, champ.kw.ac.kr, chemi.kw.ac.kr, cnlab3.kw.ac.kr, coco3.kw.ac.kr, coco7.kw.ac.kr, comeng.kw.ac.kr, comlab.kw.ac.kr, comlab11.kw.ac.kr, comm21.kw.ac.kr, cpe.kw.ac.kr, dallas.kw.ac.kr, devinfo.kw.ac.kr, devwww.kw.ac.kr, drrc.kw.ac.kr, druid.kw.ac.kr, electronic.kw.ac.kr, esal.kw.ac.kr, family.kw.ac.kr, icnt.kw.ac.kr, icslp.kw.ac.kr, image.kw.ac.kr, ims.kw.ac.kr, imsp.kw.ac.kr, ipcl.kw.ac.kr, iradar.kw.ac.kr, kwf.kw.ac.kr, kwuniv.com, kwusj.kw.ac.kr, lifelong.kw.ac.kr, march.kw.ac.kr, media.kw.ac.kr, netcom.kw.ac.kr, npsw.kw.ac.kr, oemic.kw.ac.kr, opto.kw.ac.kr, pay13.kw.ac.kr, phycom.kw.ac.kr, physics.kw.ac.kr, pllab.kw.ac.kr, power.kw.ac.kr, rolab.kw.ac.kr, soc2012.kw.ac.kr, sswlab.kw.ac.kr, tulipapp.kw.ac.kr, wdmlink.kw.ac.kr, wine.kw.ac.kr, xyz.kw.ac.kr
- **오류·기본 페이지·종료 안내** (17): 3dkiff.org, computer.kw.ac.kr, dpse.kw.ac.kr, env.kw.ac.kr, gwangunai.myfgi.kr, icc.kw.ac.kr, itrade.kw.ac.kr, kwci.kw.ac.kr, kwmusic.kw.ac.kr, nkuris.kw.ac.kr, research.kw.ac.kr, search.kw.ac.kr, sso.kwuniv.com, travis.kw.ac.kr, webhost.kw.ac.kr, webhost2.kw.ac.kr, www-eng.kw.ac.kr
- **DNS 없음** (12): cpanel.envkw.com, dorm.kw.ac.kr, icee.kw.ac.kr, kwangwoon.ac.kr, kwcyber.or.kr, mail.envkw.com, mkupis.kw.ac.kr, shobs.kw.ac.kr, webdisk.envkw.com, webmail.envkw.com, www.kwcyber.or.kr, www.shobs.kw.ac.kr
- **인프라·미요청** (40): autodiscover.3dkiff.org, cdnkwnews.kw.ac.kr, co.kr.libproxy.kw.ac.kr, cpanel.3dkiff.org, cpcalendars.3dkiff.org, cpcontacts.3dkiff.org, crm.3dkiff.org, daisy.kw.ac.kr, daple.kwuniv.com, dbpia.co.kr.libproxy.kw.ac.kr, dobong.kw.ac.kr, dobong2.kw.ac.kr, downloadk.dbpia.co.kr.libproxy.kw.ac.kr, groupmail.kw.ac.kr, iitmail.kw.ac.kr, kiss-kstudy-com.libproxy.kw.ac.kr, kr.libproxy.kw.ac.kr, mail.3dkiff.org, mail.kw.ac.kr, oc.3dkiff.org, sd.3dkiff.org, slvkwnews.kw.ac.kr, smtp.kw.ac.kr, smtp1.kw.ac.kr, smtp2.kw.ac.kr, vr.3dkiff.org, webdisk.3dkiff.org, webmail.3dkiff.org, webmail.kw.ac.kr, wildcard.libproxy.kw.ac.kr, wmail.kw.ac.kr, www-dbpia-co-kr.libproxy.kw.ac.kr, www-earticle-net.libproxy.kw.ac.kr, www.3dkiff.org, www.crm.3dkiff.org, www.libproxy.kw.ac.kr, www.oc.3dkiff.org, www.sd.3dkiff.org, www.sso.kwuniv.com, www.vr.3dkiff.org
- **옛 웹호스팅 안내 페이지** (62): abeek.kw.ac.kr, adhoc.kw.ac.kr, air.kw.ac.kr, allsports.kw.ac.kr, analysis.kw.ac.kr, annals.kw.ac.kr, awst.kw.ac.kr, baseball.kw.ac.kr, bi.kw.ac.kr, bklee.kw.ac.kr, ce95.kw.ac.kr, cemlab.kw.ac.kr, cheer.kw.ac.kr, chinese.kw.ac.kr, cis.kw.ac.kr, cm21.kw.ac.kr, conea.kw.ac.kr, dongari.kw.ac.kr, eem.kw.ac.kr, ewal.kw.ac.kr, fs.kw.ac.kr, gosi.kw.ac.kr, hbchung.kw.ac.kr, hklee.kw.ac.kr, human.kw.ac.kr, jcci.kw.ac.kr, kspc07.kw.ac.kr, kusa.kw.ac.kr, kw70th.kw.ac.kr, kwac.kw.ac.kr, kwm.kw.ac.kr, kwmedia.kw.ac.kr, kwsel.kw.ac.kr, kyungbok.kw.ac.kr, lawlab.kw.ac.kr, mathematics.kw.ac.kr, mis.kw.ac.kr, mmedia.kw.ac.kr, mpm21.kw.ac.kr, msdl.kw.ac.kr, mwantenna.kw.ac.kr, nosound.kw.ac.kr, nsrl.kw.ac.kr, pic.kw.ac.kr, point.kw.ac.kr, powerlab.kw.ac.kr, rebt.kw.ac.kr, rfic.kw.ac.kr, rficlab.kw.ac.kr, rfmdl.kw.ac.kr, sarang.kw.ac.kr, sicogg9.kw.ac.kr, srslab.kw.ac.kr, srwct.kw.ac.kr, ssd.kw.ac.kr, tg.kw.ac.kr, theochem.kw.ac.kr, tyoung.kw.ac.kr, tyy.kw.ac.kr, wnlab.kw.ac.kr, youthlab.kw.ac.kr, zeus.kw.ac.kr

