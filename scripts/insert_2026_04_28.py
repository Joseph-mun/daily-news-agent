#!/usr/bin/env python3
"""Insert 2026-04-28 articles + daily briefing analysis into news.db."""
import sqlite3
from datetime import datetime, timezone

DB = '/tmp/dailynewsbot_run_2026-04-28/web/data/news.db'
TODAY = '2026-04-28'
NOW_ISO = datetime.now(timezone.utc).isoformat()

ARTICLES = [
    {
        'category': '[국내]',
        'title': '금융보안원, NATO 락드쉴즈 2026 5년 연속 참가…AI 기반 다층 방어 체계로 실전 역량 검증',
        'title_original': '금융보안원, 락드쉴즈 2026서 AI 기반 사이버 방어 역량 검증',
        'url': 'https://www.dailysecu.com/news/articleView.html?idxno=206413',
        'summary': '금융보안원이 4월 20~24일 NATO CCDCOE 주관 락드쉴즈 2026에 참가해 AI로 악성코드 분류·리포트를 자동화하고 웹 공격 1단계·악성코드 2단계의 다층 방어 체계 실효성을 점검했다.',
    },
    {
        'category': '[국내]',
        'title': "안랩, 한국·헝가리 연합팀 블루팀으로 락드쉴즈 2026 참가…39개국 4,000명 규모 NATO 훈련",
        'title_original': "안랩, '락드쉴즈 2026' 참가…국제 사이버 방어 훈련서 실전 대응 역량 점검",
        'url': 'https://www.dailysecu.com/news/articleView.html?idxno=206420',
        'summary': '안랩이 39개국 약 4,000명·국내 47개 기관 170여 명 규모의 NATO 락드쉴즈 2026에 한국·헝가리 연합팀 블루팀으로 참여해 전략·기술 훈련 전반에서 위협 분석·대응 역량을 입증했다.',
    },
    {
        'category': '[국내]',
        'title': '금감원·금융연수원·은행연합회·지방지주, 사외이사 양성·역량강화 업무협약 체결',
        'title_original': '금감원·5대 금융지주, 사외이사 역량 강화 맞손…“지배구조 선진화”',
        'url': 'https://www.getnews.co.kr/news/articleView.html?idxno=806817',
        'summary': '4월 28일 이찬진 금감원장이 금융연수원·은행연합회·지방금융지주와 사외이사 후보군 양성·교육 협약을 체결, 금융회사 지배구조 가이드라인에 부합하는 전문성 풀을 공동 운영하기로 했다.',
    },
    {
        'category': '[국내]',
        'title': '금감원, 불법 핀플루언서 AI 추적 본격 가동…SNS·증권방송 선행매매 집중 점검',
        'title_original': '“이 종목 추천합니다”…증시 혼란에 불법 핀플루언서 기승 / 금감원 AI 추적 도입',
        'url': 'https://segye.com/newsView/20260412508702',
        'summary': '금감원은 4월 28일 정오 “불법 핀플루언서, AI 추적에 더 이상 숨을 곳 없다”는 보도자료로 SNS·증권방송 기반 선행매매·허위정보 유포에 대해 AI 매체 모니터링·집중제보 체계를 가동한다고 밝혔다.',
    },
    {
        'category': '[국내]',
        'title': '금융위·금감원, 여신전문금융업법 시행령 개정안 4월 28일 국무회의 의결',
        'title_original': '이번주 국내 주요 금융일정(4.27~5.1)',
        'url': 'https://www.newspim.com/news/view/20260424001257',
        'summary': '4월 28일 국무회의에서 여신전문금융업법 시행령 개정안이 의결되고 같은 날 금융위가 불법사금융 신고 문턱 완화·차단속도 강화 방안을 발표하는 등 카드·여전사 규율과 소비자 보호 인프라가 동시에 정비된다.',
    },
    {
        'category': '[국내]',
        'title': '과기정통부·KISA, 차세대 보안리더 BoB 15기 4월 30일 모집 개시…공급망·AI 위협 본격 대응',
        'title_original': '과기정통부·KISA, 차세대보안리더양성 BoB 15기 교육생 모집',
        'url': 'https://www.dailysecu.com/news/articleView.html?idxno=206441',
        'summary': '과기정통부와 KISA가 4월 30일 차세대 보안리더 양성 BoB 15기 교육생 모집을 개시한다. K-CTI 2026에서 KISA가 “공급망·AI 위협이 본격화됐다”고 진단한 만큼 인재 파이프라인 보강이 시급한 상황이다.',
    },
    {
        'category': '[해외]',
        'title': 'Anthropic Claude Mythos Preview, 제3자 벤더 환경 통해 Discord 그룹이 URL 추측으로 권한외 접근',
        'title_original': 'Unauthorized group has gained access to Anthropic’s exclusive cyber tool Mythos, report claims',
        'url': 'https://techcrunch.com/2026/04/21/unauthorized-group-has-gained-access-to-anthropics-exclusive-cyber-tool-mythos-report-claims/',
        'summary': '미공개 사이버 보안 모델 Claude Mythos Preview에 한 Discord 그룹이 Anthropic 제3자 협력사 계정·URL 패턴 추측으로 접근, 4월 26~27일까지도 사용 사실이 확인됐다고 Check Point Apr 27 위클리 리포트가 짚었다.',
    },
    {
        'category': '[해외]',
        'title': 'UK Biobank, 50만 명 비식별 헬스·유전 데이터 알리바바서 매각 시도…학술기관 3곳 권한 남용',
        'title_original': 'Health data of 500,000 UK Biobank members offered for sale in data breach',
        'url': 'https://www.itv.com/news/2026-04-23/details-of-500000-uk-biobank-volunteers-hacked-and-offered-for-sale',
        'summary': '4월 20일 UK Biobank가 영국 정부에 보고한 50만 자원자 비식별 데이터 3건이 알리바바 마켓플레이스에 게시됐다 회수됐고, 데이터 접근 권한을 가진 학술기관 3곳 연구자가 계약을 위반한 것으로 4월 25~26일까지 추가 확인됐다.',
    },
    {
        'category': '[해외]',
        'title': 'France Titres(ANTS), 1900만 건 신분증 데이터 유출 확인…프랑스 인구 1/3 규모 피싱·사회공학 위험',
        'title_original': 'France confirms data breach at government agency that manages citizens’ IDs',
        'url': 'https://techcrunch.com/2026/04/22/france-confirms-data-breach-at-government-agency-that-manages-citizens-ids/',
        'summary': '프랑스 신분증 발급 기관 ANTS(France Titres)가 4월 15일 침해를 인지, breach3d가 1800만~1900만 건(프랑스 인구 1/3)을 매각 시도 중이며 이름·생년월일·주소·이메일 등이 노출돼 대규모 피싱·사회공학 공격 우려가 제기됐다.',
    },
    {
        'category': '[해외]',
        'title': 'Itron, 100개국 8,000고객 유틸리티 IT망 침해 SEC 공시…고객망은 미피해 주장',
        'title_original': 'Critical infrastructure giant Itron says it was hacked',
        'url': 'https://techcrunch.com/2026/04/27/critical-infrastructure-giant-itron-says-it-was-hacked/',
        'summary': '에너지·물 인프라 SaaS 공급 Itron이 4월 13일 내부 IT망 권한외 접근을 인지하고 4월 27일 SEC에 8-K로 공시했다. 고객 호스팅 환경 피해는 없으며 운영은 중대한 영향 없이 지속 중이라고 밝혔다.',
    },
    {
        'category': '[해외]',
        'title': "CISA, Cisco Catalyst SD-WAN Manager CVE-2026-20133 KEV 추가…UAT-8616 그룹 적극 악용 진행",
        'title_original': 'CISA flags another Cisco Catalyst SD-WAN Manager bug as exploited (CVE-2026-20133)',
        'url': 'https://www.helpnetsecurity.com/2026/04/21/cisa-flags-another-cisco-catalyst-sd-wan-manager-bug-as-exploited-cve-2026-20133/',
        'summary': 'CISA가 Cisco Catalyst SD-WAN Manager 정보유출 CVE-2026-20133을 KEV에 추가하고 FCEB 패치 마감을 4월 24일로 지정, 4월 27일 Talos가 UAT-8616 그룹의 적극 악용·하든닝 가이드를 갱신해 금융 SD-WAN 경계망에도 경보가 확산됐다.',
    },
]

ANALYSIS = """### 종합요약

**4월 28일 새벽까지 이어진 48시간**은 정부·인프라·AI 모델이라는 ‘제3자 신뢰의 세 축’이 동시에 흔들린 구간이었다. 프랑스 신분증 발급 기관, 영국 국가 헬스 코호트, 미국 유틸리티 SaaS, 그리고 Anthropic의 미공개 보안 모델까지 — **공공·규제·연구·AI** 어느 영역도 안전지대가 아니라는 사실이 한꺼번에 드러났다. 이번 종합요약은 이 충격이 한국 금융권 보안 운영에 어떤 재설계 압력으로 전가되는지를 세 축으로 읽는다.

### 축1. 신뢰 경계의 동시 균열 — 시민 ID·바이오뱅크·유틸리티 SaaS가 같은 주에 노출

프랑스 **France Titres**(ANTS)는 4월 15일 침해 사실을 인지한 뒤 1,800만~**1,900만 건**(프랑스 인구의 약 1/3) 규모의 신분증 데이터가 ‘breach3d’ 명의로 매각 시도되는 사실을 확인했다 [9]. 이름·생년월일·우편주소·이메일이 결합된 데이터는 **Phishing-as-a-Service**(피싱 자동화 공격) 입장에서는 한국 금융기관 고객을 표적으로 한 EU발 사회공학 공격의 원료가 된다.

같은 주 **UK Biobank**는 50만 명 비식별 헬스·유전 데이터 3건이 알리바바 마켓플레이스에 노출된 사실을 영국 정부에 보고했고, 접근 권한을 가진 학술기관 3곳 연구자가 계약을 위반한 ‘권한 남용형 내부자 사고’로 정리되고 있다 [8]. 비식별 처리 자체는 유지됐으나, 성별·연령·생활습관 변수의 결합은 **Re-identification Risk**(재식별 위험)을 충분히 끌어올린다.

미국 유틸리티 SaaS **Itron**은 4월 13일 내부 IT망 권한외 접근을 인지하고 **4월 27일** SEC에 8-K로 공시했다. 100개국 **8,000 고객**을 운영하는 인프라 사업자가 “고객 호스팅 환경 피해 없음”을 주장했지만, 동일 주기 동안 Cisco Catalyst SD-WAN Manager **CVE-2026-20133**이 KEV에 추가되고 **UAT-8616** 그룹의 적극 악용이 확인되면서 [10][11], 금융권 SD-WAN·MPLS 경계망 또한 같은 시계열의 위험 곡선 위에 놓였다.

### 축2. 금융 보안의 ‘AI 검증 모드’ 진입 — 락드쉴즈와 핀플루언서 추적이 같은 문법

**금융보안원**은 NATO CCDCOE의 **락드쉴즈 2026**(4월 20~24일)에 5년 연속 참가해 악성코드 분류·리포트 자동화와 웹 1단계·악성코드 2단계 다층 방어 체계의 실효성을 검증했다 [1]. **안랩**은 한국·헝가리 연합팀 블루팀으로 39개국 약 **4,000명** 규모 훈련에 참여해 민간 보안기업 차원의 분석·대응 깊이를 더했다 [2]. 두 기사는 ‘AI를 도입했다’는 단계가 아니라 **‘AI를 글로벌 기준의 적대적 시나리오에서 검증했다’**는 점에서 무게가 다르다.

같은 시계열에 금감원은 4월 28일 정오 “**불법 핀플루언서, AI 추적에 더 이상 숨을 곳 없다**” 보도자료를 내고 SNS·증권방송 기반 선행매매·허위정보 유포에 대해 AI 매체 모니터링과 집중제보 체계를 본격 가동했다 [4]. 같은 날 국무회의에서 **여신전문금융업법** 시행령 개정안이 의결되고 불법사금융 신고 절차 완화 방안이 함께 발표되며, 카드·여전사 규율과 소비자 보호 인프라가 한 묶음으로 정비됐다 [5].

요지는 단순하다. **방어**(락드쉴즈)와 **시장 감시**(핀플루언서 AI 추적), **규제**(여전법 시행령)가 같은 ‘AI를 1차 도구로 쓰는’ 문법을 공유하기 시작했다는 점이다. 금융기관 입장에서는 SOC·FDS·시장감시·규제 보고가 같은 모델·로그 인프라 위에 정렬되도록 만드는 작업이 빠르게 표준이 되어 가고 있다.

### 축3. 인재와 모델의 동시 거버넌스 — 사외이사·BoB 15기·Mythos 권한외 접근

**금감원**은 4월 28일 금융연수원·은행연합회·지방금융지주와 **사외이사 양성·역량강화 업무협약**을 체결, 지배구조 가이드라인에 맞춘 후보군 풀을 공동 운영하기로 했다 [3]. 같은 시기 **과기정통부·KISA**는 4월 30일 BoB 15기 차세대 보안리더 모집을 개시한다 [6]. 이사회 거버넌스의 ‘판단력 인재’와 보안 운영의 ‘기술력 인재’가 **2026년 하반기 동시 충원**되는 셈이다.

반대편에는 **Anthropic Claude Mythos Preview** 사고가 있다. 한 Discord 그룹이 Anthropic의 제3자 협력사 계정과 과거 URL 패턴을 결합해 미공개 보안 모델에 접근했고, 4월 26~27일까지도 사용 사실이 확인됐다 [7]. 이 사건은 **AI-BOM**(AI 구성요소 명세서) 부재, 벤더 위탁 환경의 시크릿 스프롤, 그리고 **Pre-disclosure Gap**(공개 전 모델이 외부에 노출되는 간극)을 동시에 드러낸 사례다.

금융권의 함의는 명확하다. AI 거버넌스는 모델 카드·정책 문서로 끝나지 않으며, 벤더 환경의 토큰·URL·접근 기록까지 위임된 신뢰의 단위로 관리해야 한다는 것이다. 사외이사와 BoB 인재 풀이 그 ‘위임된 신뢰’를 검증할 수 있는 질문을 가져야 모델 보안의 결락점이 메워진다.

### 수렴점

이번 48시간이 보여주는 단일 명제는 “**제3자 신뢰는 더 이상 체크박스로 처리할 수 없다**”는 것이다. 시민 ID 발급 기관, 국가 코호트 연구, 인프라 SaaS, 그리고 미공개 AI 모델은 모두 외부 위탁·접근 권한이라는 같은 결합조직을 공유하기 때문에 한 곳에서 파열이 시작되면 한 주 안에 다른 영역으로 확산된다.

한국 금융권의 다음 액션 라인은 **락드쉴즈 검증 결과를 SOC·FDS 표준운영절차로 환류**, **핀플루언서 AI 추적의 모델·데이터 거버넌스 문서화**, **사외이사·BoB 인재 풀이 ‘벤더 환경 검증’을 정식 의제로 채택**하는 세 가지로 모인다. 이는 곧 ‘AI를 쓰는 보안’에서 ‘AI를 검증·위임·회수할 줄 아는 보안’으로의 단계 전환을 의미한다.
"""

con = sqlite3.connect(DB)
cur = con.cursor()

inserted_ids = []
for art in ARTICLES:
    cur.execute(
        """INSERT INTO articles (date, category, title, title_original, url, summary, insight, detected_date, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (TODAY, art['category'], art['title'], art['title_original'], art['url'],
         art['summary'], '', TODAY, NOW_ISO)
    )
    inserted_ids.append(cur.lastrowid)

# Category guard
cur.execute(
    "SELECT id, category FROM articles WHERE date=? AND category NOT IN ('[국내]','[해외]')",
    (TODAY,),
)
bad = cur.fetchall()
if bad:
    con.rollback()
    raise SystemExit(f"category guard failed: {bad}")

# Upsert daily_briefings
cur.execute("DELETE FROM daily_briefings WHERE date=?", (TODAY,))
cur.execute(
    "INSERT INTO daily_briefings (date, analysis, created_at) VALUES (?, ?, ?)",
    (TODAY, ANALYSIS, NOW_ISO)
)

con.commit()

print(f"Inserted article ids: {inserted_ids}")
print(f"Analysis chars: {len(ANALYSIS)}")
print(f"Article count for {TODAY}: {cur.execute('SELECT COUNT(*) FROM articles WHERE date=?', (TODAY,)).fetchone()[0]}")
con.close()
