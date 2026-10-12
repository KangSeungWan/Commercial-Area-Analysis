---
name: 대전 트램 상권 지도
description: 트램이 지날 길 위의 스무 상권 — 공공데이터 분석 프로젝트
colors:
  forest-ink: "#0a1d08"
  forest-ink-hover: "#2b390a"
  moss-text: "#2a332a"
  linen: "#f8f9f5"
  bone: "#eff2e8"
  mist: "#e1e6df"
  eucalyptus: "#c9d5c5"
  lichen: "#c5ccb6"
  sage-mist: "#a5ac9f"
  sage: "#4a6d47"
  sage-gray: "#6b7860"
  route-ink: "#23272e"
  diag-growth: "#228b54"
  diag-rebound: "#eb8214"
  diag-decline: "#c83232"
  diag-stable: "#8c8c8c"
  chart-blue: "#1f4fa3"
typography:
  display:
    fontFamily: "Newsreader, 'Noto Serif KR', serif"
    fontSize: "clamp(40px, 6.6vw, 88px)"
    fontWeight: 300
    lineHeight: 1.08
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Newsreader, 'Noto Serif KR', serif"
    fontSize: "36px"
    fontWeight: 300
    letterSpacing: "-0.02em"
  numeral:
    fontFamily: "Newsreader, 'Noto Serif KR', serif"
    fontSize: "34px"
    fontWeight: 300
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Pretendard, 'Apple SD Gothic Neo', sans-serif"
    fontSize: "18px"
    fontWeight: 600
  body-lead:
    fontFamily: "Pretendard, 'Apple SD Gothic Neo', sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.6
  body:
    fontFamily: "Pretendard, 'Apple SD Gothic Neo', sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Pretendard, 'Apple SD Gothic Neo', sans-serif"
    fontSize: "13px"
    fontWeight: 500
rounded:
  xs: "3px"
  md: "8px"
  lg: "10px"
  button: "20px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "40px"
  2xl: "64px"
components:
  button-primary:
    backgroundColor: "{colors.forest-ink}"
    textColor: "{colors.linen}"
    rounded: "{rounded.button}"
    padding: "10px 22px"
    typography: "{typography.body}"
  button-primary-hover:
    backgroundColor: "{colors.forest-ink-hover}"
    textColor: "{colors.linen}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.forest-ink}"
    rounded: "{rounded.button}"
    padding: "10px 22px"
  tag:
    backgroundColor: "{colors.bone}"
    textColor: "{colors.sage}"
    rounded: "{rounded.pill}"
    padding: "4px 12px"
    typography: "{typography.label}"
  panel:
    backgroundColor: "{colors.bone}"
    rounded: "{rounded.lg}"
    padding: "22px 24px"
  area-card:
    backgroundColor: "{colors.bone}"
    textColor: "{colors.forest-ink}"
    rounded: "{rounded.lg}"
    padding: "12px 16px"
  diagnosis-badge:
    textColor: "#ffffff"
    rounded: "{rounded.pill}"
    padding: "2px 10px"
    typography: "{typography.label}"
  station-card:
    backgroundColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "10px 14px"
---

# Design System: 대전 트램 상권 지도

## Overview

**Creative North Star: "노선 위의 풍경 (The Landscape Along the Line)"**

이 앱은 한 장의 풍경화처럼 시작한다. 리넨빛 하늘 아래 세이지 계열 언덕이 겹겹이 깔리고, 그 위로 실제 정거장 좌표로 그린 트램 2호선 노선이 가는 먹선으로 지나간다. 화면 전체는 그 풍경의 연장이다. 바탕은 종이처럼 밝고 따뜻하며, 글자는 숲색 잉크 하나로 쓴다. 장식은 노선과 땅 자체에서만 나온다.

분위기는 차분하고 서정적이지만 내용은 정확하다. 세리프 제목은 한 화면에 하나뿐이고 가볍게(300) 놓인다. 나머지는 Pretendard로 또박또박 읽힌다. 강조는 숲색 잉크 하나로 끝낸다. 진단 4분류나 지표 색 단계 같은 분석용 색은 풍경 위에 놓인 '측량 표시'다. 브랜드 색과 섞지 않고, 지도·배지·표에서 언제나 같은 뜻으로 쓴다.

현재 커버 화면(`tram_model/cover_page.py`)이 이 체계의 기준이다. 지도·업종 점수·비교 화면(`app.py`)은 아직 Streamlit 기본 테마와 중립 회색 카드(#fafbfc 바탕, #e3e6ea 테두리)를 쓴다. 이것은 커버 쪽으로 맞춰 갈 대상이다. 새 화면과 수정은 이 문서의 토큰을 따른다.

**Key Characteristics:**
- 리넨 바탕 + 숲색 잉크 한 가지로 쓰는 글자와 주 버튼
- 화면당 세리프 제목 하나, 가벼운 굵기(300), 나머지는 Pretendard
- 그림자 없이 얇은 안개색 선과 바탕 톤 차이로 층을 나눔
- 노선·정거장은 먹선과 속이 빈 원, 실제 좌표로만 그림
- 분석 색(진단 4분류, 지표 색 단계)은 브랜드 색과 분리해 뜻을 고정

## Colors

따뜻한 종이 바탕에 숲색 잉크, 그 사이를 세이지 계열 중간 톤이 잇는 낮은 채도의 팔레트. 분석 색은 따로 둔다.

### Primary
- **숲색 잉크 (Forest Ink)**: 모든 본문 글자, 주 버튼 바탕, 커버 노선. 거의 검정에 가까운 녹색이라 순수 검정보다 부드럽게 리넨과 어울린다. 누르면 **이끼 잉크(forest-ink-hover)**로 아주 조금 밝아진다.

### Secondary
- **세이지 (Sage)**: 태그 글자, 단계 번호, 숫자 옆 설명, 포커스 테두리. 강조가 아니라 '안내' 역할을 하는 보조 잉크.
- **세이지 회색 (Sage Gray)**: 보조 정보(메타 문구, 바닥글, 마무리 설명). 본문보다 한 단계 물러난 글자.

### Neutral
- **리넨 (Linen)**: 앱 전체 바탕, 주 버튼 글자.
- **본 (Bone)**: 한 단계 들어간 면(태그, 단계 상자, 카드 바탕). 하늘 그라데이션의 아래쪽 끝.
- **안개 (Mist)**: 모든 구분선과 테두리.
- **이끼 글자 (Moss Text)**: 긴 설명 문단. 숲색 잉크보다 살짝 연해 문단이 무겁지 않다.
- **유칼립투스 · 이끼꽃 · 세이지 안개 (Eucalyptus, Lichen, Sage Mist)**: 커버 언덕 네 겹 중 앞의 세 겹(맨 앞 겹은 세이지). 세이지 안개는 보조 버튼 테두리로도 쓴다.

### Analysis Colors (측량 표시)
- **진단 4분류**: 성장 지속(diag-growth), 트램 반등 기회(diag-rebound), 쇠퇴 우려(diag-decline), 정체·안정(diag-stable). 지도 채색·배지·요약 줄·표에서 같은 색, 같은 뜻.
- **노선 먹색 (route-ink)**: 지도 위 트램 노선·정거장 테두리. 건설 전(계획)은 #8c929a의 가는 선으로 낮춘다.
- **지표 색 단계** (`app.py` RAMP): 나쁨(노랑→주황→적갈), 좋음(연녹→녹), 트램 효과(연청→남색), 중립(회색), 증감(파랑-흰색-빨강, 0 또는 대전 평균이 흰색). 값의 뜻에 따라 고르고, 색 단계를 새로 만들지 않는다.
- **차트 파랑 (chart-blue)**: Altair 차트의 '선택한 상권·실제 값' 선. 비교 대상은 #9aa0a6 회색, 트램 건설 후 예측은 #e07b1a 주황.

### Named Rules
**The One Ink Rule.** 글자와 주 버튼은 숲색 잉크 하나로 쓴다. 강조하려고 새 색을 들이지 않는다. 굵기, 크기, 세리프로 강조한다.

**The Survey Mark Rule.** 분석 색은 데이터의 뜻을 나타낼 때만 쓴다. 진단 주황을 버튼에, 숲색을 지표 색 단계에 쓰지 않는다. 둘이 섞이면 심사자가 색을 읽을 수 없다.

## Typography

**Display Font:** Newsreader, 한글은 Noto Serif KR (serif 대체)
**Body Font:** Pretendard (Apple SD Gothic Neo, sans-serif 대체)

**Character:** 가는 세리프 제목은 풍경화의 제목처럼 조용히 놓이고, Pretendard는 수치와 설명을 또박또박 전달한다. 한글은 `word-break: keep-all`로 어절 단위로 줄을 바꾼다.

### Hierarchy
- **Display** (300, clamp(40px, 6.6vw, 88px), 1.08): 커버 대표 제목 "트램이 지날 길 위의 스무 상권". 화면에 하나뿐.
- **Headline** (300, 36px): 마무리 문구 같은 구획 제목.
- **Numeral** (300, 34px, 세리프): 핵심 수치(반등 기회 상권 수, 기본 시나리오 효과). 숫자는 세리프로, 단위·설명은 Pretendard 15px 세이지로 붙인다.
- **Title** (600, 18px): 카드·열 제목.
- **Body Lead** (400, 18px, 1.6): 대표 문단. 최대 36em.
- **Body** (400, 15px, 1.6): 일반 설명. 지도 화면 카드·범례는 13~14px까지 줄여 쓴다.
- **Label** (500, 13px): 태그, 배지, 범례, 바닥글.

### Named Rules
**The Single Serif Rule.** 세리프는 화면당 제목 하나와 핵심 수치에만 쓴다. 표, 범례, 버튼, 본문에는 쓰지 않는다.

## Layout

- 커버는 가운데 정렬 단일 열(최대 1120px), 위아래 여백이 넉넉하다(대표 영역 위 9vh, 구획 사이 40~64px). 풍경 그림만 화면 폭 전체(100vw)로 넘친다.
- 정보는 얇은 선으로 나눈 3열(`cv-rows`)과 4칸 단계 상자(`cv-steps`)로 놓는다. 760px 아래에서는 모두 한 열로 접힌다.
- 지도·분석 화면은 `layout="wide"`, 사이드바 내비게이션, 지도 높이 620px. 지도 위에는 범례 머리줄(`maphead`)이 붙고 아래 지도와 한 덩어리로 이어진다.
- 간격은 4 / 8 / 16 / 24 / 40 / 64px을 쓴다. 카드 안쪽은 12~16px, 구획 사이는 40px 이상.
- 기준 화면은 데스크톱 발표 시연이다. 모바일은 접히기만 하면 된다.

## Elevation & Depth

평평하다. 깊이는 그림자 대신 바탕 톤(리넨 → 본)과 안개색 선 한 줄로 만든다. 커버 버튼은 `box-shadow: none`이다. 예외는 지도 툴팁 하나다(`0 4px 14px rgba(0,0,0,.14)`). 지도 위에 떠서 다른 색과 겹치므로 분리가 필요하다.

### Named Rules
**The Flat Paper Rule.** 면은 종이처럼 놓인다. 위계가 필요하면 바탕을 한 톤 바꾸거나 선을 긋는다. 그림자는 지도 위에 떠 있는 것에만 허용한다.

## Shapes

부드럽지만 둥글둥글하지 않다. 상자는 10px(카드, 단계 상자), 작은 상자와 툴팁은 8px, 범례 견본은 3px. 버튼은 20px로 알약에 가깝고, 태그·배지는 완전한 알약(999px)이다. 노선은 둥근 끝(`round` cap/join)의 가는 선(1.6px), 정거장은 리넨으로 채운 작은 원에 먹선 테두리다. 지도 위 상권 이름도 같은 모양의 둥근 상자(먹색 바탕/흰 글자는 선택됨, 흰 바탕/먹 글자는 기본)로 그린다.

## Components

### Buttons
차분하고 단단하다. 주 버튼은 하나만 눈에 띈다.
- **Shape:** 거의 알약 모양(20px)
- **Primary:** 숲색 잉크 바탕, 리넨 글자, 10px 22px, 15px 500
- **Hover / Focus:** 이끼 잉크로 아주 조금 밝아짐. 포커스는 세이지 2px 윤곽선, 2px 띄움
- **Secondary:** 투명 바탕, 숲색 글자, 세이지 안개 테두리. 마우스를 올리면 테두리가 숲색으로

### Chips
- **태그:** 본 바탕, 세이지 글자, 안개 테두리, 알약. 커버의 "대전 트램 2호선 · 2030년 개통" 같은 맥락 표시.
- **진단 배지:** 진단 4분류 색 바탕에 흰 글자, 알약, 13px 600. 유형 배지는 본 바탕에 숲색 글자. '불확실' 배지는 흰 바탕에 쇠퇴 색 테두리와 글자.

### Cards / Containers
- **Corner Style:** 10px
- **Background:** 본(목표). 지금 `app.py`의 `.card`는 #fafbfc와 #e3e6ea라 맞춰야 한다
- **Shadow Strategy:** 없음 (Flat Paper Rule)
- **Border:** 안개 1px
- **Internal Padding:** 12px 16px (상권 카드), 22px 24px (단계 상자)

### Navigation
- 커버: 왼쪽에 이름(빈 원 표시 + 600), 오른쪽에 세이지 회색 메타 문구. 사이드바와 헤더는 숨긴다.
- 앱: Streamlit 사이드바. 화면 선택 라디오, 트램 건설 전/후 라디오, 지도 색칠 기준 선택, '분석 방법 한눈에 보기' 버튼, '고급 설정' 접기.

### Map Legend Bar (signature)
지도 바로 위에 붙는 머리줄. 왼쪽은 색 단계 막대(180×10px, 양 끝 값 표기)나 분류 점, 오른쪽은 기호 설명(노선 선, 정거장 원, 상권 핵심/영향 권역 사각형). 지도와 같은 테두리로 이어져 지도의 일부로 읽힌다.

### Station Card (signature)
정거장을 누르면 열리는 상자. 흰 바탕, 8px 둥근 모서리, 왼쪽에 노선 먹색 4px 띠를 둬서 '노선 위의 한 점'임을 나타낸다.

## Do's and Don'ts

### Do:
- **Do** 바탕은 리넨, 글자는 숲색 잉크로 쓰고, 지도 화면의 중립 회색(#fafbfc, #e3e6ea)은 본·안개로 바꿔 나간다.
- **Do** 세리프는 화면당 제목 하나와 핵심 수치에만, 굵기 300으로 쓴다.
- **Do** 진단 4분류 색과 지표 색 단계는 `app.py`의 QC·RAMP 값을 그대로 쓰고, 지도·배지·표에서 같은 뜻을 유지한다.
- **Do** 노선과 정거장은 실제 좌표로 그리고, 먹선과 속이 빈 원으로 표현한다.
- **Do** 한글 문단에는 `word-break: keep-all`을 둔다.

### Don't:
- **Don't** 그림자로 위계를 만들지 않는다. 지도 툴팁만 예외다.
- **Don't** 분석 색(진단 주황·빨강, 차트 파랑)을 버튼이나 장식에 쓰지 않는다.
- **Don't** 외부 사진·스톡 이미지·아이콘 장식을 풍경 대신 넣지 않는다. 그림은 노선과 땅으로만 만든다.
- **Don't** 세리프를 표, 범례, 버튼, 본문에 쓰지 않는다.
