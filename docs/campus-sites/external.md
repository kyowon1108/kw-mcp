# 광운대 학생이 쓰는 외부 사이트·앱·채널

조사일 2026-11-07. www.kw.ac.kr 밖에서 학생들이 학교 정보를 얻는 곳을 모았다. 데이터는 같은 폴더의 `external.json`에 있다.

## 조사 방법

- **웹 검색**: 한국어·영어 검색, 학교 메인 페이지와 학생자치기구 소개 페이지(activity01~10)의 외부 링크, 광운대신문 기사.
- **GitHub**: `gh search repos` 18개 검색어, `gh search code` 13개 검색어(klas.kw.ac.kr, mobileid, happydorm, facility11 등). 걸린 저장소 중 학교 정보와 관련된 것만 메타데이터를 따로 확인했다.
- **생존 확인**: 주소마다 GET 1회, UA `kw-campus-research (contact kyowon1108@gmail.com)`, 요청 간격 3초. 인스타그램·페이스북은 자동 확인하지 않았다(`미확인`).
- GitHub에만 있는 프로젝트의 상태는 커밋 날짜로 판단했다. 최근 1년 안에 커밋이 있으면 `살아 있음`, 아카이브됐거나 2년 넘게 멈췄으면 `없음·중단`, 그 사이는 `미확인`. 스토어·사이트가 404이거나 배포가 꺼진 것도 `없음·중단`이다.

## 숫자

- 전체 125곳: 공식 67, 학생 제작·운영 49, 외부 업체·플랫폼 9.
- 상태: 살아 있음 95, 죽음·중단 13, 미확인 17.
- 로드맵에 있던 곳 52, 브리프에서 이미 안다고 한 곳 5, **놓친 곳 70**.

## 놓친 곳

로드맵(docs/campus-roadmap.md)에 없고, 브리프에서 이미 안다고 한 것(daple, openklas, KLAS Helper, KW-Graduation)도 아닌 곳이다.

### 가장 쓸모 있는 15곳

1. **[KLAS+ (Android·iOS·웹뷰)](https://play.google.com/store/apps/details?id=com.icecream.kwklasplus)** (학생, 살아 있음). 학생이 만든 KLAS 대체 앱. 광운대신문이 개발자 인터뷰를 실었다. iOS판 코드는 2026년에 들어갔지만 App Store 주소는 아직 404다.
2. **[광운대 알리미 (웹 + Telegram 채널 @kw_alert)](https://viban0.github.io/kwalertweb/)** (학생, 살아 있음). 25학번이 만든 Telegram 공지 채널. 공지 알림, 아침 학사일정 브리핑, 학식까지 kw-campus 알림 기능과 거의 겹친다. 수집 저장소가 오늘(11-07)도 커밋됐다.
3. **[경력개발팀 Instagram (@kwu_career)](https://www.instagram.com/kwu_career)** (공식, 미확인). 경력개발팀이 2026학년도부터 취업정보를 모두 인스타로 내보낸다고 공지했다. job.kw.ac.kr만 보면 놓친다.
4. **[광운대 시간표 웹앱 (kw-timetable-2602)](https://ga111o.github.io/kw-timetable-2602/)** (학생, 살아 있음). 개설강좌로 시간표를 짜는 학생 제작 웹앱.
5. **[kw_mcp (공지·학식·열람실·집현전 MCP)](https://github.com/ksj804702/kw_mcp)** (학생, 살아 있음). 다른 학생이 만든 광운대 MCP(공지·학식·열람실·집현전). KLAP·klax·openklas까지 비슷한 프로젝트가 4개 넘게 있다.
6. **[Telegram KLAS 알림 봇 (klas_notification_bot)](https://github.com/snowing152/klas_notification_bot)** (학생, 살아 있음). KLAS 마감·학식·도서관 QR을 Telegram으로 보내는 봇. 사용자가 KLAS 계정을 봇에 넣는 구조라 로드맵이 피하기로 한 방식이다.
7. **[KW 알리미 (Android v2)](https://play.google.com/store/apps/details?id=dev.yjyoon.kwnotice)** (학생, 살아 있음). 로드맵에는 iOS판만 있다. Android판(Play, dev.yjyoon.kwnotice)도 살아 있다.
8. **[단과대·학부(과) 인스타그램 계정 목록 (총학 공지)](https://www.kwu-studentcouncil.co.kr/notices/cl1789744600036r7qi59t)** (학생, 살아 있음). 총학이 2026학년도 단과대·학과 인스타 계정을 정리해 공지했다. SNS 안내문 목록을 채울 출처다(목록 본문은 인스타 카드뉴스).
9. **[교환학생 네이버 카페 (kwexchange)](https://cafe.naver.com/kwexchange)** (공식, 살아 있음). 파견 학생은 생활보고서를 이 카페에 올려야 학점이 인정된다. 선배 후기도 여기에 모인다.
10. **[광운대학교 총동문회 (kwuaa.com)](https://www.kwuaa.com/)** (공식, 살아 있음). 총동문회 장학금 공고처.
11. **[광운대학교 공식 AI 챗봇 (www.kw.ac.kr 우측 하단)](https://www.kw.ac.kr/ko/)** (공식, 살아 있음). 홈페이지에 Mindlogic informe 챗봇이 붙어 있다. 학교가 이미 "홈페이지 Q&A AI"를 외부 업체로 운영한다는 뜻이다.
12. **[KW Pass (Wear OS·폰 도서관 QR)](https://github.com/kw-service/kw-pass-wearos)** (학생, 살아 있음). 도서관 출입 QR을 워치·위젯으로 띄우는 앱. 다른 도서관 대체 도구 중 집현전 예약현황 API는 배포가 꺼져 있다.
13. **[IDEC 캘린더](https://chb09876.github.io/IDEC_Calendar/)** (학생, 살아 있음). 반도체설계교육센터 강의 일정을 모은 학생 제작 캘린더. 전자 계열 학생 수요가 있다.
14. **[유니뷰 (대학 공지 모아보기 앱)](https://allconnect.andro.io/)** (외부, 살아 있음). 여러 대학 공지를 한 앱에서 키워드 알림으로 받는 외부 앱. 지원 학교 목록에 광운대가 있다. 스토어 주소는 찾지 못했고 APK 미러 페이지만 확인했다.
15. **[총동아리연합회 (Instagram @kw_club_union, 네이버 카페 kwucdy)](https://www.instagram.com/kw_club_union)** (학생, 살아 있음). 중앙동아리 공지 창구. 학교 동아리 페이지에는 동아리별 인스타·노션·디스코드·linktree가 약 40개 링크돼 있다.

### 놓친 곳 전체

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [KLAP (CLI·macOS·MCP)](https://github.com/leehyowon14/KLAP-cli) | KLAS 비공식 클라이언트. 공지·과제·강의 검색, 마감 통합, 온라인강의 다운로드·전사, 미리알림 연동, ChatGPT/MCP 연동 | 학생 | 살아 있음 | KLAS 계정(OS 키체인 저장) | 아니오 |
| [klas-flow (Dart/Flutter KLAS SDK)](https://github.com/jungwuk-ryu/klas-flow) | KLAS를 Flutter 앱에서 쓰는 고수준 SDK | 학생 | 살아 있음 | KLAS 계정 | 아니오 |
| [klax (KLAS MCP·CLI)](https://github.com/goonbam0306/klax) | KLAS MCP 서버와 CLI 비서 | 학생 | 살아 있음 | KLAS 계정 | 아니오 |
| [kw_mcp (공지·학식·열람실·집현전 MCP)](https://github.com/ksj804702/kw_mcp) | 공지 검색·본문, 학식, 열람실 빈자리, 집현전 예약 가능 시간 MCP | 학생 | 살아 있음 | 없음(공개 데이터) | 아니오 |
| [KLAS Helper Plus (klas-helper-extension-plus)](https://github.com/jundragon7419/klas-helper-extension-plus) | 과제·강의·팀프로젝트·퀴즈 마감을 툴바 배지와 사이드 패널로 보여 주고 알림 | 학생 | 살아 있음 | KLAS 웹 로그인 | 아니오 |
| [KLAS+ (Android·iOS·웹뷰)](https://play.google.com/store/apps/details?id=com.icecream.kwklasplus) | KLAS 모바일 앱 대체. 시간표·다음 수업·건물명, 미제출 과제·미수강 온라인강의, 학사일정 캘린더, 학식, 모바일 학생증·도서관 QR 위젯, QR 출석, 성적·석차, KLAS AI | 학생 | 살아 있음 | KLAS 학번·비밀번호(앱이 KLAS에 직접 로그인, 자체 서버 저장 없다고 밝힘) | 아니오 |
| [KW Auto (크롬 확장)](https://chromewebstore.google.com/detail/kw-auto/lbnhabebmehjhmandmeaijackijmmlkl) | KLAS 자동 로그인, 과제 진행도 표시, 시간표 접기/펴기 | 학생 | 살아 있음 | KLAS 계정(자동 로그인용 저장) | 아니오 |
| [KlasPlugin (크롬 확장)](https://chromewebstore.google.com/detail/klasplugin/nbfleghpmjokcjfdkelooeabmhmiplpf) | KLAS에 들어가지 않고 확장 팝업에서 KLAS 정보 확인 | 학생 | 살아 있음 | KLAS 계정 | 아니오 |
| [OpenKLAS (안드로이드 서드파티 클라이언트)](https://github.com/onebone/OpenKLAS) | KLAS 안드로이드 대체 클라이언트(소스 공개) | 학생 | 살아 있음 | KLAS 계정 | 아니오 |
| [KLAS+ iOS](https://apps.apple.com/app/id6820491776) | KLAS+의 iOS판(Kotlin Multiplatform 전환 후 2026년 추가) | 학생 | 없음·중단 | KLAS 계정 | 아니오 |
| [K-MOOC](https://www.kmooc.kr/) | 학점 인정 K-MOOC 과목 수강 | 외부 | 살아 있음 | 예 | 아니오 |
| [KW Commons (온라인 강의 콘텐츠)](https://kwcommons.kw.ac.kr/) | KLAS 온라인강의 동영상 플랫폼 | 공식 | 살아 있음 | 예 | 아니오 |
| [KW MOOC](https://kwmooc.kw.ac.kr/) | 학교 자체 MOOC 강좌 | 공식 | 살아 있음 | 예(수강) | 아니오 |
| [PC 원격지원 (ezHelp, 9011.co.kr/kwu)](http://9011.co.kr/kwu/) | 메인 페이지 하단에 링크된 IT 원격지원(ezHelp ID kwu) | 외부 | 살아 있음 | 상담원 연결 | 아니오 |
| [광운e러닝 (kw.ubob.com)](https://kw.ubob.com/) | 메인 페이지에 링크된 유밥(ubob) 운영 "광운e러닝" 사이트. 유밥이 이러닝·법정교육 업체라 법정의무교육·비교과 온라인강좌용으로 보임 | 외부 | 살아 있음 | 예(추정) | 아니오 |
| [국가인적자원개발센터 (kwhrd.com)](http://www.kwhrd.com/) | 재직자·직업훈련 과정(재학생 대상 아님) | 공식 | 살아 있음 | 예(수강) | 아니오 |
| [동해문화예술관](http://dac.kw.ac.kr/main/main.php) | 공연장 대관·공연 안내 | 공식 | 살아 있음 | 없음 | 아니오 |
| [발전기금](https://fund.kw.ac.kr/) | 기부·장학 기부 소식 | 공식 | 살아 있음 | 없음 | 아니오 |
| [안전교육 시스템](https://safety.kw.ac.kr/) | 연구실 안전교육 등 | 공식 | 살아 있음 | 예 | 아니오 |
| [웹메일](https://wmail.kw.ac.kr/) | kw.ac.kr 메일 | 공식 | 살아 있음 | 예 | 아니오 |
| [입학처](http://iphak.kw.ac.kr/) | 입시(재학생 대상 아님) | 공식 | 살아 있음 | 없음 | 아니오 |
| [광운학원 재단](https://www.kwangwoonfoundation.org/) | 학교법인 소식 | 공식 | 미확인 | 없음 | 아니오 |
| [아이스링크](http://icerink.kw.ac.kr/) | 교내 아이스링크 대관 | 공식 | 미확인 | ? | 아니오 |
| [광운대 공식 YouTube](https://www.youtube.com/channel/UC0M-8Ruuz1YJD7-z9mv92_g) | 학교 영상 | 공식 | 살아 있음 | 없음 | 아니오 |
| [광운대 공식 블로그 (네이버)](https://m.blog.naver.com/kwu1934) | 홍보 기사 | 공식 | 살아 있음 | 없음 | 아니오 |
| [광운대학교 공식 AI 챗봇 (www.kw.ac.kr 우측 하단)](https://www.kw.ac.kr/ko/) | 홈페이지 정보 Q&A 챗봇. 외부 업체 Mindlogic informe 플러그인(plugin.mindlogic.ai, 봇 ID kw-4954) | 공식 | 살아 있음 | 없음 | 아니오 |
| [광운대 공식 Instagram (@kwangwoon_univ_official)](https://www.instagram.com/kwangwoon_univ_official/) | 학교 홍보·행사 | 공식 | 미확인 | 인스타그램 | 아니오 |
| [KW Notification Discord Bot](https://github.com/y-praise/KW_Notification_Discord_Bot) | 광운대 공지를 디스코드로 알림 | 학생 | 살아 있음 | 디스코드 서버 초대 필요 | 아니오 |
| [KW 알리미 (Android v2)](https://play.google.com/store/apps/details?id=dev.yjyoon.kwnotice) | 메인 공지·SW중심대학사업단 공지 실시간 푸시, 즐겨찾기 | 학생 | 살아 있음 | 없음 | 아니오 |
| [Telegram KLAS 알림 봇 (klas_notification_bot)](https://github.com/snowing152/klas_notification_bot) | KLAS 마감 알림·대시보드, 학식, 학교 소식, 도서관 검색·QR을 Telegram으로(영·한·러) | 학생 | 살아 있음 | KLAS 계정을 봇에 입력 | 아니오 |
| [광운대 알리미 (웹 + Telegram 채널 @kw_alert)](https://viban0.github.io/kwalertweb/) | 학교 공지 실시간 알림, 매일 아침 학사일정 브리핑(D-day), 오늘의 학식을 Telegram 채널로. 구독자 75명(11-07), 매일 게시 | 학생 | 살아 있음 | 없음(Telegram 채널 구독) | 아니오 |
| [K-NET 디스코드 봇](https://github.com/KNET-KWU/discord-bot) | K-NET 동아리 디스코드 광운대 봇 | 학생 | 없음·중단 | 디스코드 | 아니오 |
| [iNoti (키워드 공지 알림)](https://github.com/dosp74/iNoti) | 키워드 기반 광운대 공지 알림 | 학생 | 미확인 | 미확인 | 아니오 |
| [광운대 공지 RSS (feedburner)](http://feeds.feedburner.com/KWUNotice) | 메인 공지·소프트웨어학부 공지·총학 페이스북 RSS | 학생 | 없음·중단 | 없음 | 아니오 |
| [KW 기숙사 앱](https://github.com/kw-dormitory) | 기숙사(행복기숙사) 공지 알림 앱 | 학생 | 없음·중단 | 없음 | 아니오 |
| [KW Pass (Wear OS·폰 도서관 QR)](https://github.com/kw-service/kw-pass-wearos) | 갤럭시워치 등에서 도서관 출입 QR, 폰 위젯·루틴 자동화 | 학생 | 살아 있음 | 도서관 계정 | 아니오 |
| [중앙도서관 API 서버 (Kwangwoon-Univ_Library)](https://github.com/leehyowon14/Kwangwoon-Univ_Library) | 도서관 기능을 API로 감싼 서버(express) | 학생 | 살아 있음 | 도서관 계정 추정 | 아니오 |
| [KW 마이시트 (iOS)](https://github.com/KW-My-Sheet/ios) | 중앙도서관 자리 예약 알림 | 학생 | 없음·중단 | 미확인 | 아니오 |
| [도서관 Q&A 챗봇 (kwu-lib-chatbot)](https://github.com/chic-tutoring/kwu-lib-chatbot) | 도서관 이용 Q&A 챗봇 프로젝트 | 학생 | 미확인 | - | 아니오 |
| [집현전(그룹스터디룸) 예약현황 API](https://kw-library-jiphyeonjeon.vercel.app/docs) | 그룹스터디룸 예약 현황 조회 API | 학생 | 없음·중단 | 없음 | 아니오 |
| [NowonLikeUs (월계동 생활 안내)](https://nowonlikeus.vercel.app/) | 월계1동 전입자 생활 안내(2026 KW해커톤) | 학생 | 살아 있음 | 없음 | 아니오 |
| [Ravit (광운대 생활 가이드 사이트)](https://ravit.co.kr/) | 광운대 학생용 안내 사이트(도서관·공지·기숙사 링크 모음) | 학생 | 살아 있음 | 없음 | 아니오 |
| [교통약자용 캠퍼스 안내 (KWU_campus_map)](https://github.com/rbqja7933/KWU_campus_map) | 교통약자를 위한 캠퍼스 안내 시스템 | 학생 | 살아 있음 | - | 아니오 |
| [막카 (버스 정류장 정보)](https://makka.co.kr/bus/seoul/11285) | 광운대학교 정류장(11285) 노선·첫차·막차 | 외부 | 살아 있음 | 없음 | 아니오 |
| [BROOM (예비군 종합 서비스)](https://broom.life/) | 광운대 예비군 정보 서비스(2024 동아리 연합 해커톤 대상) | 학생 | 미확인 | 미확인 | 아니오 |
| [광슐랭 (주변 맛집)](https://kwang-chelin.vercel.app/) | 광운대 주변 식당 정보·룰렛 | 학생 | 없음·중단 | 없음 | 아니오 |
| [유니뷰 (대학 공지 모아보기 앱)](https://allconnect.andro.io/) | 여러 대학 공지를 한 앱에서, 키워드 알림. 지원 학교 목록에 광운대 포함 | 외부 | 살아 있음 | 없음 | 아니오 |
| [캠퍼스픽](https://www.campuspick.com/) | 공모전·대외활동·대학생 커뮤니티 | 외부 | 살아 있음 | 선택 | 아니오 |
| [나무위키 광운대학교 문서](https://namu.wiki/w/%EA%B4%91%EC%9A%B4%EB%8C%80%ED%95%99%EA%B5%90) | 교통·학생자치·건물 등 비공식 정리 | 외부 | 미확인 | 없음 | 아니오 |
| [IDEC 캘린더](https://chb09876.github.io/IDEC_Calendar/) | 반도체설계교육센터(IDEC) 강의 일정·신청기간 캘린더 | 학생 | 살아 있음 | 없음 | 아니오 |
| [광운대 수강신청 도우미 (kwangwoon-course-helper)](https://github.com/MuuiGong/kwangwoon-course-helper) | 수강신청 도우미(내용 미확인) | 학생 | 살아 있음 | 미확인 | 아니오 |
| [광운대 시간표 웹앱 (kw-timetable-2602)](https://ga111o.github.io/kw-timetable-2602/) | 개설강좌로 시간표 짜기 | 학생 | 살아 있음 | 없음 | 아니오 |
| [학업나침반 (기술과경영 2조)](https://tech-management-team2.vercel.app/) | 수강 조합의 학기 부담 진단과 관심분야 수강 로드맵 | 학생 | 살아 있음 | 미확인 | 아니오 |
| [KLtime (강의·시간표 추천)](https://github.com/19-21-40) | 학생 맞춤 강의·시간표 추천 웹서비스 | 학생 | 없음·중단 | KLAS 계정(코드에 KLAS 로그인) | 아니오 |
| [SW학부 졸업심사 도우미 (graduate-helper)](https://github.com/ssahn0806/graduate-helper) | KLAS 수강·성적으로 소프트웨어학부 졸업요건 잔여학점 계산 | 학생 | 없음·중단 | KLAS 계정(로컬 Selenium) | 아니오 |
| [광운대 강의계획서 검색기 (kw-syllabus)](https://0420syj.github.io/kw-syllabus/) | 강의계획서 검색 | 학생 | 없음·중단 | 없음 | 아니오 |
| [광운대 수강신청 연습 프로그램](https://github.com/kw-service/kw-class-registration) | 수강신청 화면 연습(Windows) | 학생 | 없음·중단 | 없음 | 아니오 |
| [KW Times (영자신문)](https://kwnews.kw.ac.kr/index2.html?editcode=MAIN_12) | 영문 학보 | 공식 | 살아 있음 | 없음 | 아니오 |
| [KWBC 광운영상방송센터 YouTube](https://www.youtube.com/user/KWBConair) | 광운뉴스·교내 행사 영상 | 공식 | 살아 있음 | 없음 | 아니오 |
| [KIF (외국인 유학생 멘토단)](https://oia.kw.ac.kr/campus/KIF.php) | 유학생 행사·언어교환·멘토링. 공지는 KIF 인스타그램 | 공식 | 살아 있음 | 없음 | 아니오 |
| [광운대학교 총동문회 (kwuaa.com)](https://www.kwuaa.com/) | 총동문회 장학생 선발, 동문 소식 | 공식 | 살아 있음 | 없음 | 아니오 |
| [교환학생 네이버 카페 (kwexchange)](https://cafe.naver.com/kwexchange) | 교환학생 선배 후기·파견 정보. 파견 중 생활보고서를 여기에 올려야 학점 인정 | 공식 | 살아 있음 | 네이버 + 학번 입력 가입 | 아니오 |
| [반도체설계교육센터 IDEC](https://www.idec.or.kr/) | 반도체 설계 외부교육(전자과 학생이 많이 신청) | 외부 | 살아 있음 | 예(신청) | 아니오 |
| [경력개발팀 Instagram (@kwu_career)](https://www.instagram.com/kwu_career) | 취업정보 전부를 2026학년도부터 인스타그램으로 제공한다고 공지(DUID 51947) | 공식 | 미확인 | 인스타그램 | 아니오 |
| [단과대·학부(과) 인스타그램 계정 목록 (총학 공지)](https://www.kwu-studentcouncil.co.kr/notices/cl1789744600036r7qi59t) | 2026학년도 단과대·학과 학생회 인스타그램 계정 안내 | 학생 | 살아 있음 | 없음 | 아니오 |
| [졸업준비위원회 카카오톡 채널](http://pf.kakao.com/_CnFST/chat) | 학위복·졸업앨범 등 졸업 준비 문의 | 학생 | 살아 있음 | 카카오톡 | 아니오 |
| [중앙동아리 인스타그램·사이트 모음 (약 40개)](https://www.kw.ac.kr/ko/life/activity03.jsp) | 학교 동아리 소개 페이지가 동아리별 인스타·카페·노션·디스코드·linktree를 링크 | 학생 | 살아 있음 | 채널마다 다름 | 아니오 |
| [총동아리연합회 (Instagram @kw_club_union, 네이버 카페 kwucdy)](https://www.instagram.com/kw_club_union) | 중앙동아리 모집·행사 | 학생 | 살아 있음 | 인스타그램/네이버 | 아니오 |
| [코딩동아리 COM's 사이트](https://coms.kw.ac.kr/) | 동아리 사이트·도구 호스팅 | 학생 | 살아 있음 | 없음 | 아니오 |
| [사회봉사단 Instagram (@kw_volunteer)](https://www.instagram.com/kw_volunteer) | 봉사단 모집·활동 | 공식 | 미확인 | 인스타그램 | 아니오 |

## 용도별 전체 목록

### KLAS 보조 앱·확장

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [KLAS+ (Android·iOS·웹뷰)](https://play.google.com/store/apps/details?id=com.icecream.kwklasplus) | KLAS 모바일 앱 대체. 시간표·다음 수업·건물명, 미제출 과제·미수강 온라인강의, 학사일정 캘린더, 학식, 모바일 학생증·도서관 QR 위젯, QR 출석, 성적·석차, KLAS AI | 학생 | 살아 있음 | KLAS 학번·비밀번호(앱이 KLAS에 직접 로그인, 자체 서버 저장 없다고 밝힘) | 아니오 |
| [KLAS+ iOS](https://apps.apple.com/app/id6820491776) | KLAS+의 iOS판(Kotlin Multiplatform 전환 후 2026년 추가) | 학생 | 없음·중단 | KLAS 계정 | 아니오 |
| [KLAS Helper (브라우저 확장)](https://chromewebstore.google.com/detail/klas-helper/jicidjkhiefbhbgbfbemakjndloecjlf) | KLAS 웹에 강의계획서 새 창, 전공/전공외 평점 계산, 석차, 미시청·미제출 목록, 강의 배속 등을 추가 | 학생 | 살아 있음 | KLAS 웹 로그인 상태에서 동작 | 예 |
| [KLAS Helper Plus (klas-helper-extension-plus)](https://github.com/jundragon7419/klas-helper-extension-plus) | 과제·강의·팀프로젝트·퀴즈 마감을 툴바 배지와 사이드 패널로 보여 주고 알림 | 학생 | 살아 있음 | KLAS 웹 로그인 | 아니오 |
| [KW Auto (크롬 확장)](https://chromewebstore.google.com/detail/kw-auto/lbnhabebmehjhmandmeaijackijmmlkl) | KLAS 자동 로그인, 과제 진행도 표시, 시간표 접기/펴기 | 학생 | 살아 있음 | KLAS 계정(자동 로그인용 저장) | 아니오 |
| [KlasPlugin (크롬 확장)](https://chromewebstore.google.com/detail/klasplugin/nbfleghpmjokcjfdkelooeabmhmiplpf) | KLAS에 들어가지 않고 확장 팝업에서 KLAS 정보 확인 | 학생 | 살아 있음 | KLAS 계정 | 아니오 |
| [OpenKLAS (안드로이드 서드파티 클라이언트)](https://github.com/onebone/OpenKLAS) | KLAS 안드로이드 대체 클라이언트(소스 공개) | 학생 | 살아 있음 | KLAS 계정 | 아니오 |

### 공지·알림

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [Telegram KLAS 알림 봇 (klas_notification_bot)](https://github.com/snowing152/klas_notification_bot) | KLAS 마감 알림·대시보드, 학식, 학교 소식, 도서관 검색·QR을 Telegram으로(영·한·러) | 학생 | 살아 있음 | KLAS 계정을 봇에 입력 | 아니오 |
| [광운대 알리미 (웹 + Telegram 채널 @kw_alert)](https://viban0.github.io/kwalertweb/) | 학교 공지 실시간 알림, 매일 아침 학사일정 브리핑(D-day), 오늘의 학식을 Telegram 채널로. 구독자 75명(11-07), 매일 게시 | 학생 | 살아 있음 | 없음(Telegram 채널 구독) | 아니오 |
| [KW 알리미 (iOS)](https://apps.apple.com/kr/app/id1634571259) | 메인 공지·SW중심대학사업단 공지 등록/수정 푸시 | 학생 | 살아 있음 | 없음 | 예 |
| [KW 알리미 (Android v2)](https://play.google.com/store/apps/details?id=dev.yjyoon.kwnotice) | 메인 공지·SW중심대학사업단 공지 실시간 푸시, 즐겨찾기 | 학생 | 살아 있음 | 없음 | 아니오 |
| [iNoti (키워드 공지 알림)](https://github.com/dosp74/iNoti) | 키워드 기반 광운대 공지 알림 | 학생 | 미확인 | 미확인 | 아니오 |
| [KW Notification Discord Bot](https://github.com/y-praise/KW_Notification_Discord_Bot) | 광운대 공지를 디스코드로 알림 | 학생 | 살아 있음 | 디스코드 서버 초대 필요 | 아니오 |
| [K-NET 디스코드 봇](https://github.com/KNET-KWU/discord-bot) | K-NET 동아리 디스코드 광운대 봇 | 학생 | 없음·중단 | 디스코드 | 아니오 |
| [광운대 공지 RSS (feedburner)](http://feeds.feedburner.com/KWUNotice) | 메인 공지·소프트웨어학부 공지·총학 페이스북 RSS | 학생 | 없음·중단 | 없음 | 아니오 |

### 시간표·수강·졸업

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [KW-Graduation (크롬 확장)](https://chromewebstore.google.com/detail/kw-graduation/fedlhlkkbmflfhmeffadldpojnielkgn) | 졸업요건 시뮬레이터·남은 학점·성적 계산(일부 학과만) | 학생 | 살아 있음 | KLAS 웹 로그인 | 예 |
| [광운대 시간표 웹앱 (kw-timetable-2602)](https://ga111o.github.io/kw-timetable-2602/) | 개설강좌로 시간표 짜기 | 학생 | 살아 있음 | 없음 | 아니오 |
| [광운대 수강신청 연습 프로그램](https://github.com/kw-service/kw-class-registration) | 수강신청 화면 연습(Windows) | 학생 | 없음·중단 | 없음 | 아니오 |
| [광운대 강의계획서 검색기 (kw-syllabus)](https://0420syj.github.io/kw-syllabus/) | 강의계획서 검색 | 학생 | 없음·중단 | 없음 | 아니오 |
| [학업나침반 (기술과경영 2조)](https://tech-management-team2.vercel.app/) | 수강 조합의 학기 부담 진단과 관심분야 수강 로드맵 | 학생 | 살아 있음 | 미확인 | 아니오 |
| [KLtime (강의·시간표 추천)](https://github.com/19-21-40) | 학생 맞춤 강의·시간표 추천 웹서비스 | 학생 | 없음·중단 | KLAS 계정(코드에 KLAS 로그인) | 아니오 |
| [광운대 수강신청 도우미 (kwangwoon-course-helper)](https://github.com/MuuiGong/kwangwoon-course-helper) | 수강신청 도우미(내용 미확인) | 학생 | 살아 있음 | 미확인 | 아니오 |
| [SW학부 졸업심사 도우미 (graduate-helper)](https://github.com/ssahn0806/graduate-helper) | KLAS 수강·성적으로 소프트웨어학부 졸업요건 잔여학점 계산 | 학생 | 없음·중단 | KLAS 계정(로컬 Selenium) | 아니오 |
| [IDEC 캘린더](https://chb09876.github.io/IDEC_Calendar/) | 반도체설계교육센터(IDEC) 강의 일정·신청기간 캘린더 | 학생 | 살아 있음 | 없음 | 아니오 |
| [다전공 플래너 (daple)](https://daple.kwuniv.com/) | 다전공(복수·부·연계전공) 계획 도구. 기획처 대학혁신사업단 운영, 자체 SSO(sso.kwuniv.com) | 공식 | 살아 있음 | SSO 로그인 | 아니오 |
| [kwuniv.com SSO](https://sso.kwuniv.com/) | daple용 별도 로그인 | 공식 | 미확인 | 예 | 아니오 |

### AI·MCP·CLI

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [openklas (MCP 서버)](https://openklas.com/) | KLAS를 AI 도구에 붙이는 MCP 서버 | 학생 | 살아 있음 | KLAS 계정 | 아니오 |
| [KLAP (CLI·macOS·MCP)](https://github.com/leehyowon14/KLAP-cli) | KLAS 비공식 클라이언트. 공지·과제·강의 검색, 마감 통합, 온라인강의 다운로드·전사, 미리알림 연동, ChatGPT/MCP 연동 | 학생 | 살아 있음 | KLAS 계정(OS 키체인 저장) | 아니오 |
| [klax (KLAS MCP·CLI)](https://github.com/goonbam0306/klax) | KLAS MCP 서버와 CLI 비서 | 학생 | 살아 있음 | KLAS 계정 | 아니오 |
| [kw_mcp (공지·학식·열람실·집현전 MCP)](https://github.com/ksj804702/kw_mcp) | 공지 검색·본문, 학식, 열람실 빈자리, 집현전 예약 가능 시간 MCP | 학생 | 살아 있음 | 없음(공개 데이터) | 아니오 |
| [klas-flow (Dart/Flutter KLAS SDK)](https://github.com/jungwuk-ryu/klas-flow) | KLAS를 Flutter 앱에서 쓰는 고수준 SDK | 학생 | 살아 있음 | KLAS 계정 | 아니오 |

### 도서관·열람실

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [광운대학교 중앙도서관 앱](https://play.google.com/store/apps/details?id=idoit.slpck.kwangwoon) | 모바일 이용증(출입 QR), 좌석·대출 | 공식 | 살아 있음 | 도서관 계정 | 예 |
| [KW Pass (Wear OS·폰 도서관 QR)](https://github.com/kw-service/kw-pass-wearos) | 갤럭시워치 등에서 도서관 출입 QR, 폰 위젯·루틴 자동화 | 학생 | 살아 있음 | 도서관 계정 | 아니오 |
| [집현전(그룹스터디룸) 예약현황 API](https://kw-library-jiphyeonjeon.vercel.app/docs) | 그룹스터디룸 예약 현황 조회 API | 학생 | 없음·중단 | 없음 | 아니오 |
| [중앙도서관 API 서버 (Kwangwoon-Univ_Library)](https://github.com/leehyowon14/Kwangwoon-Univ_Library) | 도서관 기능을 API로 감싼 서버(express) | 학생 | 살아 있음 | 도서관 계정 추정 | 아니오 |
| [KW 마이시트 (iOS)](https://github.com/KW-My-Sheet/ios) | 중앙도서관 자리 예약 알림 | 학생 | 없음·중단 | 미확인 | 아니오 |
| [K-NET 열람실 API](https://github.com/KNET-KWU/kwu-readingroom-api) | 오픈열람실 좌석 API | 학생 | 없음·중단 | 없음 | 예 |
| [도서관 Q&A 챗봇 (kwu-lib-chatbot)](https://github.com/chic-tutoring/kwu-lib-chatbot) | 도서관 이용 Q&A 챗봇 프로젝트 | 학생 | 미확인 | - | 아니오 |

### 학식

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [학식 주간 식단 (함지마루)](https://www.kw.ac.kr/ko/life/facility11.jsp) | 천원의 아침·자율중식·푸드코트 주간 메뉴 | 공식 | 살아 있음 | 없음 | 예 |

### 기숙사

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [KW 기숙사 앱](https://github.com/kw-dormitory) | 기숙사(행복기숙사) 공지 알림 앱 | 학생 | 없음·중단 | 없음 | 아니오 |
| [행복기숙사(빛솔재) 사이트](https://kw.happydorm.or.kr/) | 기숙사 공지, 입사·합격 조회, 외박 신청 | 공식 | 살아 있음 | 공지 공개, 신청·조회는 로그인 | 예 |

### 생활

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [셔틀버스 안내 (교통안내 페이지)](https://www.kw.ac.kr/ko/tour/directions.jsp) | 석계역·태릉입구역 무료 셔틀(평일 08:00~10:30) | 공식 | 살아 있음 | 없음 | 예 |
| [막카 (버스 정류장 정보)](https://makka.co.kr/bus/seoul/11285) | 광운대학교 정류장(11285) 노선·첫차·막차 | 외부 | 살아 있음 | 없음 | 아니오 |
| [광슐랭 (주변 맛집)](https://kwang-chelin.vercel.app/) | 광운대 주변 식당 정보·룰렛 | 학생 | 없음·중단 | 없음 | 아니오 |
| [BROOM (예비군 종합 서비스)](https://broom.life/) | 광운대 예비군 정보 서비스(2024 동아리 연합 해커톤 대상) | 학생 | 미확인 | 미확인 | 아니오 |
| [Ravit (광운대 생활 가이드 사이트)](https://ravit.co.kr/) | 광운대 학생용 안내 사이트(도서관·공지·기숙사 링크 모음) | 학생 | 살아 있음 | 없음 | 아니오 |
| [NowonLikeUs (월계동 생활 안내)](https://nowonlikeus.vercel.app/) | 월계1동 전입자 생활 안내(2026 KW해커톤) | 학생 | 살아 있음 | 없음 | 아니오 |
| [교통약자용 캠퍼스 안내 (KWU_campus_map)](https://github.com/rbqja7933/KWU_campus_map) | 교통약자를 위한 캠퍼스 안내 시스템 | 학생 | 살아 있음 | - | 아니오 |

### 장학·취업·국제

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [광운대학교 총동문회 (kwuaa.com)](https://www.kwuaa.com/) | 총동문회 장학생 선발, 동문 소식 | 공식 | 살아 있음 | 없음 | 아니오 |
| [경력개발팀 Instagram (@kwu_career)](https://www.instagram.com/kwu_career) | 취업정보 전부를 2026학년도부터 인스타그램으로 제공한다고 공지(DUID 51947) | 공식 | 미확인 | 인스타그램 | 아니오 |
| [교환학생 네이버 카페 (kwexchange)](https://cafe.naver.com/kwexchange) | 교환학생 선배 후기·파견 정보. 파견 중 생활보고서를 여기에 올려야 학점 인정 | 공식 | 살아 있음 | 네이버 + 학번 입력 가입 | 아니오 |
| [KIF (외국인 유학생 멘토단)](https://oia.kw.ac.kr/campus/KIF.php) | 유학생 행사·언어교환·멘토링. 공지는 KIF 인스타그램 | 공식 | 살아 있음 | 없음 | 아니오 |
| [반도체설계교육센터 IDEC](https://www.idec.or.kr/) | 반도체 설계 외부교육(전자과 학생이 많이 신청) | 외부 | 살아 있음 | 예(신청) | 아니오 |

### 학생자치·SNS

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [총학생회 이음 웹사이트](https://www.kwu-studentcouncil.co.kr/) | 총학 공지·행사·제휴 | 학생 | 살아 있음 | 공지 공개 | 예 |
| [총학생회 Instagram (@kwu_studentcouncil)](https://instagram.com/kwu_studentcouncil) | 총학의 사실상 공식 공지 창구. 선착순 사업(예비군 셔틀 등) 신청을 여기서만 받음 | 학생 | 미확인 | 인스타그램 | 예 |
| [총학생회 카카오톡 채널](https://pf.kakao.com/_Cxldyn) | 총학 문의·공지 | 학생 | 살아 있음 | 카카오톡 | 예 |
| [단과대·학부(과) 인스타그램 계정 목록 (총학 공지)](https://www.kwu-studentcouncil.co.kr/notices/cl1789744600036r7qi59t) | 2026학년도 단과대·학과 학생회 인스타그램 계정 안내 | 학생 | 살아 있음 | 없음 | 아니오 |
| [총동아리연합회 (Instagram @kw_club_union, 네이버 카페 kwucdy)](https://www.instagram.com/kw_club_union) | 중앙동아리 모집·행사 | 학생 | 살아 있음 | 인스타그램/네이버 | 아니오 |
| [중앙동아리 인스타그램·사이트 모음 (약 40개)](https://www.kw.ac.kr/ko/life/activity03.jsp) | 학교 동아리 소개 페이지가 동아리별 인스타·카페·노션·디스코드·linktree를 링크 | 학생 | 살아 있음 | 채널마다 다름 | 아니오 |
| [졸업준비위원회 카카오톡 채널](http://pf.kakao.com/_CnFST/chat) | 학위복·졸업앨범 등 졸업 준비 문의 | 학생 | 살아 있음 | 카카오톡 | 아니오 |
| [사회봉사단 Instagram (@kw_volunteer)](https://www.instagram.com/kw_volunteer) | 봉사단 모집·활동 | 공식 | 미확인 | 인스타그램 | 아니오 |
| [학과·ROTC 인스타그램 (로드맵 기재분)](https://www.instagram.com/kw.142rotc_official) | ROTC, 전자융합공학과(@kw_e_c_e), 전기공학과 인스타·페이스북 | 공식 | 미확인 | 인스타그램 | 예 |
| [국제학부 Facebook 그룹](https://www.facebook.com/groups/264661916941585/) | 국제학부 학과 공지 | 공식 | 미확인 | 페이스북 | 예 |
| [코딩동아리 COM's 사이트](https://coms.kw.ac.kr/) | 동아리 사이트·도구 호스팅 | 학생 | 살아 있음 | 없음 | 아니오 |

### 공식 채널

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [광운대학교 공식 AI 챗봇 (www.kw.ac.kr 우측 하단)](https://www.kw.ac.kr/ko/) | 홈페이지 정보 Q&A 챗봇. 외부 업체 Mindlogic informe 플러그인(plugin.mindlogic.ai, 봇 ID kw-4954) | 공식 | 살아 있음 | 없음 | 아니오 |
| [광운대 공식 Instagram (@kwangwoon_univ_official)](https://www.instagram.com/kwangwoon_univ_official/) | 학교 홍보·행사 | 공식 | 미확인 | 인스타그램 | 아니오 |
| [광운대 공식 YouTube](https://www.youtube.com/channel/UC0M-8Ruuz1YJD7-z9mv92_g) | 학교 영상 | 공식 | 살아 있음 | 없음 | 아니오 |
| [광운대 공식 블로그 (네이버)](https://m.blog.naver.com/kwu1934) | 홍보 기사 | 공식 | 살아 있음 | 없음 | 아니오 |

### 언론·방송

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [KWBC 광운영상방송센터 YouTube](https://www.youtube.com/user/KWBConair) | 광운뉴스·교내 행사 영상 | 공식 | 살아 있음 | 없음 | 아니오 |
| [광운대신문 (국문) 사이트·RSS](https://kwnews.kw.ac.kr/) | 학보 | 공식 | 살아 있음 | 없음 | 예 |
| [KW Times (영자신문)](https://kwnews.kw.ac.kr/index2.html?editcode=MAIN_12) | 영문 학보 | 공식 | 살아 있음 | 없음 | 아니오 |
| [광운소식(광운미디어)](https://news.kw.ac.kr/) | 홍보 기사·소식지 | 공식 | 살아 있음 | 없음 | 예 |

### 공식 연계 서비스

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [광운e러닝 (kw.ubob.com)](https://kw.ubob.com/) | 메인 페이지에 링크된 유밥(ubob) 운영 "광운e러닝" 사이트. 유밥이 이러닝·법정교육 업체라 법정의무교육·비교과 온라인강좌용으로 보임 | 외부 | 살아 있음 | 예(추정) | 아니오 |
| [sw.kw.ac.kr (인공지능융합대학 별칭 주소)](https://sw.kw.ac.kr/) | 옛 SW중심대학 주소. 지금은 aicon.kw.ac.kr의 CNAME이라 같은 인융대 사이트가 열림 | 공식 | 살아 있음 | 없음 | 예 |
| [KW Commons (온라인 강의 콘텐츠)](https://kwcommons.kw.ac.kr/) | KLAS 온라인강의 동영상 플랫폼 | 공식 | 살아 있음 | 예 | 아니오 |
| [KW MOOC](https://kwmooc.kw.ac.kr/) | 학교 자체 MOOC 강좌 | 공식 | 살아 있음 | 예(수강) | 아니오 |
| [K-MOOC](https://www.kmooc.kr/) | 학점 인정 K-MOOC 과목 수강 | 외부 | 살아 있음 | 예 | 아니오 |
| [안전교육 시스템](https://safety.kw.ac.kr/) | 연구실 안전교육 등 | 공식 | 살아 있음 | 예 | 아니오 |
| [웹메일](https://wmail.kw.ac.kr/) | kw.ac.kr 메일 | 공식 | 살아 있음 | 예 | 아니오 |
| [광운학원 재단](https://www.kwangwoonfoundation.org/) | 학교법인 소식 | 공식 | 미확인 | 없음 | 아니오 |
| [발전기금](https://fund.kw.ac.kr/) | 기부·장학 기부 소식 | 공식 | 살아 있음 | 없음 | 아니오 |
| [PC 원격지원 (ezHelp, 9011.co.kr/kwu)](http://9011.co.kr/kwu/) | 메인 페이지 하단에 링크된 IT 원격지원(ezHelp ID kwu) | 외부 | 살아 있음 | 상담원 연결 | 아니오 |
| [동해문화예술관](http://dac.kw.ac.kr/main/main.php) | 공연장 대관·공연 안내 | 공식 | 살아 있음 | 없음 | 아니오 |
| [국가인적자원개발센터 (kwhrd.com)](http://www.kwhrd.com/) | 재직자·직업훈련 과정(재학생 대상 아님) | 공식 | 살아 있음 | 예(수강) | 아니오 |
| [아이스링크](http://icerink.kw.ac.kr/) | 교내 아이스링크 대관 | 공식 | 미확인 | ? | 아니오 |
| [입학처](http://iphak.kw.ac.kr/) | 입시(재학생 대상 아님) | 공식 | 살아 있음 | 없음 | 아니오 |

### 서드파티 플랫폼

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [에브리타임 (광운대)](https://everytime.kr/) | 익명 커뮤니티, 시간표·강의평(강의실)·학점계산기·책방 | 외부 | 살아 있음 | 학교 인증 | 예 |
| [캠퍼스픽](https://www.campuspick.com/) | 공모전·대외활동·대학생 커뮤니티 | 외부 | 살아 있음 | 선택 | 아니오 |
| [유니뷰 (대학 공지 모아보기 앱)](https://allconnect.andro.io/) | 여러 대학 공지를 한 앱에서, 키워드 알림. 지원 학교 목록에 광운대 포함 | 외부 | 살아 있음 | 없음 | 아니오 |
| [나무위키 광운대학교 문서](https://namu.wiki/w/%EA%B4%91%EC%9A%B4%EB%8C%80%ED%95%99%EA%B5%90) | 교통·학생자치·건물 등 비공식 정리 | 외부 | 미확인 | 없음 | 아니오 |

### 로드맵 기재 공식 사이트

| 이름 | 용도 | 구분 | 상태 | 로그인 | 로드맵 |
|---|---|---|---|---|---|
| [중앙도서관 KUPIS](https://kupis.kw.ac.kr/) | 검색·신착·공지, 내 대출(로그인) | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [열람실 좌석 현황](http://mobileid.kw.ac.kr/seatweb/domian5.asp) | 열람실 실시간 좌석 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [경력개발팀 (job.kw)](https://job.kw.ac.kr/) | 취업 공지·채용정보 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [현장실습 (internship)](https://internship.kw.ac.kr/index.do) | 현장실습 공지 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [KW-IPP](https://ipp.kw.ac.kr/) | 일학습병행 알림마당 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [국제처·글로벌전략팀 (oia)](https://oia.kw.ac.kr/) | 유학생·교환학생 공지 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [학생상담실](https://sangdam.kw.ac.kr/) | 상담 프로그램 공지 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [교수학습센터](https://ontl.kw.ac.kr/) | 학습 프로그램 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [창업지원단](https://startup.kw.ac.kr/) | 창업 공지 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [대학혁신사업단](https://inno.kw.ac.kr/) | 비교과 프로그램 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [참빛인재 비교과 (itplusinfo)](https://itplusinfo.kw.ac.kr/main.do) | 비교과 포인트(SSO) | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [포트폴리오 (kwjob)](https://kwjob.kw.ac.kr/) | 취업 포트폴리오(SSO) | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [국제교육원](https://kwiie.kw.ac.kr/) | 어학 과정 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [인권센터](https://humanrights.kw.ac.kr/) | 인권·성평등 상담 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [교육혁신원](https://icei.kw.ac.kr/) | 성과관리 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [공학교육혁신센터 드림캐처](https://dream.kw.ac.kr/) | e-포트폴리오 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [원격교육지원센터](http://mooc.kw.ac.kr/) | 원격수업 지원 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [캠퍼스타운 사업단](https://kwcampustown.startup-plus.kr/) | 창업·지역 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [HUSS 사업단](https://huss.kw.ac.kr/) | 인문사회 융합 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [반도체특성화대학사업단](https://semi.kw.ac.kr/) | 반도체 사업 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [정보과학교육원](http://iit.kw.ac.kr/) | 학점은행 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [교직과정](https://teacher.kw.ac.kr/) | 교직 | 공식 | 미확인 | 대부분 공개 | 예 |
| [ROTC 사이트](http://142rotc.kw.ac.kr/) | ROTC | 공식 | 미확인 | 대부분 공개 | 예 |
| [대학혁신사업단 옛 주소](https://performance.kw.ac.kr/main.do) | 옛 사이트 | 공식 | 미확인 | 대부분 공개 | 예 |
| [건축학과 (Wix)](https://www.kwuarchitecture.com/) | 학과 소식(RSS) | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [미디어커뮤니케이션학부 (Wix)](https://www.kwmedia.info/) | 학부 공지 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [환경공학과 (Wix)](https://www.envkw.com/) | 학과 소개 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [국제학부 (Canva)](https://kwdois.my.canva.site/) | 학부 소개 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [규정관리시스템](https://rule.kw.ac.kr/) | 학칙·규정 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [홈페이지 수정요청게시판](http://info.kw.ac.kr/webnote/bbs/list.php?bbs_id=www_fuz) | 홈페이지 오류 신고 | 공식 | 미확인 | 대부분 공개 | 예 |
| [푸드코트 옛 사이트](https://foodcourt.kw.ac.kr/) | 2021 폐쇄 | 공식 | 없음·중단 | 대부분 공개 | 예 |
| [일반대학원](https://grad.kw.ac.kr/) | 대학원 공지 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [산학협력단](https://iacf.kw.ac.kr/) | 산학 공지 | 공식 | 살아 있음 | 대부분 공개 | 예 |
| [KLAS 공식 앱 (Android)](https://play.google.com/store/apps/details?id=kr.ac.kw.SmartLearning) | KLAS 모바일, QR 출석, 모바일 학생증, 스마트인증(2차 인증) 등록 | 공식 | 살아 있음 | KLAS 계정 | 예 |
| [KLAS 공식 앱 (iOS)](https://apps.apple.com/kr/app/id1510521632) | KLAS 모바일 | 공식 | 살아 있음 | KLAS 계정 | 예 |

## 이미 알던 것과 로드맵 항목의 생존 확인

| 이름 | 상태 | 근거 |
|---|---|---|
| [KLAS Helper (브라우저 확장)](https://chromewebstore.google.com/detail/klas-helper/jicidjkhiefbhbgbfbemakjndloecjlf) | 살아 있음 | HTTP 200 (KLAS Helper - Chrome Web Store) / Chrome 웹스토어 2.2.1.0 (2026-02-26), GitHub kw-service/klas-helper-extension 2026-09 |
| [KW-Graduation (크롬 확장)](https://chromewebstore.google.com/detail/kw-graduation/fedlhlkkbmflfhmeffadldpojnielkgn) | 살아 있음 | HTTP 200 (KW-graduation - Chrome Web Store) / GitHub Jihye511/KW-Graduation 2024-08; 후속 저장소 oz115/KW-Graduation 2026-08 |
| [openklas (MCP 서버)](https://openklas.com/) | 살아 있음 | HTTP 200 (OpenKLAS) / GitHub openklas/openklas 2026-06-27 |
| [다전공 플래너 (daple)](https://daple.kwuniv.com/) | 살아 있음 | HTTP 200 (다전공 플래너 — 내 전공 경로를 한눈에) |
| [kwuniv.com SSO](https://sso.kwuniv.com/) | 미확인 | 루트 경로 404(22B). daple 로그인 흐름에서만 쓰는 것으로 보임 |
| [KW 알리미 (iOS)](https://apps.apple.com/kr/app/id1634571259) | 살아 있음 | HTTP 200 (‎KW 알리미 앱 - App Store) / 1.0.3 (2024-10) |
| [광운대학교 중앙도서관 앱](https://play.google.com/store/apps/details?id=idoit.slpck.kwangwoon) | 살아 있음 | HTTP 200 (광운대학교 중앙도서관 - Apps on Google Play) / Android 3.6 (2026-09) |
| [K-NET 열람실 API](https://github.com/KNET-KWU/kwu-readingroom-api) | 없음·중단 | GitHub 아카이브(마지막 2026-05-25) / 2026-05-25 아카이브 |
| [행복기숙사(빛솔재) 사이트](https://kw.happydorm.or.kr/) | 살아 있음 | HTTP 200 (광운대학교 행복기숙사) |
| [셔틀버스 안내 (교통안내 페이지)](https://www.kw.ac.kr/ko/tour/directions.jsp) | 살아 있음 | 검색 결과로 현재 내용 확인(직접 요청 안 함) |
| [학식 주간 식단 (함지마루)](https://www.kw.ac.kr/ko/life/facility11.jsp) | 살아 있음 | HTTP 200 (광운대학교 식단안내) |
| [sw.kw.ac.kr (인공지능융합대학 별칭 주소)](https://sw.kw.ac.kr/) | 살아 있음 | HTTP 200 |
| [총학생회 이음 웹사이트](https://www.kwu-studentcouncil.co.kr/) | 살아 있음 | HTTP 200 (광운대학교 제53대 총학생회 이음) |
| [총학생회 Instagram (@kwu_studentcouncil)](https://instagram.com/kwu_studentcouncil) | 미확인 | SNS·위키는 자동 확인 안 함(학교·총학 페이지에 링크된 것만 확인) |
| [총학생회 카카오톡 채널](https://pf.kakao.com/_Cxldyn) | 살아 있음 | HTTP 200 (카카오톡채널 - 광운대 제53대 총학생회 이음) |
| [학과·ROTC 인스타그램 (로드맵 기재분)](https://www.instagram.com/kw.142rotc_official) | 미확인 | SNS·위키는 자동 확인 안 함(학교·총학 페이지에 링크된 것만 확인) |
| [국제학부 Facebook 그룹](https://www.facebook.com/groups/264661916941585/) | 미확인 | SNS·위키는 자동 확인 안 함(학교·총학 페이지에 링크된 것만 확인) |
| [광운대신문 (국문) 사이트·RSS](https://kwnews.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대신문 - 전체기사) |
| [광운소식(광운미디어)](https://news.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운미디어-광운대학교 온라인 홍보페이지) |
| [에브리타임 (광운대)](https://everytime.kr/) | 살아 있음 | HTTP 200 |
| [중앙도서관 KUPIS](https://kupis.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 중앙도서관) |
| [열람실 좌석 현황](http://mobileid.kw.ac.kr/seatweb/domian5.asp) | 살아 있음 | HTTP 200 |
| [경력개발팀 (job.kw)](https://job.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 경력개발팀) |
| [현장실습 (internship)](https://internship.kw.ac.kr/index.do) | 살아 있음 | HTTP 200 (광운대학교 현장실습 온라인 시스템) |
| [KW-IPP](https://ipp.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 KW-IPP공동훈련센터) |
| [국제처·글로벌전략팀 (oia)](https://oia.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 글로벌전략팀) |
| [학생상담실](https://sangdam.kw.ac.kr/) | 살아 있음 | HTTP 200 |
| [교수학습센터](https://ontl.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 교수학습센터) |
| [창업지원단](https://startup.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 창업지원) |
| [대학혁신사업단](https://inno.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 대학혁신사업단) |
| [참빛인재 비교과 (itplusinfo)](https://itplusinfo.kw.ac.kr/main.do) | 살아 있음 | HTTP 200 (광운대학교 참빛인재양성 통합관리시스템) |
| [포트폴리오 (kwjob)](https://kwjob.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교) |
| [국제교육원](https://kwiie.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 한국어교육센터) |
| [인권센터](https://humanrights.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 인권센터) |
| [교육혁신원](https://icei.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 교육혁신원) |
| [공학교육혁신센터 드림캐처](https://dream.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운드림캐처 - 자기주도적 학습 진로관리 시스템) |
| [원격교육지원센터](http://mooc.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운MOOC센터) |
| [캠퍼스타운 사업단](https://kwcampustown.startup-plus.kr/) | 살아 있음 | HTTP 200 (광운대학교 캠퍼스타운) |
| [HUSS 사업단](https://huss.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 인문사회융합인재사업단) |
| [반도체특성화대학사업단](https://semi.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 반도체특성화대학사업단) |
| [정보과학교육원](http://iit.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 정보과학교육원) |
| [교직과정](https://teacher.kw.ac.kr/) | 미확인 | 이번 확인에서 응답 없음(25초 타임아웃·연결 실패) |
| [ROTC 사이트](http://142rotc.kw.ac.kr/) | 미확인 | 이번 확인에서 응답 없음(25초 타임아웃·연결 실패) |
| [대학혁신사업단 옛 주소](https://performance.kw.ac.kr/main.do) | 미확인 | 이번 확인에서 응답 없음(25초 타임아웃·연결 실패) |
| [건축학과 (Wix)](https://www.kwuarchitecture.com/) | 살아 있음 | HTTP 200 (광운대학교 건축학과 / Kwuarchitecture) |
| [미디어커뮤니케이션학부 (Wix)](https://www.kwmedia.info/) | 살아 있음 | HTTP 200 (HOME / 광운대학교 미디어커뮤니케이션학부) |
| [환경공학과 (Wix)](https://www.envkw.com/) | 살아 있음 | HTTP 200 (홈 / 2026학년도 광운대학교 환경공학과) |
| [국제학부 (Canva)](https://kwdois.my.canva.site/) | 살아 있음 | HTTP 200 (광운대 국제학부 웹사이트) |
| [규정관리시스템](https://rule.kw.ac.kr/) | 살아 있음 | HTTP 200 |
| [홈페이지 수정요청게시판](http://info.kw.ac.kr/webnote/bbs/list.php?bbs_id=www_fuz) | 미확인 | 이번 확인에서 응답 없음(25초 타임아웃·연결 실패) |
| [푸드코트 옛 사이트](https://foodcourt.kw.ac.kr/) | 없음·중단 | 웹호스팅 기본 페이지만 나옴(2021-04 폐쇄) |
| [일반대학원](https://grad.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대학교 일반대학원) |
| [산학협력단](https://iacf.kw.ac.kr/) | 살아 있음 | HTTP 200 (광운대산학협력단) |
| [KLAS 공식 앱 (Android)](https://play.google.com/store/apps/details?id=kr.ac.kw.SmartLearning) | 살아 있음 | HTTP 200 (광운대학교 KLAS - Apps on Google Play) |
| [KLAS 공식 앱 (iOS)](https://apps.apple.com/kr/app/id1510521632) | 살아 있음 | HTTP 200 (‎광운대학교 KLAS 앱 - App Store) |

## 확인하지 못한 것

- 인스타그램·페이스북·X 계정은 열지 않았다. 학교·총학 페이지에 링크돼 있다는 사실만 확인했다.
- 단과대·학과 인스타 계정 목록 본문은 총학 인스타 카드뉴스에 있어 읽지 못했다.
- KIF 인스타그램 계정명, Telegram KLAS 봇의 봇 아이디, Discord 공지 봇의 서버 초대 링크, 유니뷰의 스토어 주소는 찾지 못했다.
- KLAS+ iOS는 앱 ID(6820491776)를 웹사이트에서 확인했지만 한국 App Store 주소는 404였다.
- 학생 프로젝트 중 배포 주소가 없는 것(iNoti, 수강신청 도우미, 도서관 API 서버 등)은 실제로 쓰이는지 모른다.
